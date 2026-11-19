"""
Tests unitarios para la herramienta interactiva de preguntas estructuradas (ask_question):
- Ejecución con callback personalizado.
- Auto-selección de opción recomendada en entornos no interactivos / headless.
- Manejo de preguntas de selección simple y múltiple.
- Despacho a través de execute_tool del registro central.
"""

import json
from unittest.mock import patch
from rich.console import Console

from tools.agent_tools import ask_question_tool, set_ask_question_callback
from tools.registry import execute_tool
from cli.ui import prompt_interactive_question


def test_ask_question_with_callback():
    """Verifica que el callback registrado intercepte las preguntas."""
    captured = []

    def mock_callback(questions):
        captured.extend(questions)
        return [{"question": questions[0]["question"], "selected": ["PostgreSQL"]}]

    set_ask_question_callback(mock_callback)
    try:
        payload = {
            "questions": [
                {
                    "question": "¿Qué base de datos usar?",
                    "options": ["(Recommended) SQLite", "PostgreSQL"],
                    "is_multi_select": False,
                }
            ]
        }
        res_str = ask_question_tool(payload)
        data = json.loads(res_str)
        assert data["status"] == "success"
        assert data["answers"][0]["selected"] == ["PostgreSQL"]
        assert len(captured) == 1
    finally:
        set_ask_question_callback(None)


def test_ask_question_headless_auto_selects_recommended():
    """En entorno headless/CI (isatty False), selecciona automáticamente la recomendada."""
    set_ask_question_callback(None)
    mock_console = Console(record=True)

    with patch("sys.stdin.isatty", return_value=False):
        questions = [
            {
                "question": "¿Qué framework HTTP deseas emplear?",
                "options": ["Flask", "(Recommended) FastAPI", "Django"],
                "is_multi_select": False,
            }
        ]
        answers = prompt_interactive_question(questions, console_inst=mock_console)
        assert len(answers) == 1
        assert answers[0]["selected"] == ["(Recommended) FastAPI"]


def test_ask_question_interactive_user_input(monkeypatch):
    """Simula interacción del usuario eligiendo la opción 2."""
    set_ask_question_callback(None)
    mock_console = Console(record=True)

    with patch("sys.stdin.isatty", return_value=True):
        monkeypatch.setattr(mock_console, "input", lambda _: "2")
        questions = [
            {
                "question": "¿Qué arquitectura prefieres?",
                "options": ["(Recommended) Monolito Modular", "Microservicios"],
                "is_multi_select": False,
            }
        ]
        answers = prompt_interactive_question(questions, console_inst=mock_console)
        assert answers[0]["selected"] == ["Microservicios"]


def test_ask_question_dispatch_via_registry():
    """Verifica que execute_tool despache ask_question correctamente."""
    set_ask_question_callback(lambda qs: [{"question": "Q1", "selected": ["Op1"]}])
    try:
        out = execute_tool("ask_question", {"questions": [{"question": "Q1", "options": ["Op1"]}]})
        parsed = json.loads(out)
        assert parsed["status"] == "success"
        assert parsed["answers"][0]["selected"] == ["Op1"]
    finally:
        set_ask_question_callback(None)
