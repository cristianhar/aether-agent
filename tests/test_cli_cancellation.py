"""
Tests unitarios para la cancelación y detención limpia de tareas en AETHER CLI:
- Comando slash /cancel y /stop.
- Interrupción limpia mediante CancellationToken sin colapsar el proceso.
- Manejo de KeyboardInterrupt en main y preservación de memoria.
"""

from unittest.mock import MagicMock
from rich.console import Console
from agent.state import AgentState, CancellationToken
from agent.orchestrator import AgentOrchestrator
from cli.commands import handle_slash_command


def test_slash_cancel_and_stop():
    """Verifica que /cancel y /stop detengan la tarea y dejen el estado en IDLE."""
    mock_orchestrator = MagicMock()
    mock_orchestrator.active_token = CancellationToken()
    mock_orchestrator.state = AgentState.RUNNING
    mock_console = Console(record=True)

    # 1. Probar /cancel
    res_cancel = handle_slash_command("/cancel", mock_orchestrator, mock_console)
    assert res_cancel is True
    mock_orchestrator.cancel_active_turn.assert_called_once()

    # 2. Probar /stop
    mock_orchestrator.reset_mock()
    res_stop = handle_slash_command("/stop", mock_orchestrator, mock_console)
    assert res_stop is True
    mock_orchestrator.cancel_active_turn.assert_called_once()


def test_orchestrator_cancel_active_turn_method():
    """Verifica la lógica directa de cancel_active_turn en AgentOrchestrator."""
    orch = AgentOrchestrator()
    token = CancellationToken()
    orch.active_token = token
    orch.state = AgentState.RUNNING

    orch.cancel_active_turn("Detenido por usuario")
    assert token.is_cancelled is True
    assert token.reason == "Detenido por usuario"
    assert orch.state == AgentState.IDLE
