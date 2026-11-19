from unittest.mock import MagicMock

from agent.i18n import (
    get_current_language,
    get_localized_system_prompt,
    set_current_language,
)
from agent.prompts import get_system_prompt
from cli.commands import handle_slash_command


def test_i18n_language_switching():
    # Establecer inglés
    assert set_current_language("en") is True
    assert get_current_language() == "en"

    en_prompt = get_system_prompt("agent")
    assert "You are AETHER" in en_prompt
    assert "Autonomous Software Engineering Agent" in en_prompt

    en_plan = get_system_prompt("plan")
    assert "You are AETHER in PLAN Mode" in en_plan

    # Establecer español
    assert set_current_language("es") is True
    assert get_current_language() == "es"

    es_prompt = get_system_prompt("agent")
    assert "Eres AETHER" in es_prompt
    assert "Agente Programador Autónomo" in es_prompt


def test_i18n_unsupported_language():
    assert set_current_language("fr") is False
    assert get_current_language() in ("es", "en")


def test_i18n_cli_slash_command():
    mock_orch = MagicMock()
    mock_console = MagicMock()

    # /language
    assert handle_slash_command("/language", mock_orch, console=mock_console) is True

    # /language en
    assert handle_slash_command("/language en", mock_orch, console=mock_console) is True
    assert get_current_language() == "en"

    # /language es
    assert handle_slash_command("/language es", mock_orch, console=mock_console) is True
    assert get_current_language() == "es"
