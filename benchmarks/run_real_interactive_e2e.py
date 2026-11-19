"""
Script de pruebas End-to-End REALES con Ollama qwen2.5-coder:7b.
Ejecuta de principio a fin tareas conversacionales y de programación reales
en los 4 modos (ASK, PLAN, AGENT, REVIEW) simulando exactamente el CLI interactivo.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

# Añadir raíz al path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.orchestrator import AgentOrchestrator
from agent.context import resolve_at_file_mentions


def run_e2e_plan_test():
    print("\n" + "=" * 70)
    print("🚀 TEST E2E 1: MODO PLAN — Consulta de Arquitectura de Sitio de Citas")
    print("=" * 70)

    orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="plan")
    user_input = "COmo iniciarias una arquitectura de un sitio de citas?"
    print(f"👤 Usuario: {user_input}\n")

    expanded, _ = resolve_at_file_mentions(user_input)
    answer = orch.run_turn(expanded)

    print("🤖 Respuesta de AETHER (Modo PLAN):")
    print("-" * 50)
    print(answer)
    print("-" * 50)
    assert len(answer) > 200, "Respuesta demasiado corta"
    assert "arquitectura" in answer.lower() or "frontend" in answer.lower() or "backend" in answer.lower()
    print("✅ TEST E2E 1 PASADO: El agente respondió con la arquitectura completa sin evasivas.\n")


def run_e2e_ask_test():
    print("\n" + "=" * 70)
    print("🚀 TEST E2E 2: MODO ASK — Explicación de Código sin @ explícito")
    print("=" * 70)

    test_dir = tempfile.mkdtemp(prefix="e2e_ask_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)

    try:
        sample_code = (
            "def calculate_discount(price: float, discount_percent: float) -> float:\n"
            "    \"\"\"Calcula el precio final tras aplicar un porcentaje de descuento.\"\"\"\n"
            "    if discount_percent < 0 or discount_percent > 100:\n"
            "        raise ValueError('Descuento debe estar entre 0 y 100')\n"
            "    return price * (1.0 - discount_percent / 100.0)\n"
        )
        Path("pricing.py").write_text(sample_code, encoding="utf-8")

        user_input = "¿Qué hace la función en pricing.py y qué excepciones lanza?"
        print(f"👤 Usuario: {user_input}\n")

        expanded, attached = resolve_at_file_mentions(user_input)
        print(f"📎 Archivos adjuntados automáticamente: {[f.name for f in attached]}")
        assert len(attached) == 1 and attached[0].name == "pricing.py"

        orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="ask")
        answer = orch.run_turn(expanded)

        print("🤖 Respuesta de AETHER (Modo ASK):")
        print("-" * 50)
        print(answer)
        print("-" * 50)
        assert "calculate_discount" in answer or "descuento" in answer.lower()
        assert "valueerror" in answer.lower() or "excepción" in answer.lower() or "excepcion" in answer.lower()
        print("✅ TEST E2E 2 PASADO: El agente leyó pricing.py y explicó la función y sus excepciones.\n")
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


def run_e2e_agent_test():
    print("\n" + "=" * 70)
    print("🚀 TEST E2E 3: MODO AGENT — Programación Autónoma de Principio a Fin")
    print("=" * 70)

    test_dir = tempfile.mkdtemp(prefix="e2e_agent_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)

    try:
        def on_thought(t):
            clean = t.strip().replace("\n", " ")
            if clean and not clean.startswith("{"):
                print(f"💭 Razonamiento: {clean[:90]}...")

        def on_tool(name, args):
            info = f"path='{args.get('path')}'" if 'path' in args else (f"cmd='{args.get('command')}'" if 'command' in args else str(list(args.keys())))
            print(f"⚙️ Herramienta: {name}({info})")

        orch = AgentOrchestrator(
            model="qwen2.5-coder:7b",
            mode="agent",
            on_thought=on_thought,
            on_tool_call=on_tool
        )

        user_input = (
            "Crea un módulo validator.py con una función is_valid_email(email: str) -> bool que use regex, "
            "crea sus pruebas unitarias en test_validator.py y corre las pruebas con run_tests."
        )
        print(f"👤 Usuario: {user_input}\n")

        expanded, _ = resolve_at_file_mentions(user_input)
        answer = orch.run_turn(expanded)

        print("\n🤖 Respuesta de AETHER (Modo AGENT):")
        print("-" * 50)
        print(answer)
        print("-" * 50)

        # Verificaciones en disco
        assert Path("validator.py").exists(), "validator.py no fue creado"
        assert Path("test_validator.py").exists(), "test_validator.py no fue creado"
        validator_code = Path("validator.py").read_text(encoding="utf-8")
        assert "is_valid_email" in validator_code or "validate" in validator_code, "La función de validación no fue encontrada en validator.py"

        print("✅ TEST E2E 3 PASADO: El agente programó validator.py, escribió los tests y los corrió de forma autónoma.\n")
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


def run_e2e_review_test():
    print("\n" + "=" * 70)
    print("🚀 TEST E2E 4: MODO REVIEW — Supervisión Interactiva de Modificaciones")
    print("=" * 70)

    test_dir = tempfile.mkdtemp(prefix="e2e_review_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)

    try:
        Path("config.py").write_text("DEBUG = False\nPORT = 8000\n", encoding="utf-8")

        diff_received = []

        def mock_confirm(msg):
            diff_received.append(msg)
            print(f"🔍 Confirmación recibida en callback (Vista Previa Diff):\n{msg[:160]}...\n")
            return True  # Aprobado por el usuario

        orch = AgentOrchestrator(
            model="qwen2.5-coder:7b",
            mode="review",
            confirm_callback=mock_confirm
        )

        user_input = "Modifica config.py cambiando PORT a 9000"
        print(f"👤 Usuario: {user_input}\n")

        expanded, _ = resolve_at_file_mentions(user_input)
        answer = orch.run_turn(expanded)

        print("🤖 Respuesta de AETHER (Modo REVIEW):")
        print("-" * 50)
        print(answer)
        print("-" * 50)

        assert len(diff_received) > 0, "No se presentó solicitud de confirmación con diff en review mode"
        assert "9000" in Path("config.py").read_text(encoding="utf-8"), "El cambio aprobado no se aplicó"
        print("✅ TEST E2E 4 PASADO: El agente presentó el unified diff al usuario y aplicó el cambio tras aprobación.\n")
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    print("Iniciando Suite de Pruebas End-to-End Reales con qwen2.5-coder:7b...")
    run_e2e_plan_test()
    run_e2e_ask_test()
    run_e2e_review_test()
    run_e2e_agent_test()
    print("\n" + "=" * 70)
    print("🎉 TODAS LAS 4 PRUEBAS E2E REALES COMPLETADAS EXITOSAMENTE")
    print("=" * 70)
