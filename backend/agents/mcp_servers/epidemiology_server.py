"""
Serveur MCP Épidémiologie — Diagno-Pilot

Serveur MCP spécialiste pour le domaine épidémiologique. Déployé comme service Docker
indépendant communiquant via JSON-RPC 2.0 sur HTTP+SSE.

Primitives exposées :
- Tool : `query_epidemiology` — Analyse épidémiologique des symptômes par région
- Resource : `epidemiology://documents` — Collection de données épidémiologiques
- Prompt : `epidemiology_query` — Template de requête épidémiologique

Configuration :
- MONGODB_URI : URI de connexion MongoDB
- LLM_PRIMARY_URL / LLM_FALLBACK_URL : URLs des LLMs
- EMBED_MODEL : Modèle d'embedding
- SERVER_PORT : Port d'écoute (défaut : 8001)
- LLAMAINDEX_SIMILARITY_THRESHOLD : Seuil de similarité (défaut : 0.75)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient

from backend.agents.mcp_servers.base_server import BaseMCPServer
from backend.core.config import settings
from backend.services.embedding_model import EmbeddingModel
from backend.services.index_manager import IndexManager
from backend.services.llm_router import LLMRouter
from backend.services.llamaindex_pipeline import LlamaIndexPipeline

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SERVER_PORT = int(os.environ.get("SERVER_PORT", "8001"))
SOURCE_FILTER = {"metadata.document_type": "guideline"}

TOOL_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "symptoms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "severity": {"type": "string", "nullable": True},
                    "duration_days": {"type": "integer", "nullable": True},
                },
                "required": ["name"],
            },
        },
        "patient_profile": {"type": "object", "nullable": True},
        "locale": {"type": "string"},
        "region": {"type": "string", "nullable": True},
    },
    "required": ["symptoms", "locale"],
}


# ---------------------------------------------------------------------------
# EpidemiologyMCPServer
# ---------------------------------------------------------------------------


class EpidemiologyMCPServer(BaseMCPServer):
    """MCP server for epidemiological analysis.

    Inherits from :class:`BaseMCPServer` and registers:
    - Tool ``query_epidemiology``
    - Resource ``epidemiology://documents``
    - Prompt ``epidemiology_query``

    Each instance creates its own MongoDB connection, EmbeddingModel,
    IndexManager and LlamaIndexPipeline for full process isolation.
    """

    def __init__(self, port: int = SERVER_PORT) -> None:
        super().__init__(server_name="epidemiology", port=port)

        # --- Isolated infrastructure ---
        client: AsyncIOMotorClient = AsyncIOMotorClient(settings.MONGODB_URI)
        db = client.get_default_database()
        collection = db["document_chunks"]  # noqa: F841 — used by IndexManager

        self._embedder = EmbeddingModel()
        self._index_manager = IndexManager(db=db)
        self._llm_router = LLMRouter()
        self._pipeline = LlamaIndexPipeline(
            index_manager=self._index_manager,
            llm_router=self._llm_router,
            embedder=self._embedder,
        )

        # --- Register MCP primitives ---
        self.register_tool(
            name="query_epidemiology",
            description=(
                "Analyse épidémiologique des symptômes par région. "
                "Retourne les données épidémiologiques pertinentes, "
                "un score de confiance et un diagnostic différentiel partiel."
            ),
            input_schema=TOOL_INPUT_SCHEMA,
            handler=self._handle_query_epidemiology,
        )

        self.register_resource(
            uri="epidemiology://documents",
            name="Epidemiological Documents",
            description=(
                "Collection de données épidémiologiques indexées : "
                "prévalence régionale, incidence saisonnière, facteurs de risque, "
                "données OMS et bulletins épidémiologiques pour le Togo et le Bénin."
            ),
            mime_type="application/json",
        )

        self.register_prompt(
            name="epidemiology_query",
            description=(
                "Template de requête épidémiologique. Formule une sous-question "
                "ciblée pour l'analyse des données épidémiologiques en fonction "
                "des symptômes, du profil patient, de la locale et de la région."
            ),
            arguments=[
                {"name": "symptoms", "description": "Liste des symptômes du patient", "required": True},
                {"name": "patient_profile", "description": "Profil du patient (âge, poids, antécédents)", "required": False},
                {"name": "locale", "description": "Locale BCP-47 (ex. fr-TG, fr-BJ, en)", "required": True},
                {"name": "region", "description": "Code région ISO 3166-1 alpha-2 (ex. TG, BJ)", "required": False},
            ],
        )

    # -- Resource reading ----------------------------------------------------

    async def read_resource(self, uri: str) -> dict:
        """Return a description of the epidemiological data available."""
        if uri == "epidemiology://documents":
            return {
                "text": (
                    "Collection de données épidémiologiques pour le diagnostic médical. "
                    "Contient des documents sur la prévalence régionale des maladies, "
                    "l'incidence saisonnière, les facteurs de risque environnementaux, "
                    "les bulletins épidémiologiques de l'OMS, et les données spécifiques "
                    "au Togo (TG) et au Bénin (BJ). Les documents sont indexés par région "
                    "et type de maladie pour une recherche vectorielle optimisée."
                ),
            }
        return {"text": ""}

    # -- Tool handler --------------------------------------------------------

    async def _handle_query_epidemiology(self, arguments: dict[str, Any]) -> dict:
        """Handle the ``query_epidemiology`` tool invocation.

        Retrieval-only: embeds the sub-question, retrieves relevant chunks
        via vector search + BM25, and returns them without calling the LLM.
        The synthesis agent on the backend handles LLM-based diagnosis.
        """
        symptoms = arguments.get("symptoms", [])
        _patient_profile = arguments.get("patient_profile")  # noqa: F841
        _locale = arguments.get("locale", "fr-TG")  # noqa: F841
        region = arguments.get("region")

        symptom_names = ", ".join(s["name"] for s in symptoms if isinstance(s, dict) and "name" in s)
        region_clause = f" dans la région {region}" if region else ""
        sub_question = (
            f"Quelles sont les données épidémiologiques pertinentes pour les symptômes "
            f"suivants{region_clause} : {symptom_names} ?"
        )

        # Retrieval-only: embed query then search chunks (no LLM call)
        try:
            query_vector = await self._embedder.encode(sub_question)
            raw_chunks = await self._index_manager.retrieve(
                query_vector, sub_question, top_k=5, region=region,
                source_filter=SOURCE_FILTER,
            )
        except Exception as exc:
            logger.error("Retrieval error: %s", exc)
            return {
                "agent_name": "epidemiology",
                "sub_question": sub_question,
                "chunks": [],
                "confidence_score": 0.0,
                "partial_differential": [],
                "fallback_used": False,
            }

        chunks = [
            {
                "document_id": str(c.get("document_id", "")),
                "title": c.get("metadata", {}).get("title", c.get("metadata", {}).get("source", "")),
                "source": c.get("metadata", {}).get("source", ""),
                "excerpt": c.get("content", "")[:500],
                "page": c.get("metadata", {}).get("page"),
            }
            for c in raw_chunks
        ]

        cosine_scores = [float(c["score"]) for c in raw_chunks if c.get("score") is not None]
        confidence_score = (sum(cosine_scores) / len(cosine_scores)) if cosine_scores else 0.0

        return {
            "agent_name": "epidemiology",
            "sub_question": sub_question,
            "chunks": chunks,
            "confidence_score": confidence_score,
            "partial_differential": [],
            "fallback_used": False,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_partial_differential(answer: str) -> list[dict]:
    """Parse the LLM answer as a JSON array of diagnoses.

    If parsing fails, returns an empty list.
    """
    try:
        parsed = json.loads(answer)
        if isinstance(parsed, list):
            return [
                {
                    "condition": d.get("condition", ""),
                    "probability": float(d.get("probability", 0.0)),
                    "icd_code": d.get("icd_code"),
                    "matching_symptoms": d.get("matching_symptoms", []),
                }
                for d in parsed
                if isinstance(d, dict)
            ]
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return []


# ---------------------------------------------------------------------------
# Module entrypoint
# ---------------------------------------------------------------------------

def create_server(port: int | None = None) -> EpidemiologyMCPServer:
    """Factory function to create an EpidemiologyMCPServer instance."""
    return EpidemiologyMCPServer(port=port or SERVER_PORT)


if __name__ == "__main__":
    server = create_server()
    server.run()
