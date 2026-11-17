"""
Máquina de estados formal y gestión de cancelación para el Agente AETHER.
Garantiza transiciones predecibles y control de ciclo de vida en tiempo de ejecución.
"""

from enum import Enum
import threading
from typing import Optional


class AgentState(str, Enum):
    IDLE = "IDLE"
    PLANNING = "PLANNING"
    RUNNING = "RUNNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CancellationToken:
    """Token de cancelación thread-safe para abortar generación o ejecución de herramientas."""

    def __init__(self):
        self._event = threading.Event()
        self._reason: Optional[str] = None

    def cancel(self, reason: str = "Operación cancelada por el usuario."):
        self._reason = reason
        self._event.set()

    def reset(self):
        self._reason = None
        self._event.clear()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> Optional[str]:
        return self._reason
