from agent.state import AgentState, CancellationToken
from agent.orchestrator import AgentOrchestrator


def test_agent_state_enums():
    states = [
        AgentState.IDLE,
        AgentState.PLANNING,
        AgentState.RUNNING,
        AgentState.WAITING_APPROVAL,
        AgentState.VERIFYING,
        AgentState.COMPLETED,
        AgentState.FAILED,
        AgentState.CANCELLED,
    ]
    assert len(states) == 8
    assert AgentState.RUNNING.value == "RUNNING"


def test_cancellation_token_behavior():
    token = CancellationToken()
    assert token.is_cancelled is False

    token.cancel("Detención solicitada por usuario")
    assert token.is_cancelled is True
    assert token.reason == "Detención solicitada por usuario"

    token.reset()
    assert token.is_cancelled is False
    assert token.reason is None


def test_orchestrator_cancellation():
    orchestrator = AgentOrchestrator()
    token = CancellationToken()
    token.cancel("Abortar tarea de inmediato")

    result = orchestrator.run_turn("Escribe un script de prueba", cancellation_token=token)
    assert "Abortar tarea de inmediato" in result
    assert orchestrator.state == AgentState.CANCELLED
