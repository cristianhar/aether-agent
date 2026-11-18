"""
Pruebas unitarias para el Circuit Breaker Anti-Bucle y Diagnósticos Inteligentes de Terminal.
Verifica que AETHER no entre en bucles de re-ejecución sin modificaciones de código
y que detecte SyntaxErrors y subcarpetas desalineadas.
"""

from pathlib import Path
import tempfile
from agent.orchestrator import AgentOrchestrator
from tools.file_tools import write_file, edit_file
from tools.shell_tools import _generate_shell_diagnostics


def test_circuit_breaker_blocks_repeated_failing_command():
    """El circuit breaker debe bloquear un run_command idéntico si falló y no se modificaron archivos."""
    orch = AgentOrchestrator()

    # Intento 1: comando falla previamente
    last_failed = "python test_fail.py"
    files_modified = False

    tripped, msg = orch._check_circuit_breaker(
        tool_name="run_command",
        args={"command": "python test_fail.py"},
        last_failed_command=last_failed,
        files_modified_since_cmd_fail=files_modified,
        known_syntax_error_files=set(),
        last_failed_tool_key=None,
    )
    assert tripped is True
    assert "CIRCUIT BREAKER" in msg
    assert "ACCIÓN OBLIGATORIA" in msg
    assert "edit_file" in msg


def test_circuit_breaker_allows_command_after_file_modification():
    """El circuit breaker debe permitir volver a ejecutar si se modificó un archivo de código."""
    orch = AgentOrchestrator()

    last_failed = "python test_fail.py"
    files_modified = True  # Se llamó exitosamente a edit_file

    tripped, _ = orch._check_circuit_breaker(
        tool_name="run_command",
        args={"command": "python test_fail.py"},
        last_failed_command=last_failed,
        files_modified_since_cmd_fail=files_modified,
        known_syntax_error_files=set(),
        last_failed_tool_key=None,
    )
    assert tripped is False


def test_circuit_breaker_blocks_script_with_unresolved_syntax_error():
    """El circuit breaker debe bloquear ejecutar un script si tiene un SyntaxError pendiente."""
    orch = AgentOrchestrator()

    tripped, msg = orch._check_circuit_breaker(
        tool_name="run_command",
        args={"command": "python minijuego.py"},
        last_failed_command=None,
        files_modified_since_cmd_fail=False,
        known_syntax_error_files={"minijuego.py"},
        last_failed_tool_key=None,
    )
    assert tripped is True
    assert "SyntaxError pendiente de corrección" in msg
    assert "minijuego.py" in msg


def test_circuit_breaker_blocks_consecutive_identical_failed_tool():
    """Bloquea cualquier herramienta que repita inmediatamente los mismos argumentos tras haber fallado."""
    orch = AgentOrchestrator()

    key = 'read_file:{"end_line": 200, "path": "inexistente.py", "start_line": 1}'

    tripped, msg = orch._check_circuit_breaker(
        tool_name="read_file",
        args={"path": "inexistente.py", "start_line": 1, "end_line": 200},
        last_failed_command=None,
        files_modified_since_cmd_fail=False,
        known_syntax_error_files=set(),
        last_failed_tool_key=key,
    )
    assert tripped is True
    assert "CIRCUIT BREAKER" in msg
    assert "repetir la misma acción fallida" in msg


def test_edit_file_rejects_traceback_as_target():
    """edit_file debe rechazar si el modelo pasa un mensaje de error/traceback en vez de código."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = Path(tmp_dir) / "game.py"
        test_file.write_text("print('hola')\n", encoding="utf-8")

        traceback_target = "Traceback (most recent call last):\n  File 'game.py', line 1\nEOFError: EOF when reading a line"
        res = edit_file(str(test_file), target=traceback_target, replacement="pass")
        assert "Error de parámetro 'target'" in res
        assert "Has pasado la salida o mensaje de error de la terminal" in res
        assert "read_file" in res


def test_circuit_breaker_prevents_ping_pong_loop():
    """El circuit breaker no debe desbloquear un comando que falló solo porque otro comando diferente tuvo éxito."""
    orch = AgentOrchestrator()

    # Supongamos que 'python game.py' falló previamente
    failed_cmds = {"python game.py"}
    files_modified = False

    # El modelo intenta llamar 'python game.py' de nuevo (incluso si py_compile pasó)
    tripped, msg = orch._check_circuit_breaker(
        tool_name="run_command",
        args={"command": "python game.py"},
        failed_commands=failed_cmds,
        files_modified_since_cmd_fail=files_modified,
        known_syntax_error_files=set(),
        last_failed_tool_key=None,
    )
    assert tripped is True
    assert "CIRCUIT BREAKER" in msg
    assert "concluye el turno e informa al usuario" in msg


def test_shell_diagnostics_detects_operation_cancelled():
    """Verifica que el auto-diagnóstico detecte cuando una herramienta CLI se cancela sin TTY."""
    ws = Path.cwd()
    diag = _generate_shell_diagnostics(
        command="npm create vite@latest . -- --template vanilla",
        work_dir=ws,
        exit_code=0,
        stdout="create-vite v9.3.4\n— Operation cancelled",
        stderr=""
    )
    assert diag is not None
    assert "OPERACIÓN CANCELADA" in diag
    assert "create-vite" in diag


def test_shell_diagnostics_detects_subproject_package_json():
    """Verifica que el auto-diagnóstico detecte package.json en una subcarpeta cuando npm falla en root."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        sub = ws / "my-vite-app"
        sub.mkdir()
        (sub / "package.json").write_text('{"name": "my-vite-app"}', encoding="utf-8")

        stderr_msg = "npm error enoent ENOENT: no such file or directory, open 'package.json'"
        diag = _generate_shell_diagnostics(
            command="npm install",
            work_dir=ws,
            exit_code=1,
            stdout="",
            stderr=stderr_msg
        )
        assert diag is not None
        assert "DIAGNÓSTICO AUTOMÁTICO DE TERMINAL" in diag
        assert "my-vite-app" in diag
        assert "cwd=" in diag


def test_shell_diagnostics_flags_syntax_error():
    """Verifica que el auto-diagnóstico identifique SyntaxError en consola."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        diag = _generate_shell_diagnostics(
            command="python minijuego.py",
            work_dir=ws,
            exit_code=1,
            stdout="",
            stderr="File 'minijuego.py', line 23\n    print(\"texto)\nSyntaxError: unterminated string literal"
        )
        assert diag is not None
        assert "DIAGNÓSTICO DE SINTAXIS" in diag
        assert "PROHIBIDO volver a ejecutar" in diag


def test_auto_linter_directive_in_write_file():
    """write_file debe incluir la directiva obligatoria de edit_file si hay un error de sintaxis."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        test_file = Path(tmp_dir) / "bad.py"
        res = write_file(str(test_file), "def broken():\n    print('incompleto)\n")
        assert "Auto-Linter" in res
        assert "ACCIÓN OBLIGATORIA" in res
        assert "edit_file" in res
        assert "NUNCA llames a 'run_command'" in res


def test_persistent_assertion_error_regex():
    """Verifica que la detección regex de AssertionError capture la línea exacta de discrepancia."""
    import re
    result_mock = "FAIL: test_foo\nAssertionError: 1.581138830084 != 1.4142135623730951 within 7 places"
    match = re.search(r"(AssertionError:[^\n\r]+)", result_mock)
    assert match is not None
    assert "1.581138830084 != 1.4142135623730951" in match.group(1)


def test_shell_diagnostics_detects_assertion_error_discrepancy():
    """Verifica que shell diagnostics extraiga los valores real y esperado e instruya la corrección."""
    from tools.shell_tools import _generate_shell_diagnostics
    with tempfile.TemporaryDirectory() as tmp_dir:
        diag = _generate_shell_diagnostics(
            command="python -m unittest test_calculadora_stats.py",
            work_dir=Path(tmp_dir),
            exit_code=1,
            stdout="",
            stderr="AssertionError: 1.5811388300841898 != 1.41 within 2 places (0.17113883008418984 difference)"
        )
        assert diag is not None
        assert "DIAGNÓSTICO AUTOMÁTICO DE DISCREPANCIA EN TEST" in diag
        assert "1.5811388300841898" in diag
        assert "1.41" in diag
        assert "1.58" in diag
        assert "assertAlmostEqual" in diag


def test_shell_diagnostics_detects_pytest_approx_in_unittest():
    """Verifica que se alerte si se intenta mezclar pytest.approx en unittest."""
    from tools.shell_tools import _generate_shell_diagnostics
    with tempfile.TemporaryDirectory() as tmp_dir:
        diag = _generate_shell_diagnostics(
            command="python -m unittest test_calculadora_stats.py",
            work_dir=Path(tmp_dir),
            exit_code=1,
            stdout="",
            stderr="TypeError: unsupported operand type(s) for -: 'float' and '_pytest.python_api.ApproxScalar'"
        )
        assert diag is not None
        assert "INCOMPATIBILIDAD DE FRAMEWORK DE TEST" in diag
        assert "pytest.approx" in diag


def test_package_install_unblocks_failed_command():
    """Verifica que un comando exitoso de pip/npm install limpie los comandos fallidos previos."""
    from agent.orchestrator import AgentOrchestrator
    orchestrator = AgentOrchestrator(model="dummy-model")

    blocked, _ = orchestrator._check_circuit_breaker(
        tool_name="run_command",
        args={"command": "python -m pytest"},
        failed_commands={"python -m pytest"},
        files_modified_since_cmd_fail=False
    )
    assert blocked is True

    # Si se modificaron archivos o cambió el entorno (pip install), ya no debe estar bloqueado
    unblocked, _ = orchestrator._check_circuit_breaker(
        tool_name="run_command",
        args={"command": "python -m pytest"},
        failed_commands=set(),
        files_modified_since_cmd_fail=True
    )
    assert unblocked is False


def test_circuit_breaker_blocks_blind_edit_ping_pong():
    """El circuit breaker debe bloquear llamadas consecutivas de edit_file/apply_patch a ciegas."""
    from agent.orchestrator import AgentOrchestrator
    orchestrator = AgentOrchestrator(model="dummy-model")

    blocked, msg = orchestrator._check_circuit_breaker(
        tool_name="edit_file",
        args={"path": "lru_cache.py", "target": "not found", "replacement": "bar"},
        consecutive_edit_failures=2
    )
    assert blocked is True
    assert "CIRCUIT BREAKER - EDICIÓN A CIEGAS BLOQUEADA" in msg
    assert "read_file" in msg


def test_circuit_breaker_blocks_multi_tool_ping_pong():
    """El circuit breaker debe detectar y bloquear bucles oscilantes entre 2 herramientas."""
    from agent.orchestrator import AgentOrchestrator
    orchestrator = AgentOrchestrator(model="dummy-model")

    recent_tools = ["edit_file", "run_command", "edit_file"]
    blocked, msg = orchestrator._check_circuit_breaker(
        tool_name="run_command",
        args={"command": "pytest test_foo.py"},
        recent_failed_tools=recent_tools,
        consecutive_tool_failures=3
    )
    assert blocked is True
    assert "CIRCUIT BREAKER - BUCLE ALTERNANTE DETECTADO" in msg
    assert "edit_file" in msg
    assert "run_command" in msg


def test_circuit_breaker_blocks_repeated_edits():
    """El circuit breaker debe bloquear ediciones idénticas sobre el mismo target en el mismo turno."""
    from agent.orchestrator import AgentOrchestrator
    orchestrator = AgentOrchestrator(model="dummy-model")

    executed_edits = {"app.py:def foo():"}
    blocked, msg = orchestrator._check_circuit_breaker(
        tool_name="edit_file",
        args={"path": "app.py", "target": "def foo():", "replacement": "def bar():"},
        executed_edits=executed_edits
    )
    assert blocked is True
    assert "EDICIÓN REPETIDA BLOQUEADA" in msg
