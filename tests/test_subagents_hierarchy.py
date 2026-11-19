import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.subagents import (
    SubagentManager,
    get_global_subagent_manager,
)
from cli.commands import handle_slash_command
from tools.agent_tools import (
    define_subagent_tool,
    invoke_subagent_tool,
    manage_subagents_tool,
    send_message_tool,
)


def test_default_templates_and_define_subagent():
    mgr = SubagentManager()
    assert "research" in mgr.templates
    assert "self" in mgr.templates
    assert "tester" in mgr.templates
    assert mgr.templates["research"].enable_write_tools is False

    res = mgr.define_subagent(
        name="security-audit",
        description="Audita vulnerabilidades",
        system_prompt="Eres un auditor de seguridad.",
        enable_write_tools=False,
    )
    assert "security-audit" in mgr.templates
    assert "✅ Subagente tipo 'security-audit' registrado" in res


def test_invoke_subagent_isolated_turn():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        mgr = SubagentManager(workspace_root=ws)

        class MockOrchestrator:
            def __init__(self, **kwargs):
                self.mode = kwargs.get("mode")
                self.calls = []

            def run_turn(self, prompt):
                self.calls.append(prompt)
                return f"Respuesta a: {prompt} (Modo: {self.mode})"

        with patch("agent.orchestrator.AgentOrchestrator", MockOrchestrator):
            output = mgr.invoke_subagent(
                type_name="research",
                role="Inspector de Código",
                prompt="Analiza si existe SQL injection",
                workspace="inherit",
            )
            assert "Subagente Activado: [Inspector de Código]" in output
            assert "Modo: `ASK`" in output
            assert len(mgr.instances) == 1

            cid = list(mgr.instances.keys())[0]
            inst = mgr.instances[cid]
            assert inst.role == "Inspector de Código"
            assert inst.status == "idle"
            assert len(inst.inbox) == 1
            assert len(inst.outbox) == 1
            assert "SQL injection" in inst.inbox[0].content


def test_subagent_branch_workspace_and_kill_cleanup():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        mgr = SubagentManager(workspace_root=ws)

        class MockOrchestrator:
            def __init__(self, **kwargs):
                pass

            def run_turn(self, prompt):
                return "Ejecución completada en branch."

        with patch("agent.orchestrator.AgentOrchestrator", MockOrchestrator):
            mgr.invoke_subagent(
                type_name="self",
                role="Desarrollador Aislado",
                prompt="Crea un prototipo en rama",
                workspace="branch",
            )
            cid = list(mgr.instances.keys())[0]
            inst = mgr.instances[cid]
            assert inst.workspace_mode == "branch"
            assert inst.workspace_dir.exists()

            # Matar subagente y comprobar limpieza del sandbox
            kill_res = mgr.manage_subagents(action="kill", conversation_ids=[cid])
            assert "Subagentes terminados" in kill_res
            assert inst.is_killed is True
            assert inst.status == "terminated"
            assert not inst.workspace_dir.exists()


def test_mailbox_message_roundtrip():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        mgr = SubagentManager(workspace_root=ws)

        class MockOrchestrator:
            def __init__(self, **kwargs):
                self.history = []

            def run_turn(self, prompt):
                self.history.append(prompt)
                return f"Procesado turno {len(self.history)}: {prompt}"

        with patch("agent.orchestrator.AgentOrchestrator", MockOrchestrator):
            mgr.invoke_subagent(
                type_name="self",
                role="Asistente Interactivo",
                prompt="Paso 1: Inicializa",
            )
            cid = list(mgr.instances.keys())[0]

            # Enviar mensaje 2 por el buzón
            reply2 = mgr.send_message(recipient=cid, message="Paso 2: Genera reporte")
            assert "Respuesta del Subagente" in reply2
            assert "Procesado turno 2: Paso 2: Genera reporte" in reply2

            # Estado del buzón
            status_report = mgr.manage_subagents(action="status", conversation_ids=[cid])
            assert "Historial de Mensajes (2 entradas, 2 salidas)" in status_report

            # Listado
            list_report = mgr.manage_subagents(action="list")
            assert cid in list_report


def test_send_message_to_killed_subagent_error():
    mgr = SubagentManager()
    mgr.instances["sub-test"] = MagicMock(is_killed=True, status="terminated")
    res = mgr.send_message("sub-test", "Hola")
    assert "❌ Error: El subagente `sub-test` ha sido terminado" in res

    missing = mgr.send_message("sub-inexistente", "Hola")
    assert "❌ Error: No se encontró ningún subagente" in missing


def test_agent_tools_subagent_wrappers():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        get_global_subagent_manager(workspace_root=ws, force_reload=True)

        class MockOrchestrator:
            def __init__(self, **kwargs):
                pass

            def run_turn(self, prompt):
                return "Mock turn output"

        with patch("agent.orchestrator.AgentOrchestrator", MockOrchestrator):
            # define_subagent_tool
            def_res = define_subagent_tool(
                name="tester-tool",
                description="Auditor",
                system_prompt="Test prompt",
            )
            assert "tester-tool" in def_res

            # invoke_subagent_tool
            inv_res = invoke_subagent_tool(
                type_name="tester-tool",
                role="Tool Tester",
                prompt="Corre tests",
            )
            assert "Subagente Activado" in inv_res

            # manage_subagents_tool list
            list_res = manage_subagents_tool("list")
            assert "Tool Tester" in list_res


def test_cli_slash_command_subagents():
    mock_orch = MagicMock()
    mock_console = MagicMock()

    assert handle_slash_command("/subagents", mock_orch, console=mock_console) is True
    assert handle_slash_command("/subagents kill sub-1234", mock_orch, console=mock_console) is True
    assert handle_slash_command("/subagents status sub-1234", mock_orch, console=mock_console) is True
