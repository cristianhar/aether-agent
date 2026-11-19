"""
Esquemas consolidados de herramientas para el Agente AETHER.
Arquitectura modular dividida por dominios funcionales.
"""

from typing import Any, Dict, List

from tools.schemas.filesystem import FILESYSTEM_TOOLS
from tools.schemas.execution import EXECUTION_TOOLS
from tools.schemas.intelligence import INTELLIGENCE_TOOLS
from tools.schemas.agentic import AGENTIC_TOOLS
from tools.schemas.network import NETWORK_TOOLS

TOOLS_SCHEMA: List[Dict[str, Any]] = (
    FILESYSTEM_TOOLS
    + EXECUTION_TOOLS
    + INTELLIGENCE_TOOLS
    + AGENTIC_TOOLS
    + NETWORK_TOOLS
)

__all__ = [
    "TOOLS_SCHEMA",
    "FILESYSTEM_TOOLS",
    "EXECUTION_TOOLS",
    "INTELLIGENCE_TOOLS",
    "AGENTIC_TOOLS",
    "NETWORK_TOOLS",
]
