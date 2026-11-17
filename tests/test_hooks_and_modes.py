import pytest
from agent.hooks import HookManager

def test_hooks_mode_switching():
    hooks = HookManager(mode="agent")
    assert hooks.mode == "agent"

    hooks.set_mode("ask")
    assert hooks.mode == "ask"

    hooks.set_mode("plan")
    assert hooks.mode == "plan"

    # Ignora modos no válidos
    hooks.set_mode("invalid_mode")
    assert hooks.mode == "plan"

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

def test_hooks_post_tool_use_enriches_eoferror():
    hooks = HookManager(mode="agent")
    raw_error = "Código de salida: 1\nTraceback: EOFError: EOF when reading a line"
    enriched = hooks.post_tool_use("run_command", {"command": "python test.py"}, raw_error)
    assert "[HOOK POST-TOOL]" in enriched
    assert "EOFError" in enriched
