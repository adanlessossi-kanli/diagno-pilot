"""Epidemiology specialist agent — REQ 2.3.

Reads a JSON request from stdin, queries RAGService filtered to
document_type=epidemiology, writes a JSON response to stdout.
"""
import asyncio

from backend.agents._base_agent import run_agent

SOURCE_FILTER = {"metadata.document_type": "epidemiology"}

if __name__ == "__main__":
    asyncio.run(run_agent(SOURCE_FILTER))
