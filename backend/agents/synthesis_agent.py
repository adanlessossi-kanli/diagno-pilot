"""Synthesis_Agent — fusionne les résultats des agents spécialistes en un DiagnosticResult.

REQ 2.7 : garantit un minimum de 3 diagnostics différentiels.
REQ 2.9 : exclut les agents sans chunks grounded et enregistre l'omission.
"""
from __future__ import annotations

import logging

from backend.models.consultation import DifferentialDiagnosis
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

        fallback_used = len(active_results) == 0

        return DiagnosticResult(
            diagnoses=diagnoses,
            fallback_used=fallback_used,
            degraded_warning=degraded_warning,
            locale=locale,
        )
