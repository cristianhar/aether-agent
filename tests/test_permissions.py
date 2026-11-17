import tempfile
from pathlib import Path
from agent.permissions import PermissionEngine, PermissionRequest, PermissionDecision
from tools.base import ToolCategory, PermissionLevel


def test_permission_engine_jail_boundaries():
    with tempfile.TemporaryDirectory() as tmp_workspace:
        ws = Path(tmp_workspace).resolve()
        engine = PermissionEngine(workspace_root=ws, enforce_workspace_jail=True)

        inside_file = ws / "module" / "app.py"
        outside_file = ws.parent / "secret.txt"

        assert engine.is_path_within_boundaries(inside_file) is True
        assert engine.is_path_within_boundaries(outside_file) is False

        # Solicitud de escritura dentro del workspace debe permitirse
        req_inside = PermissionRequest(
            tool_name="write_file",
            category=ToolCategory.FILESYSTEM,
            level=PermissionLevel.WORKSPACE_WRITE,
            target_path=str(inside_file),
        )
        dec, _ = engine.evaluate(req_inside)
        assert dec == PermissionDecision.ALLOW

        # Solicitud de escritura fuera del workspace debe ser denegada
        req_outside = PermissionRequest(
            tool_name="write_file",
            category=ToolCategory.FILESYSTEM,
            level=PermissionLevel.WORKSPACE_WRITE,
            target_path=str(outside_file),
        )
        dec, reason = engine.evaluate(req_outside)
        assert dec == PermissionDecision.DENY
        assert "Violación de límites" in reason


def test_permission_engine_dangerous_commands():
    engine = PermissionEngine()

    safe_cmd = "pytest -v tests/test_app.py"
    is_safe, _ = engine.is_command_safe(safe_cmd)
    assert is_safe is True

    catastrophic_cmds = [
        "format C:",
        "del /F /Q C:\\Windows",
        "rmdir /s /q c:\\",
        "rm -rf /",
        "shutdown -s -t 0",
    ]

    for cmd in catastrophic_cmds:
        is_safe, reason = engine.is_command_safe(cmd)
        assert is_safe is False, f"Comando '{cmd}' debería considerarse peligroso"
        assert "patrón destructivo" in reason.lower()


def test_permission_engine_approval_callback():
    approved = False

    def mock_approval(req: PermissionRequest) -> bool:
        return approved

    engine = PermissionEngine(approval_callback=mock_approval)

    req = PermissionRequest(
        tool_name="delete_database",
        category=ToolCategory.EXECUTION,
        level=PermissionLevel.ADMIN_DESTRUCTIVE,
    )

    # Inicialmente approved es False -> DENY
    dec, _ = engine.evaluate(req)
    assert dec == PermissionDecision.DENY

    # Cuando el usuario aprueba -> ALLOW
    approved = True
    dec, _ = engine.evaluate(req)
    assert dec == PermissionDecision.ALLOW
