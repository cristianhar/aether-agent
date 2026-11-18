import pytest
from agent.hooks import HookManager

def test_hooks_mode_switching():
    hooks = HookManager(mode="agent")
    assert hooks.mode == "agent"

    hooks.set_mode("ask")
    assert hooks.mode == "ask"

    hooks.set_mode("plan")
    assert hooks.mode == "plan"

    hooks.set_mode("review")
    assert hooks.mode == "review"

    # Ignora modos no válidos
    hooks.set_mode("invalid_mode")
    assert hooks.mode == "review"

def test_hooks_pre_tool_use_ask_mode_blocks_modifications():
    hooks = HookManager(mode="ask")

    for tool in ["write_file", "edit_file", "delete_file", "move_file", "run_command", "create_checkpoint"]:
        allowed, reason = hooks.pre_tool_use(tool, {"path": "test.txt"})
        assert not allowed
        assert "ASK" in reason

    # Herramientas de lectura permitidas
    for tool in ["read_file", "list_directory", "get_file_outline", "get_repo_map", "search_web"]:
        allowed, reason = hooks.pre_tool_use(tool, {"path": "test.txt"})
        assert allowed
        assert reason == "OK"

def test_hooks_pre_tool_use_plan_mode_blocks_code_modification():
    hooks = HookManager(mode="plan")

    for tool in ["edit_file", "delete_file", "move_file", "run_command", "create_checkpoint"]:
        allowed, reason = hooks.pre_tool_use(tool, {"path": "main.py"})
        assert not allowed
        assert "PLAN" in reason

    # write_file en código fuente está bloqueado
    allowed, reason = hooks.pre_tool_use("write_file", {"path": "src/app.py"})
    assert not allowed
    assert "PLAN" in reason

    # Inspección y lectura sí permitidos
    for tool in ["read_file", "list_directory", "get_file_outline", "get_repo_map", "get_plan", "update_plan"]:
        allowed, reason = hooks.pre_tool_use(tool, {})
        assert allowed
        assert reason == "OK"


def test_hooks_post_tool_use_enriches_eoferror():
    hooks = HookManager(mode="agent")
    raw_error = "Código de salida: 1\nTraceback: EOFError: EOF when reading a line"
    enriched = hooks.post_tool_use("run_command", {"command": "python test.py"}, raw_error)
    assert "[HOOK POST-TOOL]" in enriched
    assert "EOFError" in enriched


def test_hooks_dynamic_pre_hook_registration():
    hooks = HookManager(mode="agent")

    def custom_pre(tool_name, args):
        if tool_name == "delete_file" and "protected" in args.get("path", ""):
            return False, "No puedes borrar archivos protegidos"
        return True, "OK"

    hooks.register_pre_hook(custom_pre)

    allowed, reason = hooks.pre_tool_use("delete_file", {"path": "safe.txt"})
    assert allowed is True

    allowed, reason = hooks.pre_tool_use("delete_file", {"path": "protected_secret.key"})
    assert allowed is False
    assert "protegidos" in reason


def test_hooks_dynamic_post_hook_registration():
    hooks = HookManager(mode="agent")

    def custom_post(tool_name, args, result):
        if tool_name == "write_file":
            return result + "\n[TELEMETRIA_CUSTOM]: Archivo auditado"
        return result

    hooks.register_post_hook(custom_post)

    out = hooks.post_tool_use("write_file", {"path": "main.py"}, "Éxito")
    assert "[TELEMETRIA_CUSTOM]" in out


def test_hooks_post_tool_use_test_success_guidance():
    hooks = HookManager(mode="agent")
    out = hooks.post_tool_use("run_command", {"command": "pytest"}, "Código de salida: 0\n2 passed in 0.05s")
    assert "TODAS LAS PRUEBAS PASARON EXITOSAMENTE" in out
    assert "is_completed=True" in out


def test_hooks_post_tool_use_plan_completed_guidance():
    hooks = HookManager(mode="agent")
    out = hooks.post_tool_use("update_plan", {}, "🎉 COMPLETADO (Todos los hitos finalizados)")
    assert "Plan completado y verificado en su totalidad" in out


def test_hooks_blocks_autonomous_git_add_commit():
    hooks = HookManager(mode="agent")
    allowed, reason = hooks.pre_tool_use("run_command", {"command": "git add -A"})
    assert allowed is False
    assert "Comando de Git bloqueado" in reason

    allowed, reason = hooks.pre_tool_use("run_command", {"command": "git commit -m 'test'"})
    assert allowed is False
    assert "Comando de Git bloqueado" in reason


def test_hooks_blocks_gitignore_tampering():
    hooks = HookManager(mode="agent")
    allowed, reason = hooks.pre_tool_use("edit_file", {"path": ".gitignore", "target": ".aether\n", "replacement": ""})
    assert allowed is False
    assert ".gitignore bloqueada" in reason


def test_review_mode_diff_generation(tmp_path):
    from agent.orchestrator import AgentOrchestrator
    orchestrator = AgentOrchestrator()

    # 1. Diff write_file (nuevo archivo)
    f = tmp_path / "hello.py"
    diff_new = orchestrator._generate_tool_diff("write_file", {"path": str(f), "content": "def hello(): pass\n"})
    assert "+++ b/" in diff_new
    assert "+def hello(): pass" in diff_new

    # 2. Diff edit_file (archivo existente)
    f.write_text("def hello():\n    return 1\n", encoding="utf-8")
    diff_edit = orchestrator._generate_tool_diff("edit_file", {"path": str(f), "target": "return 1", "replacement": "return 2"})
    assert "-    return 1" in diff_edit
    assert "+    return 2" in diff_edit

    # 3. Diff delete_file
    diff_del = orchestrator._generate_tool_diff("delete_file", {"path": str(f)})
    assert "--- a/" in diff_del
    assert "-def hello():" in diff_del


def test_review_mode_confirmation_flow(tmp_path):
    from agent.orchestrator import AgentOrchestrator
    f = tmp_path / "app.py"
    f.write_text("initial = 1\n", encoding="utf-8")

    # Caso A: Desarrollador rechaza los cambios
    calls_made = []
    def reject_callback(msg: str) -> bool:
        calls_made.append(msg)
        return False

    orchestrator = AgentOrchestrator(confirm_callback=reject_callback)
    orchestrator.hooks.set_mode("review")

    diff_text = orchestrator._generate_tool_diff("write_file", {"path": str(f), "content": "initial = 99\n"})
    assert "+initial = 99" in diff_text
    should_run = orchestrator.confirm_callback(diff_text)
    assert should_run is False
    assert len(calls_made) == 1
    assert f.read_text(encoding="utf-8") == "initial = 1\n"

    # Caso B: Desarrollador aprueba los cambios
    def accept_callback(msg: str) -> bool:
        return True

    orchestrator_acc = AgentOrchestrator(confirm_callback=accept_callback)
    orchestrator_acc.hooks.set_mode("review")
    should_run = orchestrator_acc.confirm_callback(diff_text)
    assert should_run is True


def test_cli_tab_completion_commands():
    import main
    assert hasattr(main, "COMMANDS_META")
    assert hasattr(main, "COMPLETION_WORDS")
    for cmd in ["/help", "/plan", "/test", "/diff", "/commit", "/mode", "/model", "/compact", "/undo", "/checkpoint", "/exit"]:
        assert cmd in main.COMMANDS_META
        assert cmd in main.COMPLETION_WORDS
    assert "/mode review" in main.COMPLETION_WORDS


