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
        consecutive_tool_counts={},
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
        consecutive_tool_counts={},
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
        consecutive_tool_counts={},
    )
    assert tripped is True
    assert "SyntaxError pendiente de corrección" in msg
    assert "minijuego.py" in msg


def test_circuit_breaker_blocks_consecutive_identical_failed_tool():
    """Bloquea cualquier herramienta que repita exactamente los mismos argumentos tras haber fallado."""
    orch = AgentOrchestrator()

    key = 'read_file:{"end_line": 200, "path": "inexistente.py", "start_line": 1}'
    consecutive_counts = {key: 1}

    tripped, msg = orch._check_circuit_breaker(
        tool_name="read_file",
        args={"path": "inexistente.py", "start_line": 1, "end_line": 200},
        last_failed_command=None,
        files_modified_since_cmd_fail=False,
        known_syntax_error_files=set(),
        consecutive_tool_counts=consecutive_counts,
    )
    assert tripped is True
    assert "CIRCUIT BREAKER" in msg
    assert "repetir la misma acción fallida" in msg


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
