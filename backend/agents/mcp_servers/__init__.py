"""MCP specialist servers package.

Each server inherits from :class:`BaseMCPServer` and exposes MCP primitives
(Tools, Resources, Prompts) via JSON-RPC 2.0 over HTTP+SSE.
"""

from .base_server import BaseMCPServer
from .epidemiology_server import EpidemiologyMCPServer
from .lab_server import LabMCPServer
from .symptomatology_server import SymptomatologyMCPServer
from .treatment_server import TreatmentMCPServer

__all__ = ["BaseMCPServer", "EpidemiologyMCPServer", "LabMCPServer", "SymptomatologyMCPServer", "TreatmentMCPServer"]
