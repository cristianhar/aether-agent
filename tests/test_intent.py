"""
tests/test_intent.py - Pruebas unitarias para el clasificador de intención de AETHER.
"""

from agent.intent import classify_intent, IntentType


def test_classify_conversational_spanish():
    assert classify_intent("hola") == IntentType.CONVERSATIONAL
    assert classify_intent("¡Hola!") == IntentType.CONVERSATIONAL
    assert classify_intent("Buenos días") == IntentType.CONVERSATIONAL
    assert classify_intent("Buenas tardes Aether") == IntentType.CONVERSATIONAL
    assert classify_intent("¿Cómo estás?") == IntentType.CONVERSATIONAL
    assert classify_intent("Que tal amigo") == IntentType.CONVERSATIONAL
    assert classify_intent("muchas gracias") == IntentType.CONVERSATIONAL
    assert classify_intent("perfecto, gracias") == IntentType.CONVERSATIONAL
    assert classify_intent("adiós") == IntentType.CONVERSATIONAL


def test_classify_conversational_english():
    assert classify_intent("hi") == IntentType.CONVERSATIONAL
    assert classify_intent("Hello!") == IntentType.CONVERSATIONAL
    assert classify_intent("Good morning") == IntentType.CONVERSATIONAL
    assert classify_intent("how are you?") == IntentType.CONVERSATIONAL
    assert classify_intent("thanks a lot") == IntentType.CONVERSATIONAL
    assert classify_intent("got it") == IntentType.CONVERSATIONAL
    assert classify_intent("bye") == IntentType.CONVERSATIONAL


def test_classify_code_task_spanish():
    assert classify_intent("Crea un archivo main.py") == IntentType.CODE_TASK
    assert classify_intent("Edita la función suma en math_utils.py") == IntentType.CODE_TASK
    assert classify_intent("Ejecuta pytest en tests/") == IntentType.CODE_TASK
    assert classify_intent("Arregla el bug en el login") == IntentType.CODE_TASK
    assert classify_intent("Refactoriza el orquestador") == IntentType.CODE_TASK
    assert classify_intent("Haz git commit con los cambios") == IntentType.CODE_TASK
    assert classify_intent("Revisa @agent/orchestrator.py") == IntentType.CODE_TASK


def test_classify_code_task_english():
    assert classify_intent("create a test file") == IntentType.CODE_TASK
    assert classify_intent("edit server.py and fix the timeout") == IntentType.CODE_TASK
    assert classify_intent("run the unit tests") == IntentType.CODE_TASK
    assert classify_intent("delete obsolete cache file") == IntentType.CODE_TASK
    assert classify_intent("check git status") == IntentType.CODE_TASK


def test_classify_questions():
    assert classify_intent("¿Qué es una API REST y cómo funciona?") == IntentType.QUESTION
    assert classify_intent("Explícame la diferencia entre async y sync") == IntentType.QUESTION
    assert classify_intent("What is dependency injection?") == IntentType.QUESTION
    assert classify_intent("Hola peudes decirme que hace el @artifacts.py") == IntentType.QUESTION
    assert classify_intent("¿Cómo funciona el módulo @agent/memory.py?") == IntentType.QUESTION
    assert classify_intent("Explícame qué hace @tools/git_tools.py") == IntentType.QUESTION
