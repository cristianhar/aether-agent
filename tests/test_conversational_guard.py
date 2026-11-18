import pytest
from unittest.mock import MagicMock, patch
from agent.orchestrator import AgentOrchestrator
from tools.agent_tools import update_plan
from tools.file_tools import write_file, edit_file


def test_conversational_query_does_not_trigger_tests_or_tools():
    """Verifica que una consulta no relacionada con código concluya en 1 solo turno sin invocar herramientas."""
    tool_calls_recorded = []

    def mock_on_tool_call(tool_name, args):
        tool_calls_recorded.append((tool_name, args))

    orchestrator = AgentOrchestrator(
        on_tool_call=mock_on_tool_call
    )

    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "message": {
            "content": "Claro, aquí tienes un ejercicio de lógica sobre 3 personas...",
            "tool_calls": []
        }
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client.post", return_value=mock_resp):
        ans = orchestrator.run_turn("Dame un ejercicio de logica")

    assert "ejercicio de lógica" in ans
    assert len(tool_calls_recorded) == 0, f"Expected 0 tools called, but got: {tool_calls_recorded}"


def test_update_plan_works_without_plan_steps():
    """Verifica que update_plan(is_completed=True) no lance TypeError si plan_steps es None."""
    res = update_plan(is_completed=True)
    assert "completado" in res.lower()


def test_file_tools_intercept_angle_bracket_placeholders():
    """Verifica que write_file y edit_file rechacen nombres con <...> de forma amigable sin lanzar [Errno 22]."""
    w_res = write_file("test_<modulo>.py", "print(1)")
    assert "marcador de posición" in w_res

    e_res = edit_file("test_<modulo>.py", target="1", replacement="2")
    assert "marcador de posición" in e_res
