"""
Serveur MCP Laboratoire — Diagno-Pilot

Serveur MCP spécialiste pour le domaine laboratoire. Déployé comme service Docker
indépendant communiquant via JSON-RPC 2.0 sur HTTP+SSE.

Primitives exposées :
- Tool : `query_lab` — Analyse des examens biologiques et résultats de laboratoire
- Resource : `laboratory://documents` — Collection de données de laboratoire
- Prompt : `lab_query` — Template de requête laboratoire

Configuration :
- MONGODB_URI : URI de connexion MongoDB
- LLM_PRIMARY_URL / LLM_FALLBACK_URL : URLs des LLMs
- EMBED_MODEL : Modèle d'embedding
- SERVER_PORT : Port d'écoute (défaut : 8003)
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
SERVER_PORT = int(os.environ.get("SERVER_PORT", "8003"))
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
# LabMCPServer
# ---------------------------------------------------------------------------


class LabMCPServer(BaseMCPServer):
    """MCP server for laboratory analysis.

    Inherits from :class:`BaseMCPServer` and registers:
    - Tool ``query_lab``
    - Resource ``laboratory://documents``
    - Prompt ``lab_query``

    Each instance creates its own MongoDB connection, EmbeddingModel,
    IndexManager and LlamaIndexPipeline for full process isolation.
    """

    def __init__(self, port: int = SERVER_PORT) -> None:
        super().__init__(server_name="lab", port=port)

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
            name="query_lab",
            description=(
                "Analyse des examens biologiques et résultats de laboratoire. "
                "Retourne les données de laboratoire pertinentes, "
                "un score de confiance et un diagnostic différentiel partiel."
            ),
            input_schema=TOOL_INPUT_SCHEMA,
            handler=self._handle_query_lab,
        )

        self.register_resource(
            uri="laboratory://documents",
            name="Laboratory Documents",
            description=(
                "Collection de données de laboratoire indexées : "
                "examens biologiques, résultats d'analyses, valeurs de référence, "
                "panels diagnostiques et protocoles de laboratoire."
            ),
            mime_type="application/json",
        )

        self.register_prompt(
            name="lab_query",
            description=(
                "Template de requête laboratoire. Formule une sous-question "
                "ciblée pour l'analyse des examens biologiques et résultats "
                "de laboratoire en fonction des symptômes, du profil patient, "
                "de la locale et de la région."
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
        """Return a description of the laboratory data available."""
        if uri == "laboratory://documents":
            return {
                "text": (
                    "Collection de données de laboratoire pour le diagnostic médical. "
                    "Contient des documents sur les examens biologiques, les résultats "
                    "d'analyses de laboratoire, les valeurs de référence, les panels "
                    "diagnostiques et les protocoles de laboratoire. Les documents sont "
                    "indexés par type d'examen et pathologie pour une recherche "
                    "vectorielle optimisée."
                ),
            }
        return {"text": ""}

    # -- Tool handler --------------------------------------------------------

    async def _handle_query_lab(self, arguments: dict[str, Any]) -> dict:
        """Retrieval-only: embed query, retrieve chunks, return without LLM call."""
        symptoms = arguments.get("symptoms", [])
        region = arguments.get("region")

        symptom_names = ", ".join(s["name"] for s in symptoms if isinstance(s, dict) and "name" in s)
        region_clause = f" dans la région {region}" if region else ""
        sub_question = (
            f"Quels examens biologiques et résultats de laboratoire sont indiqués "
            f"pour les symptômes suivants{region_clause} : {symptom_names} ?"
        )

        try:
            query_vector = await self._embedder.encode(sub_question)
            raw_chunks = await self._index_manager.retrieve(
                query_vector, sub_question, top_k=5, region=region,
                source_filter=SOURCE_FILTER,
            )
        except Exception as exc:
            logger.error("Retrieval error: %s", exc)
            return {
                "agent_name": "lab", "sub_question": sub_question,
                "chunks": [], "confidence_score": 0.0, "partial_differential": [], "fallback_used": False,
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
            "agent_name": "lab", "sub_question": sub_question,
            "chunks": chunks, "confidence_score": confidence_score,
            "partial_differential": [], "fallback_used": False,
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

def create_server(port: int | None = None) -> LabMCPServer:
    """Factory function to create a LabMCPServer instance."""
    return LabMCPServer(port=port or SERVER_PORT)


if __name__ == "__main__":
    server = create_server()
    server.run()
