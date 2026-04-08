"""Synthesis_Agent — fusionne les résultats des agents spécialistes en un DiagnosticResult.

REQ 2.7 : garantit un minimum de 3 diagnostics différentiels.
REQ 2.9 : exclut les agents sans chunks grounded et enregistre l'omission.
REQ 5.1–5.8 : citations de preuves, score de confiance pondéré, contributions agents.
REQ 8.1–8.3 : gestion du fallback LLM et disclaimer.
"""
from __future__ import annotations

import logging

from backend.models.consultation import (
    AgentContribution,
    DifferentialDiagnosis,
    EvidenceCitation,
)
from backend.services.diagnostic_service import DiagnosticResult
from backend.services.mcp_host import AgentResult

logger = logging.getLogger(__name__)


class Synthesis_Agent:
    """Fusionne les résultats des quatre agents spécialistes en un DiagnosticResult.

    Étapes :
    1. Filtrer les agents sans chunks grounded (chunks == []) — REQ 2.9.
    2. Fusionner les listes ``partial_differential`` des agents retenus.
    3. Dédupliquer par nom de condition (insensible à la casse), en conservant
       la probabilité la plus élevée.
    4. Trier par probabilité décroissante.
    5. Compléter jusqu'à 3 diagnostics si nécessaire — REQ 2.7.
    6. Retourner un :class:`DiagnosticResult`.
    """

    # ------------------------------------------------------------------
    # New helper methods (REQ 5.7, 5.8, 11.6, 8.3)
    # ------------------------------------------------------------------

    def _compute_weighted_confidence(
        self, active_results: list[AgentResult]
    ) -> float:
        """Weighted average: sum(score_i × len(chunks_i)) / sum(len(chunks_i)).

        Returns 0.0 when there are no active agents (total_weight == 0).
        """
        total_weight = sum(len(r.chunks) for r in active_results)
        if total_weight == 0:
            return 0.0
        weighted_sum = sum(
            r.confidence_score * len(r.chunks) for r in active_results
        )
        return weighted_sum / total_weight

    def _build_evidence_citations(
        self,
        active_results: list[AgentResult],
        diagnoses: list[DifferentialDiagnosis],
    ) -> list[EvidenceCitation]:
        """Associate chunks from active agents to the diagnoses they contributed.

        For each diagnosis, find which active agents contributed it (condition
        match, case-insensitive) and turn their chunks into EvidenceCitation
        objects.  Placeholder diagnostics (those added to reach minimum 3) get
        no citations.
        """
        citations: list[EvidenceCitation] = []

        for diag in diagnoses:
            diag_key = diag.condition.strip().lower()
            for result in active_results:
                # Check if this agent contributed this diagnosis
                agent_conditions = {
                    d.condition.strip().lower()
                    for d in result.partial_differential
                }
                if diag_key not in agent_conditions:
                    continue
                for chunk in result.chunks:
                    citations.append(
                        EvidenceCitation(
                            document_id=chunk.get("document_id", ""),
                            title=chunk.get("title", ""),
                            source=chunk.get("source", ""),
                            excerpt=chunk.get("excerpt", ""),
                            page=chunk.get("page"),
                        )
                    )
        return citations

    def _build_agent_contributions(
        self, agent_results: list[AgentResult]
    ) -> list[AgentContribution]:
        """Build AgentContribution list from ALL agent results (not just active)."""
        contributions: list[AgentContribution] = []
        for result in agent_results:
            contributions.append(
                AgentContribution(
                    agent_name=result.agent_name,
                    confidence_score=result.confidence_score,
                    partial_differential=[
                        d.model_dump() for d in result.partial_differential
                    ],
                )
            )
        return contributions

    # ------------------------------------------------------------------
    # Main synthesis
    # ------------------------------------------------------------------

    def synthesize(
        self,
        agent_results: list[AgentResult],
        locale: str = "fr-TG",
    ) -> DiagnosticResult:
        """Synthétise les résultats des agents en un DiagnosticResult.

        Args:
            agent_results: Résultats produits par les agents spécialistes.
            locale: Locale BCP-47 (ex. ``"fr-TG"``).

        Returns:
            :class:`DiagnosticResult` avec au moins 3 diagnostics différentiels.
        """
        # --- REQ 2.9 : séparer agents avec et sans chunks grounded ---
        active_results: list[AgentResult] = []
        omitted_agents: list[str] = []

        for result in agent_results:
            if result.chunks:
                active_results.append(result)
            else:
                omitted_agents.append(result.agent_name)
                logger.warning(
                    "Agent %r omis de la synthèse : aucun chunk grounded",
                    result.agent_name,
                )

        # --- Fusionner les partial_differential des agents actifs ---
        merged: dict[str, DifferentialDiagnosis] = {}
        for result in active_results:
            for diag in result.partial_differential:
                key = diag.condition.strip().lower()
                existing = merged.get(key)
                if existing is None or diag.probability > existing.probability:
                    merged[key] = diag

        # --- Trier par probabilité décroissante ---
        diagnoses: list[DifferentialDiagnosis] = sorted(
            merged.values(),
            key=lambda d: d.probability,
            reverse=True,
        )

        # --- REQ 2.7 : garantir au moins 3 diagnostics ---
        MIN_DIAGNOSES = 3
        for i in range(len(diagnoses) + 1, MIN_DIAGNOSES + 1):
            placeholder = DifferentialDiagnosis(
                condition=f"Diagnostic différentiel {i}",
                probability=0.0,
                icd_code=None,
                matching_symptoms=[],
            )
            diagnoses.append(placeholder)
            logger.info(
                "Diagnostic placeholder ajouté (confidence: low) : %r",
                placeholder.condition,
            )

        # --- Construire degraded_warning si des agents ont été omis ---
        degraded_warning: str | None = None
        if omitted_agents:
            names = ", ".join(omitted_agents)
            degraded_warning = (
                f"Agents omis de la synthèse (aucun chunk grounded) : {names}."
            )

        # --- REQ 8.1, 8.2, 8.3 : fallback_used logic ---
        any_agent_fallback = any(r.fallback_used for r in agent_results)
        all_agents_no_chunks = len(active_results) == 0
        fallback_used = all_agents_no_chunks or any_agent_fallback

        disclaimer: str | None = None
        if any_agent_fallback:
            disclaimer = (
                "Certains résultats ont été produits par le modèle de secours. "
                "Une vérification clinique approfondie est recommandée."
            )

        # --- REQ 5.7 : evidence citations ---
        evidence_citations = self._build_evidence_citations(
            active_results, diagnoses
        )

        # --- REQ 5.8 : weighted confidence score ---
        confidence_score = self._compute_weighted_confidence(active_results)

        # --- REQ 11.6 : agent contributions ---
        agent_contributions = self._build_agent_contributions(agent_results)

        return DiagnosticResult(
            diagnoses=diagnoses,
            fallback_used=fallback_used,
            degraded_warning=degraded_warning,
            locale=locale,
            disclaimer=disclaimer,
            confidence_score=confidence_score,
            evidence_citations=evidence_citations,
            agent_contributions=agent_contributions,
        )
