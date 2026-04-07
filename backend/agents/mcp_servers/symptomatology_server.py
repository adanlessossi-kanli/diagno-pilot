"""
Serveur MCP Symptomatologie — Diagno-Pilot

Serveur MCP spécialiste pour le domaine symptomatologique. Déployé comme service Docker
indépendant communiquant via JSON-RPC 2.0 sur HTTP+SSE.

Primitives exposées :
- Tool : `query_symptomatology` — Analyse symptomatologique selon les guidelines cliniques
- Resource : `guidelines://documents` — Collection de guidelines cliniques
- Prompt : `symptomatology_query` — Template de requête symptomatologique

Configuration :
- MONGODB_URI : URI de connexion MongoDB
- LLM_PRIMARY_URL / LLM_FALLBACK_URL : URLs des LLMs
- EMBED_MODEL : Modèle d'embedding
- SERVER_PORT : Port d'écoute (défaut : 8002)
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
SERVER_PORT = int(os.environ.get("SERVER_PORT", "8002"))
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
# SymptomatologyMCPServer
# ---------------------------------------------------------------------------


class SymptomatologyMCPServer(BaseMCPServer):
    """MCP server for symptomatological analysis.

    Inherits from :class:`BaseMCPServer` and registers:
    - Tool ``query_symptomatology``
    - Resource ``guidelines://documents``
    - Prompt ``symptomatology_query``

    Each instance creates its own MongoDB connection, EmbeddingModel,
    IndexManager and LlamaIndexPipeline for full process isolation.
    """

    def __init__(self, port: int = SERVER_PORT) -> None:
        super().__init__(server_name="symptomatology", port=port)

        # --- Isolated infrastructure ---
        client: AsyncIOMotorClient = AsyncIOMotorClient(settings.MONGODB_URI)
        db = client.get_default_database()

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
            name="query_symptomatology",
            description=(
                "Analyse symptomatologique selon les guidelines cliniques. "
                "Retourne les pathologies correspondantes, "
                "un score de confiance et un diagnostic différentiel partiel."
            ),
            input_schema=TOOL_INPUT_SCHEMA,
            handler=self._handle_query_symptomatology,
        )

        self.register_resource(
            uri="guidelines://documents",
            name="Clinical Guidelines",
            description=(
                "Collection de guidelines cliniques indexées : "
                "recommandations diagnostiques, arbres décisionnels, "
                "critères diagnostiques, protocoles de prise en charge "
                "et guidelines OMS pour les pathologies tropicales."
            ),
            mime_type="application/json",
        )

        self.register_prompt(
            name="symptomatology_query",
            description=(
                "Template de requête symptomatologique. Formule une sous-question "
                "ciblée pour l'analyse des guidelines cliniques en fonction "
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
        """Return a description of the clinical guidelines data available."""
        if uri == "guidelines://documents":
            return {
                "text": (
                    "Collection de guidelines cliniques pour le diagnostic médical. "
                    "Contient des recommandations diagnostiques, des arbres décisionnels, "
                    "des critères diagnostiques standardisés, des protocoles de prise en charge, "
                    "et des guidelines OMS pour les pathologies tropicales. Les documents sont "
                    "indexés par pathologie et type de guideline pour une recherche vectorielle optimisée."
                ),
            }
        return {"text": ""}

    # -- Tool handler --------------------------------------------------------

    async def _handle_query_symptomatology(self, arguments: dict[str, Any]) -> dict:
        """Handle the ``query_symptomatology`` tool invocation.

        Builds a symptomatological sub-question from the symptoms, queries the
        RAG pipeline with the guideline source filter and region, then
        parses the response into an AgentResult-like dict.
        """
        symptoms = arguments.get("symptoms", [])
        _patient_profile = arguments.get("patient_profile")  # noqa: F841 — reserved for future use
        _locale = arguments.get("locale", "fr-TG")  # noqa: F841 — reserved for future use
        region = arguments.get("region")

        # Build sub-question
        symptom_names = ", ".join(s["name"] for s in symptoms if isinstance(s, dict) and "name" in s)
        region_clause = f" dans la région {region}" if region else ""
        sub_question = (
            f"Quelles pathologies correspondent aux symptômes suivants selon les "
            f"guidelines cliniques{region_clause} : {symptom_names} ?"
        )

        # Query RAG pipeline
        try:
            rag_response = await self._pipeline.query(
                question=sub_question,
                context=None,
                top_k=5,
                region=region,
                source_filter=SOURCE_FILTER,
            )
        except Exception as exc:
            logger.error("RAG pipeline error: %s", exc)
            return {
                "agent_name": "symptomatology",
                "sub_question": sub_question,
                "chunks": [],
                "confidence_score": 0.0,
                "partial_differential": [],
                "fallback_used": False,
            }

        # Extract chunks from sources
        chunks = [
            {
                "document_id": src.document_id,
                "title": src.title,
                "source": src.source,
                "excerpt": src.excerpt or "",
                "page": src.page,
            }
            for src in rag_response.sources
        ]

        confidence_score = rag_response.confidence_score if rag_response.confidence_score is not None else 0.0
        fallback_used = rag_response.fallback_used

        # Parse partial_differential from LLM answer
        partial_differential = _parse_partial_differential(rag_response.answer)

        return {
            "agent_name": "symptomatology",
            "sub_question": sub_question,
            "chunks": chunks,
            "confidence_score": confidence_score,
            "partial_differential": partial_differential,
            "fallback_used": fallback_used,
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

def create_server(port: int | None = None) -> SymptomatologyMCPServer:
    """Factory function to create a SymptomatologyMCPServer instance."""
    return SymptomatologyMCPServer(port=port or SERVER_PORT)


if __name__ == "__main__":
    server = create_server()
    server.run()
