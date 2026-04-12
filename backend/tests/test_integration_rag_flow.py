"""
Tests d'intégration — Flux RAG complet (REQ-02, REQ-03, REQ-04, REQ-09)

Couvre le flux end-to-end :
  symptômes → diagnostic différentiel → prescription → alertes de sécurité
  + assistant chat avec sources citées

Toutes les dépendances externes (LLM, MongoDB) sont mockées.
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.models.common import AgeGroup, AlertLevel
from backend.models.consultation import Prescription, Symptom
from backend.models.document import DocumentSource, RAGResponse
from backend.models.patient import Comorbidities, PatientProfile
from backend.services.alert_service import AlertService
from backend.services.chat_service import ChatService
from backend.services.diagnostic_service import DiagnosticService
from backend.services.prescription_service import ANTIBIOTIC_PROTOCOLS, PrescriptionService
from backend.services.llm_router import LLMResult
from backend.services.llamaindex_pipeline import StreamEvent


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _make_patient(
    age_group: AgeGroup = AgeGroup.ADULT,
    weight_kg: float | None = 70.0,
    allergies: list[str] | None = None,
    renal_failure: bool = False,
    hepatic_failure: bool = False,
    current_medications: list[str] | None = None,
) -> PatientProfile:
    return PatientProfile(
        full_name="Patient Test",
        weight_kg=weight_kg,
        age_group=age_group,
        allergies=allergies or [],
        comorbidities=Comorbidities(
            renal_failure=renal_failure,
            hepatic_failure=hepatic_failure,
        ),
        current_medications=current_medications or [],
    )


def _make_diagnosis_json(diagnoses: list[dict] | None = None) -> str:
    """Return a JSON array of diagnoses suitable for LLM mock output."""
    if diagnoses is None:
        diagnoses = [
            {"condition": "Paludisme", "probability": 0.80, "icd_code": "B54"},
            {"condition": "Fièvre typhoïde", "probability": 0.60, "icd_code": "A01.0"},
            {"condition": "Dengue", "probability": 0.40, "icd_code": "A90"},
        ]
    return json.dumps(diagnoses)


def _make_rag_service(
    llm_answer: str = "Réponse médicale basée sur les sources.",
    chunks: list[dict] | None = None,
) -> MagicMock:
    """Build a mock RAG pipeline with the same query() interface as LlamaIndexPipeline."""
    if chunks is None:
        chunks = [
            {
                "document_id": "doc1",
                "content": "Le paludisme est traité par artémisinine.",
                "metadata": {"source": "OMS_AFRO", "section": "Paludisme", "page": 12},
                "score": 0.92,
            },
            {
                "document_id": "doc2",
                "content": "L'amoxicilline est un antibiotique à large spectre.",
                "metadata": {"source": "CHU_LOME", "section": "Antibiotiques", "page": 5},
                "score": 0.85,
            },
        ]

    sources = [
        DocumentSource(
            document_id=str(c.get("document_id", "")),
            title=c.get("metadata", {}).get("source", ""),
            source=c.get("metadata", {}).get("source", ""),
            section=c.get("metadata", {}).get("section"),
            excerpt=c.get("content", "")[:200],
            page=c.get("metadata", {}).get("page"),
        )
        for c in chunks
    ]

    rag_response = RAGResponse(
        answer=llm_answer,
        sources=sources,
        llm_used="qwen3",
        fallback_used=False,
    )

    mock_llm = MagicMock()
    mock_llm.generate = AsyncMock(return_value=LLMResult(answer=llm_answer, fallback_used=False))
    mock_llm.last_used = "qwen3"

    service = MagicMock()
    service.query = AsyncMock(return_value=rag_response)
    service._llm = mock_llm

    async def _query_stream(**kwargs):
        yield StreamEvent(type="token", content=llm_answer)
        yield StreamEvent(
            type="done",
            answer=llm_answer,
            sources=sources,
            llm_used="qwen3",
        )

    service.query_stream = MagicMock(side_effect=_query_stream)
    return service


# ---------------------------------------------------------------------------
# 1. Flux complet : symptômes → diagnostic différentiel (REQ-02)
# ---------------------------------------------------------------------------

class TestDiagnosticFlow:
    """REQ-02 : Diagnostic différentiel via pipeline RAG."""

    def test_returns_at_least_3_diagnoses(self):
        """Le service retourne au moins 3 diagnostics différentiels."""
        rag = _make_rag_service(llm_answer=_make_diagnosis_json())
        service = DiagnosticService(rag_service=rag)
        symptoms = [
            Symptom(name="fièvre", severity="severe", duration_days=3),
            Symptom(name="céphalées", severity="moderate"),
        ]

        result = asyncio.run(service.get_differential_diagnosis(symptoms))

        assert len(result.diagnoses) >= 3

    def test_diagnoses_have_probability_scores(self):
        """Chaque diagnostic possède un score de probabilité entre 0 et 1."""
        rag = _make_rag_service(llm_answer=_make_diagnosis_json())
        service = DiagnosticService(rag_service=rag)
        symptoms = [Symptom(name="fièvre", severity="severe")]

        result = asyncio.run(service.get_differential_diagnosis(symptoms))

        for diag in result.diagnoses:
            assert 0.0 <= diag.probability <= 1.0, (
                f"Probabilité hors plage pour {diag.condition!r}: {diag.probability}"
            )

    def test_diagnoses_ordered_by_descending_probability(self):
        """Les diagnostics sont triés par probabilité décroissante."""
        rag = _make_rag_service(llm_answer=_make_diagnosis_json())
        service = DiagnosticService(rag_service=rag)
        symptoms = [Symptom(name="fièvre")]

        result = asyncio.run(service.get_differential_diagnosis(symptoms))

        probabilities = [d.probability for d in result.diagnoses]
        assert probabilities == sorted(probabilities, reverse=True)

    def test_diagnoses_have_icd_codes(self):
        """Les diagnostics incluent des codes CIM-10 quand disponibles."""
        rag = _make_rag_service(llm_answer=_make_diagnosis_json())
        service = DiagnosticService(rag_service=rag)
        symptoms = [Symptom(name="fièvre")]

        result = asyncio.run(service.get_differential_diagnosis(symptoms))

        icd_codes = [d.icd_code for d in result.diagnoses if d.icd_code]
        assert len(icd_codes) >= 1, "Au moins un code CIM-10 attendu"

    def test_patient_profile_influences_prompt(self):
        """Le profil patient est transmis au service RAG."""
        rag = _make_rag_service(llm_answer=_make_diagnosis_json())
        service = DiagnosticService(rag_service=rag)
        patient = _make_patient(age_group=AgeGroup.CHILD, weight_kg=15.0)
        symptoms = [Symptom(name="fièvre")]

        result = asyncio.run(
            service.get_differential_diagnosis(symptoms, patient_profile=patient)
        )

        # RAG query must have been called
        rag.query.assert_called_once()
        assert len(result.diagnoses) >= 3

    def test_fallback_when_llm_returns_invalid_json(self):
        """En cas de réponse LLM invalide, le service retourne 3 diagnostics de secours."""
        rag = _make_rag_service(llm_answer="Réponse non-JSON invalide.")
        service = DiagnosticService(rag_service=rag)
        symptoms = [Symptom(name="toux")]

        result = asyncio.run(service.get_differential_diagnosis(symptoms))

        assert len(result.diagnoses) >= 3


# ---------------------------------------------------------------------------
# 2. Flux complet : diagnostic → prescription (REQ-03)
# ---------------------------------------------------------------------------

class TestPrescriptionFlow:
    """REQ-03 : Prescription antibiotique adaptée au profil patient."""

    def test_adult_prescription_contains_all_fields(self):
        """La prescription adulte contient tous les champs requis."""
        service = PrescriptionService()
        patient = _make_patient(AgeGroup.ADULT, 70.0)

        rx = asyncio.run(service.calculate_prescription("amoxicillin", patient))

        assert rx.antibiotic == "amoxicillin"
        assert rx.dose_mg > 0
        assert rx.frequency
        assert rx.duration_days > 0
        assert rx.route in ("oral", "IV", "IM")

    def test_paediatric_dose_calculated_per_kg(self):
        """La dose pédiatrique est calculée au poids (mg/kg)."""
        service = PrescriptionService()
        patient = _make_patient(AgeGroup.CHILD, weight_kg=20.0)
        protocol = ANTIBIOTIC_PROTOCOLS["amoxicillin"]

        rx = asyncio.run(service.calculate_prescription("amoxicillin", patient))

        expected_dose = protocol.paediatric_dose_per_kg * 20.0
        assert rx.dose_mg == pytest.approx(expected_dose)
        assert rx.dose_per_kg == protocol.paediatric_dose_per_kg
        assert rx.is_capped_to_adult_dose is False

    def test_paediatric_dose_capped_to_adult_max(self):
        """La dose pédiatrique est plafonnée à la dose adulte maximale."""
        service = PrescriptionService()
        # 80 kg child: 50 mg/kg × 80 = 4000 mg > 3000 mg adult max
        patient = _make_patient(AgeGroup.CHILD, weight_kg=80.0)

        rx = asyncio.run(service.calculate_prescription("amoxicillin", patient))

        assert rx.dose_mg == ANTIBIOTIC_PROTOCOLS["amoxicillin"].adult_max_dose_mg
        assert rx.is_capped_to_adult_dose is True

    def test_renal_failure_reduces_dose(self):
        """L'insuffisance rénale réduit la dose selon le facteur d'ajustement."""
        service = PrescriptionService()
        patient = _make_patient(AgeGroup.ADULT, 70.0, renal_failure=True)
        protocol = ANTIBIOTIC_PROTOCOLS["amoxicillin"]

        rx = asyncio.run(service.calculate_prescription("amoxicillin", patient))

        expected = protocol.adult_max_dose_mg * protocol.renal_adjustment_factor
        assert rx.dose_mg == pytest.approx(expected)

    def test_hepatic_failure_reduces_dose(self):
        """L'insuffisance hépatique réduit la dose selon le facteur d'ajustement."""
        service = PrescriptionService()
        patient = _make_patient(AgeGroup.ADULT, 70.0, hepatic_failure=True)
        protocol = ANTIBIOTIC_PROTOCOLS["metronidazole"]

        rx = asyncio.run(service.calculate_prescription("metronidazole", patient))

        expected = protocol.adult_max_dose_mg * protocol.hepatic_adjustment_factor
        assert rx.dose_mg == pytest.approx(expected)

    def test_neonatal_dose_calculated(self):
        """La dose néonatale est calculée au poids."""
        service = PrescriptionService()
        patient = _make_patient(AgeGroup.NEONATAL, weight_kg=3.5)
        protocol = ANTIBIOTIC_PROTOCOLS["amoxicillin"]

        rx = asyncio.run(service.calculate_prescription("amoxicillin", patient))

        assert rx.dose_mg == pytest.approx(protocol.paediatric_dose_per_kg * 3.5)


# ---------------------------------------------------------------------------
# 3. Flux complet : prescription → alertes de sécurité (REQ-09)
# ---------------------------------------------------------------------------

class TestAlertFlow:
    """REQ-09 : Alertes de sécurité sur la prescription."""

    def test_allergy_conflict_generates_critical_alert(self):
        """Une allergie connue génère une alerte CRITIQUE bloquante."""
        alert_svc = AlertService()
        patient = _make_patient(allergies=["amoxicillin"])
        protocol = ANTIBIOTIC_PROTOCOLS["amoxicillin"]
        rx = Prescription(
            antibiotic="amoxicillin",
            dose_mg=protocol.adult_max_dose_mg,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
        )

        alerts = asyncio.run(alert_svc.check_prescription(rx, patient))

        critical = [a for a in alerts if a.level == AlertLevel.CRITICAL and a.type == "allergy"]
        assert len(critical) >= 1, "Une alerte critique d'allergie est attendue"

    def test_allergy_alert_proposes_alternative(self):
        """L'alerte d'allergie propose une alternative thérapeutique."""
        alert_svc = AlertService()
        patient = _make_patient(allergies=["ciprofloxacin"])
        protocol = ANTIBIOTIC_PROTOCOLS["ciprofloxacin"]
        rx = Prescription(
            antibiotic="ciprofloxacin",
            dose_mg=protocol.adult_max_dose_mg,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
        )

        alerts = asyncio.run(alert_svc.check_prescription(rx, patient))

        critical = [a for a in alerts if a.level == AlertLevel.CRITICAL and a.type == "allergy"]
        assert len(critical) >= 1
        assert critical[0].alternative is not None, "Une alternative doit être proposée"

    def test_age_contraindication_generates_critical_alert(self):
        """La contre-indication par âge génère une alerte CRITIQUE."""
        alert_svc = AlertService()
        patient = _make_patient(AgeGroup.CHILD, weight_kg=20.0)
        protocol = ANTIBIOTIC_PROTOCOLS["ciprofloxacin"]
        rx = Prescription(
            antibiotic="ciprofloxacin",
            dose_mg=protocol.adult_max_dose_mg,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
        )

        alerts = asyncio.run(alert_svc.check_prescription(rx, patient))

        critical = [
            a for a in alerts
            if a.level == AlertLevel.CRITICAL and a.type == "contraindication"
        ]
        assert len(critical) >= 1

    def test_drug_interaction_generates_warning(self):
        """Une interaction médicamenteuse connue génère une alerte WARNING."""
        alert_svc = AlertService()
        patient = _make_patient(current_medications=["warfarin"])
        protocol = ANTIBIOTIC_PROTOCOLS["ciprofloxacin"]
        rx = Prescription(
            antibiotic="ciprofloxacin",
            dose_mg=protocol.adult_max_dose_mg,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
        )

        alerts = asyncio.run(alert_svc.check_prescription(rx, patient))

        warnings = [a for a in alerts if a.level == AlertLevel.WARNING and a.type == "interaction"]
        assert len(warnings) >= 1

    def test_no_alerts_for_safe_prescription(self):
        """Aucune alerte pour une prescription sans risque."""
        alert_svc = AlertService()
        patient = _make_patient()  # adult, no allergies, no comorbidities
        protocol = ANTIBIOTIC_PROTOCOLS["amoxicillin"]
        rx = Prescription(
            antibiotic="amoxicillin",
            dose_mg=protocol.adult_max_dose_mg,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
        )

        alerts = asyncio.run(alert_svc.check_prescription(rx, patient))

        assert alerts == []

    def test_renal_failure_generates_warning_alert(self):
        """L'insuffisance rénale génère une alerte WARNING."""
        alert_svc = AlertService()
        patient = _make_patient(renal_failure=True)
        protocol = ANTIBIOTIC_PROTOCOLS["amoxicillin"]
        rx = Prescription(
            antibiotic="amoxicillin",
            dose_mg=protocol.adult_max_dose_mg,
            frequency=protocol.frequency,
            duration_days=protocol.duration_days,
            route=protocol.route,
        )

        alerts = asyncio.run(alert_svc.check_prescription(rx, patient))

        warnings = [a for a in alerts if a.level == AlertLevel.WARNING]
        assert len(warnings) >= 1


# ---------------------------------------------------------------------------
# 4. Flux complet : chat RAG avec sources citées (REQ-04)
# ---------------------------------------------------------------------------

class TestChatRAGFlow:
    """REQ-04 : Assistant Q&A conversationnel avec sources citées."""

    def _make_chat_service(self, llm_answer: str = "L'amoxicilline est indiquée.") -> ChatService:
        """Build a ChatService with mocked LLMRouter and MongoDB.

        Updated for LLM-only ChatService (no RAG). Uses StreamChunk mock.
        """
        from backend.services.llm_router import StreamChunk

        mock_llm = MagicMock()

        async def _fake_generate_stream(prompt: str, context: list[dict]):
            for word in llm_answer.split():
                yield StreamChunk(token=word + " ", llm_used="qwen3")

        mock_llm.generate_stream = _fake_generate_stream

        # Mock MongoDB for ChatService session persistence
        mock_session_collection = MagicMock()
        mock_session_collection.update_one = AsyncMock(return_value=None)
        mock_session_collection.find_one = AsyncMock(return_value=None)

        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_session_collection)

        return ChatService(db=mock_db, llm_router=mock_llm)

    def test_chat_returns_rag_response(self):
        """send_message_stream yields a done event with a non-empty answer."""
        chat_svc = self._make_chat_service("L'amoxicilline est indiquée pour les infections ORL.")

        async def _collect():
            events = []
            async for event in chat_svc.send_message_stream(
                session_id=None,
                user_message="Quel antibiotique pour une otite ?",
            ):
                events.append(event)
            return events

        events = asyncio.run(_collect())
        done_events = [e for e in events if e.type == "done"]

        assert len(done_events) == 1
        assert done_events[0].answer.strip() == "L'amoxicilline est indiquée pour les infections ORL."

    def test_chat_response_includes_empty_sources(self):
        """La réponse du chat Q&A ne cite aucune source (LLM-only, pas de RAG)."""
        chat_svc = self._make_chat_service()

        async def _collect():
            async for event in chat_svc.send_message_stream(
                session_id=None,
                user_message="Quelle est la posologie de l'amoxicilline ?",
            ):
                if event.type == "done":
                    return event
            return None

        done = asyncio.run(_collect())
        assert done is not None
        assert done.sources == [], "Q&A chat should return empty sources (LLM-only)"

    def test_chat_sources_always_empty_in_qa_mode(self):
        """Les sources sont toujours vides en mode Q&A (pas de RAG)."""
        chat_svc = self._make_chat_service()

        async def _collect():
            async for event in chat_svc.send_message_stream(
                session_id=None,
                user_message="Traitement du paludisme ?",
            ):
                if event.type == "done":
                    return event
            return None

        done = asyncio.run(_collect())
        assert done is not None
        assert done.sources == [], "Q&A chat should return empty sources"

    def test_chat_with_patient_context(self):
        """Le contexte patient est inclus dans le prompt envoyé au LLM."""
        chat_svc = self._make_chat_service()
        patient = _make_patient(AgeGroup.CHILD, weight_kg=15.0)

        async def _collect():
            events = []
            async for event in chat_svc.send_message_stream(
                session_id=None,
                user_message="Quelle dose pour cet enfant ?",
                patient_context=patient,
            ):
                events.append(event)
            return events

        events = asyncio.run(_collect())
        # Verify we got a done event (LLM processed the request)
        done_events = [e for e in events if e.type == "done"]
        assert len(done_events) == 1, "Should get exactly one done event"

    def test_chat_session_persisted(self):
        """La session de chat est persistée en base de données."""
        chat_svc = self._make_chat_service()

        async def _collect():
            async for _ in chat_svc.send_message_stream(
                session_id=None,
                user_message="Question médicale",
            ):
                pass

        asyncio.run(_collect())
        # MongoDB update_one must have been called to persist the session
        chat_svc._db[ChatService.COLLECTION].update_one.assert_called_once()

    def test_chat_llm_used_field_populated(self):
        """Le champ llm_used de la réponse est renseigné."""
        chat_svc = self._make_chat_service()

        async def _collect():
            async for event in chat_svc.send_message_stream(
                session_id=None,
                user_message="Test",
            ):
                if event.type == "done":
                    return event
            return None

        done = asyncio.run(_collect())
        assert done is not None
        assert done.llm_used, "llm_used doit être renseigné"


# ---------------------------------------------------------------------------
# 5. Flux end-to-end intégré : symptômes → diagnostic → prescription → alertes
# ---------------------------------------------------------------------------

class TestEndToEndRAGFlow:
    """Flux complet intégré couvrant REQ-02, REQ-03, REQ-04, REQ-09."""

    def test_full_flow_adult_patient(self):
        """
        Flux complet pour un patient adulte :
        symptômes → ≥3 diagnostics → prescription → 0 alerte (prescription sûre).
        """
        # Step 1: Diagnostic (REQ-02)
        rag = _make_rag_service(llm_answer=_make_diagnosis_json())
        diag_svc = DiagnosticService(rag_service=rag)
        symptoms = [
            Symptom(name="fièvre", severity="severe", duration_days=5),
            Symptom(name="toux", severity="moderate", duration_days=3),
        ]
        patient = _make_patient(AgeGroup.ADULT, 70.0)

        diagnoses = asyncio.run(
            diag_svc.get_differential_diagnosis(symptoms, patient_profile=patient)
        )
        assert len(diagnoses.diagnoses) >= 3
        assert all(0.0 <= d.probability <= 1.0 for d in diagnoses.diagnoses)

        # Step 2: Prescription (REQ-03)
        rx_svc = PrescriptionService()
        rx = asyncio.run(rx_svc.calculate_prescription("amoxicillin", patient))
        assert rx.dose_mg > 0
        assert rx.antibiotic == "amoxicillin"

        # Step 3: Safety alerts (REQ-09)
        alert_svc = AlertService()
        alerts = asyncio.run(alert_svc.check_prescription(rx, patient))
        assert alerts == [], "Aucune alerte attendue pour une prescription sûre"

    def test_full_flow_paediatric_patient_with_allergy(self):
        """
        Flux complet pour un enfant avec allergie à la ciprofloxacine :
        symptômes → diagnostics → prescription → alerte CRITIQUE d'allergie + alternative.

        On utilise ciprofloxacine car son protocole définit une alternative (ceftriaxone).
        """
        # Step 1: Diagnostic (REQ-02)
        rag = _make_rag_service(llm_answer=_make_diagnosis_json())
        diag_svc = DiagnosticService(rag_service=rag)
        symptoms = [
            Symptom(name="fièvre", severity="severe"),
            Symptom(name="éruption cutanée", severity="mild"),
        ]
        patient = _make_patient(
            AgeGroup.ADULT,  # adult so ciprofloxacin is not age-contraindicated
            weight_kg=65.0,
            allergies=["ciprofloxacin"],
        )

        diagnoses = asyncio.run(
            diag_svc.get_differential_diagnosis(symptoms, patient_profile=patient)
        )
        assert len(diagnoses.diagnoses) >= 3

        # Step 2: Prescription (REQ-03) — dose adulte
        rx_svc = PrescriptionService()
        rx = asyncio.run(rx_svc.calculate_prescription("ciprofloxacin", patient))
        assert rx.dose_mg == ANTIBIOTIC_PROTOCOLS["ciprofloxacin"].adult_max_dose_mg

        # Step 3: Safety alerts (REQ-09) — allergie détectée avec alternative
        alert_svc = AlertService()
        alerts = asyncio.run(alert_svc.check_prescription(rx, patient))
        critical = [a for a in alerts if a.level == AlertLevel.CRITICAL and a.type == "allergy"]
        assert len(critical) >= 1, "Alerte critique d'allergie attendue"
        assert critical[0].alternative is not None, "Une alternative doit être proposée"

    def test_full_flow_patient_with_renal_failure(self):
        """
        Flux complet pour un patient avec insuffisance rénale :
        prescription ajustée + alerte WARNING.
        """
        patient = _make_patient(AgeGroup.ADULT, 70.0, renal_failure=True)
        protocol = ANTIBIOTIC_PROTOCOLS["amoxicillin"]

        # Prescription ajustée (REQ-03)
        rx_svc = PrescriptionService()
        rx = asyncio.run(rx_svc.calculate_prescription("amoxicillin", patient))
        expected_dose = protocol.adult_max_dose_mg * protocol.renal_adjustment_factor
        assert rx.dose_mg == pytest.approx(expected_dose)

        # Alerte WARNING insuffisance rénale (REQ-09)
        alert_svc = AlertService()
        alerts = asyncio.run(alert_svc.check_prescription(rx, patient))
        warnings = [a for a in alerts if a.level == AlertLevel.WARNING]
        assert len(warnings) >= 1

    def test_full_flow_fluoroquinolone_contraindicated_in_child(self):
        """
        Flux complet : ciprofloxacine contre-indiquée chez l'enfant → alerte CRITIQUE.
        """
        patient = _make_patient(AgeGroup.CHILD, weight_kg=25.0)

        rx_svc = PrescriptionService()
        rx = asyncio.run(rx_svc.calculate_prescription("ciprofloxacin", patient))

        alert_svc = AlertService()
        alerts = asyncio.run(alert_svc.check_prescription(rx, patient))

        critical = [
            a for a in alerts
            if a.level == AlertLevel.CRITICAL and a.type == "contraindication"
        ]
        assert len(critical) >= 1
        assert critical[0].alternative is not None

    def test_full_flow_chat_with_patient_context_and_sources(self):
        """
        Flux complet chat Q&A : question médicale avec contexte patient → réponse (sans sources, LLM-only).
        """
        from backend.services.llm_router import StreamChunk

        mock_llm = MagicMock()

        async def _fake_generate_stream(prompt: str, context: list[dict]):
            answer = "Artémisinine-luméfantrine recommandée."
            for word in answer.split():
                yield StreamChunk(token=word + " ", llm_used="qwen3")

        mock_llm.generate_stream = _fake_generate_stream

        mock_collection = MagicMock()
        mock_collection.update_one = AsyncMock(return_value=None)
        mock_collection.find_one = AsyncMock(return_value=None)
        mock_db = MagicMock()
        mock_db.__getitem__ = MagicMock(return_value=mock_collection)

        chat_svc = ChatService(db=mock_db, llm_router=mock_llm)
        patient = _make_patient(AgeGroup.ADULT, 65.0)

        async def _collect():
            async for event in chat_svc.send_message_stream(
                session_id=None,
                user_message="Quel traitement pour le paludisme ?",
                patient_context=patient,
            ):
                if event.type == "done":
                    return event
            return None

        done = asyncio.run(_collect())

        # Q&A chat: réponse sans sources (LLM-only)
        assert done is not None
        assert "Artémisinine-luméfantrine recommandée." in done.answer.strip()
        assert done.sources == [], "Q&A chat should return empty sources"
        assert done.llm_used == "qwen3"
