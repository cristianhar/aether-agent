"""
Tests unitarios para la arquitectura modular de CLI:
- cli.ui (renderizado, tablas, banners, confirmaciones, meta de comandos)
- cli.commands (despacho de slash commands)
- main.py (re-exportación y compatibilidad hacia atrás)
"""

from unittest.mock import MagicMock
from rich.console import Console

import main
import cli
from cli.ui import (
    COMMANDS_META,
    COMPLETION_WORDS,
    confirm_prompt,
    handle_thought,
    handle_tool_call,
    handle_tool_result,
    render_banner,
    render_response,
)
from cli.commands import handle_slash_command


def test_main_reexports_backward_compatibility():
    """Verifica que main re-exporte todos los símbolos requeridos para retrocompatibilidad."""
    assert hasattr(main, "COMMANDS_META")
    assert hasattr(main, "COMPLETION_WORDS")
    assert hasattr(main, "render_banner")
    assert hasattr(main, "render_thought")
    assert hasattr(main, "render_response")
    assert hasattr(main, "handle_thought")
    assert hasattr(main, "handle_tool_call")
    assert hasattr(main, "handle_tool_result")
    assert hasattr(main, "confirm_prompt")
    assert hasattr(main, "handle_slash_command")
    assert hasattr(main, "console")

    for cmd in ["/help", "/plan", "/test", "/diff", "/commit", "/mode", "/model", "/compact", "/undo", "/checkpoint", "/exit"]:
        assert cmd in main.COMMANDS_META
        assert cmd in main.COMPLETION_WORDS


def test_cli_package_exports():
    """Verifica que el paquete cli exporte la interfaz unificada."""
    assert hasattr(cli, "render_banner")
    assert hasattr(cli, "handle_slash_command")
    assert hasattr(cli, "COMMANDS_META")
    assert hasattr(cli, "COMPLETION_WORDS")


def test_cli_ui_rendering_smoke():
    """Prueba que los componentes visuales de cli.ui ejecuten sin generar excepciones."""
    # Banner
    render_banner("qwen2.5-coder:7b", ollama_ok=True)
    render_banner("qwen2.5-coder:7b", ollama_ok=False)

    # Pensamientos
    handle_thought("")
    handle_thought("Analizando el problema")
    handle_thought("Línea 1\nLínea 2\nLínea 3\nLínea 4\nLínea 5\nLínea 6\nLínea 7")
    handle_thought("{'name': 'tool', 'arguments': {}}")
    handle_thought("```python\nprint(1)\n```")

    # Llamadas a herramientas
    handle_tool_call("write_file", {"path": "test.py", "content": "print(1)\n"})
    handle_tool_call("edit_file", {"path": "test.py", "target": "old"})
    handle_tool_call("read_file", {"path": "test.py", "start_line": 1, "end_line": 10})
    handle_tool_call("run_command", {"command": "dir"})
    handle_tool_call("run_tests", {"test_target": "tests/test_cli.py"})
    handle_tool_call("update_plan", {"current_step": "1"})
    handle_tool_call("conclude_turn", {"summary": "Done"})
    handle_tool_call("other_tool", {"arg1": "value", "arg2": "long " * 20})

    # Resultados de herramientas
    handle_tool_result("write_file", "Éxito al escribir archivo")
    handle_tool_result("write_file", "Error al escribir")
    handle_tool_result("edit_file", "Éxito al modificar archivo")
    handle_tool_result("edit_file", "Error al editar")
    handle_tool_result("read_file", "linea 1\nlinea 2")
    handle_tool_result("update_plan", "Plan activo actualizado")
    handle_tool_result("run_tests", "Código de salida: 0\n=== 5 passed ===")
    handle_tool_result("run_tests", "Código de salida: 1\nFAILED test_x")
    handle_tool_result("general_tool", "⛔ [CIRCUIT BREAKER: REGLA 0]: Bucle detectado\n• Tu SIGUIENTE ACCIÓN OBLIGATORIA es leer")
    handle_tool_result("general_tool", "Error: no existe")
    handle_tool_result("general_tool", "Resultado corto")
    handle_tool_result("general_tool", "\n".join([f"line {i}" for i in range(12)]))

    # Respuestas
    render_response("### Respuesta\nTodo funcionando correctamente.")


def test_cli_confirm_prompt(monkeypatch):
    """Prueba la lógica interactiva de confirm_prompt en cli.ui."""
    # Respuesta positiva
    monkeypatch.setattr(main.console, "input", lambda _: "s")
    assert confirm_prompt("¿Deseas continuar?") is True

    # Respuesta negativa
    monkeypatch.setattr(main.console, "input", lambda _: "n")
    assert confirm_prompt("¿Deseas continuar?") is False

    # Confirmación con diff formateado
    diff_q = "Modificación de archivo\n--- a/test.py\n+++ b/test.py\n@@ -1,1 +1,1 @@\n-old\n+new\n¿Autorizar?"
    monkeypatch.setattr(main.console, "input", lambda _: "yes")
    assert confirm_prompt(diff_q) is True


def test_handle_slash_command_dispatch():
    """Prueba el enrutamiento de todos los comandos slash sin interacción de red."""
    mock_orchestrator = MagicMock()
    mock_orchestrator.model = "qwen2.5-coder:7b"
    mock_orchestrator.session_id = "test-session-123"
    mock_orchestrator.state.value = "IDLE"
    mock_orchestrator.hooks.mode = "agent"
    mock_orchestrator.memory.estimate_tokens.return_value = 150
    mock_orchestrator.memory.get_messages.return_value = [{"role": "user", "content": "hola"}]

    mock_console = Console(record=True)

    # 1. No es un comando slash -> Retorna None
    assert handle_slash_command("hola agente", mock_orchestrator, mock_console) is None

    # 2. Comandos de salida -> Retorna False
    assert handle_slash_command("/exit", mock_orchestrator, mock_console) is False
    assert handle_slash_command("/quit", mock_orchestrator, mock_console) is False

    # 3. Comandos estándar informativos / control -> Retorna True
    assert handle_slash_command("/help", mock_orchestrator, mock_console) is True
    assert handle_slash_command("/status", mock_orchestrator, mock_console) is True
    assert handle_slash_command("/map", mock_orchestrator, mock_console) is True
    assert handle_slash_command("/diff", mock_orchestrator, mock_console) is True
    assert handle_slash_command("/telemetry", mock_orchestrator, mock_console) is True
    assert handle_slash_command("/sessions", mock_orchestrator, mock_console) is True
    assert handle_slash_command("/clear", mock_orchestrator, mock_console) is True
    assert handle_slash_command("/compact", mock_orchestrator, mock_console) is True
    assert handle_slash_command("/voice", mock_orchestrator, mock_console) is True
    assert handle_slash_command("/cd", mock_orchestrator, mock_console) is True

    # 4. Comandos de modo
    for mode in ["agent", "ask", "plan", "review"]:
        assert handle_slash_command(f"/mode {mode}", mock_orchestrator, mock_console) is True
        mock_orchestrator.set_mode.assert_called_with(mode)

    assert handle_slash_command("/mode invalid_mode", mock_orchestrator, mock_console) is True

    # 5. Comandos de modelo
    assert handle_slash_command("/model codellama:7b", mock_orchestrator, mock_console) is True
    assert mock_orchestrator.model == "codellama:7b"
    assert handle_slash_command("/model", mock_orchestrator, mock_console) is True

    # 6. Comando no reconocido que empiece por '/' -> Retorna True
    assert handle_slash_command("/comando_inexistente", mock_orchestrator, mock_console) is True
