import tempfile
from pathlib import Path
from tools.agent_tools import update_plan, request_approval, set_approval_callback, get_project_instructions


def test_update_plan():
    steps = ["Auditar repositorio", "Implementar patch engine", "Verificar tests"]
    criteria = ["Todos los tests pasan en verde", "Cero regresiones"]

    result = update_plan(plan_steps=steps, current_step=2, acceptance_criteria=criteria)

    assert "1. ✅ Auditar repositorio" in result
    assert "2. ⏳ [EN PROGRESO] Implementar patch engine" in result
    assert "3. ⬜ Verificar tests" in result
    assert "Todos los tests pasan en verde" in result


def test_request_approval_callback():
    approved = False

    def mock_cb(desc: str, risk: str) -> bool:
        return approved

    set_approval_callback(mock_cb)

    res_denied = request_approval("Borrar base de datos", risk_level="critical")
    assert "⛔ Autorización DENEGADA" in res_denied

    approved = True
    res_allowed = request_approval("Reiniciar servicio", risk_level="medium")
    assert "✅ Autorización CONCEDIDA" in res_allowed

    set_approval_callback(None)


def test_get_project_instructions():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        agents_md = ws / "AGENTS.md"
        agents_md.write_text("# Reglas del proyecto\nUsar tipado estricto en Python.", encoding="utf-8")

        res = get_project_instructions(path=str(ws))
        assert "Reglas de Proyecto: AGENTS.md" in res
        assert "Usar tipado estricto en Python" in res
        assert "<project_instructions" in res


def test_execute_tools_parallel():
    from tools.registry import execute_tools_parallel
    calls = [
        ("read_file", {"path": "main.py", "start_line": 1, "end_line": 5}),
        ("list_directory", {"path": ".", "max_depth": 1}),
    ]
    results = execute_tools_parallel(calls, max_workers=2)
    assert len(results) == 2
    assert "main.py" in results[0]
    assert "main.py" in results[1]


def test_delegate_research_read_only_restriction(monkeypatch):
    from tools.subagent import delegate_research
    called_mode = None

    class MockOrchestrator:
        def __init__(self, **kwargs):
            self.hooks = kwargs.get("hooks")

        def run_turn(self, prompt):
            nonlocal called_mode
            called_mode = getattr(self.hooks, "mode", None)
            return "Hallazgo: la función se encuentra en core.py:10"

    monkeypatch.setattr("agent.orchestrator.AgentOrchestrator", MockOrchestrator)
    res = delegate_research("¿Dónde está la función?")
    assert "INFORME DEL SUBAGENTE RESEARCHER" in res
    assert "core.py:10" in res
    assert called_mode == "ask"


def test_delegate_test_dispatch(monkeypatch):
    from tools.subagent import delegate_test

    class MockOrchestrator:
        def __init__(self, **kwargs):
            pass

        def run_turn(self, prompt):
            return "Todos los tests pasaron exitosamente (Exit code 0)"

    monkeypatch.setattr("agent.orchestrator.AgentOrchestrator", MockOrchestrator)
    res = delegate_test("pytest", "tests/test_agent_tools.py")
    assert "INFORME DEL SUBAGENTE TESTER" in res
    assert "Exit code 0" in res
