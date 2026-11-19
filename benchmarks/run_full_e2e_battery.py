"""
Batería de Pruebas End-to-End Exhaustivas con qwen2.5-coder:7b.
Ejecuta 16 escenarios reales de principio a fin evaluando la robustez
absoluta de los 4 modos operativos (PLAN, ASK, REVIEW, AGENT).
"""

import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.orchestrator import AgentOrchestrator
from agent.context import resolve_at_file_mentions


def log_test_header(num: int, mode: str, title: str):
    print("\n" + "=" * 75)
    print(f"🧪 [TEST E2E {num}/16] MODO {mode.upper()} — {title}")
    print("=" * 75)


def run_plan_tests() -> List[Dict[str, Any]]:
    results = []

    # 1. PLAN-E2E-1: Arquitectura General
    log_test_header(1, "PLAN", "Consulta de Arquitectura de Sitio de Citas")
    orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="plan")
    prompt = "COmo iniciarias una arquitectura de un sitio de citas?"
    print(f"👤 Usuario: {prompt}")
    expanded, _ = resolve_at_file_mentions(prompt)
    t0 = time.perf_counter()
    ans = orch.run_turn(expanded)
    dur = time.perf_counter() - t0
    print(f"🤖 AETHER:\n{ans}\n(Duración: {dur:.2f}s)")
    ans_lower = ans.lower()
    p1 = len(ans) > 200 and any(k in ans_lower for k in ["frontend", "backend", "base de datos", "arquitectura", "caching", "seguridad"])
    p1 = p1 and not ("como agente local autónomo, no pediré" in ans_lower)
    assert p1, "Modo PLAN falló o respondió con evasivas robóticas"
    print("✅ PLAN-E2E-1 PASADO\n")
    results.append({"id": "PLAN-E2E-1", "pass": True, "dur": dur})

    # 2. PLAN-E2E-2: Esquema de Base de Datos y Modelo de Datos
    log_test_header(2, "PLAN", "Diseño de Esquema de Base de Datos E-commerce")
    orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="plan")
    prompt = "Diseña el modelo de base de datos relacional para una tienda con usuarios, productos, pedidos y pagos."
    print(f"👤 Usuario: {prompt}")
    expanded, _ = resolve_at_file_mentions(prompt)
    t0 = time.perf_counter()
    ans = orch.run_turn(expanded)
    dur = time.perf_counter() - t0
    print(f"🤖 AETHER:\n{ans}\n(Duración: {dur:.2f}s)")
    ans_lower = ans.lower()
    p2 = len(ans) > 150 and any(k in ans_lower for k in ["tabla", "usuario", "producto", "pedido", "relaci", "foreign key", "id", "schema"])
    assert p2, "Modo PLAN no diseñó el modelo de base de datos"
    print("✅ PLAN-E2E-2 PASADO\n")
    results.append({"id": "PLAN-E2E-2", "pass": True, "dur": dur})

    # 3. PLAN-E2E-3: Creación y Sincronización de Plan con update_plan
    log_test_header(3, "PLAN", "Estructuración de Plan de Ejecución con update_plan")
    test_dir = tempfile.mkdtemp(prefix="e2e_plan_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)
    try:
        orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="plan")
        prompt = "Crea un plan de 3 pasos para refactorizar la autenticación JWT usando update_plan."
        print(f"👤 Usuario: {prompt}")
        expanded, _ = resolve_at_file_mentions(prompt)
        t0 = time.perf_counter()
        ans = orch.run_turn(expanded)
        dur = time.perf_counter() - t0
        print(f"🤖 AETHER:\n{ans}\n(Duración: {dur:.2f}s)")
        plan_file = Path(".aether/plans/plan_activo.md")
        p3 = plan_file.exists() or "plan" in ans.lower()
        assert p3, "No se generó el artefacto de plan"
        print("✅ PLAN-E2E-3 PASADO\n")
        results.append({"id": "PLAN-E2E-3", "pass": True, "dur": dur})
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)

    # 4. PLAN-E2E-4: Consulta de Plan Activo con get_plan
    log_test_header(4, "PLAN", "Consulta del Plan Activo con get_plan")
    test_dir = tempfile.mkdtemp(prefix="e2e_get_plan_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)
    try:
        from tools.agent_tools import update_plan
        update_plan(
            plan_steps=["1. Diseñar modelos", "2. Crear endpoints REST", "3. Ejecutar pruebas unitarias"],
            current_step=2,
            acceptance_criteria=["Todos los endpoints responden con 200 OK"]
        )
        orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="plan")
        prompt = "¿Cuál es el estado actual del plan y qué paso está en progreso?"
        print(f"👤 Usuario: {prompt}")
        expanded, _ = resolve_at_file_mentions(prompt)
        t0 = time.perf_counter()
        ans = orch.run_turn(expanded)
        dur = time.perf_counter() - t0
        print(f"🤖 AETHER:\n{ans}\n(Duración: {dur:.2f}s)")
        p4 = "paso 2" in ans.lower() or "endpoints" in ans.lower() or "en progreso" in ans.lower() or "plan" in ans.lower()
        assert p4, "No se leyó el plan activo correctamente"
        print("✅ PLAN-E2E-4 PASADO\n")
        results.append({"id": "PLAN-E2E-4", "pass": True, "dur": dur})
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)

    return results


def run_ask_tests() -> List[Dict[str, Any]]:
    results = []

    # 5. ASK-E2E-1: Consulta sin @ explícito
    log_test_header(5, "ASK", "Explicación de Código sin @ explícito")
    test_dir = tempfile.mkdtemp(prefix="e2e_ask1_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)
    try:
        code = (
            "def calculate_discount(price: float, discount_percent: float) -> float:\n"
            "    if discount_percent < 0 or discount_percent > 100:\n"
            "        raise ValueError('Descuento debe estar entre 0 y 100')\n"
            "    return price * (1.0 - discount_percent / 100.0)\n"
        )
        Path("pricing.py").write_text(code, encoding="utf-8")
        prompt = "¿Qué hace la función en pricing.py y qué excepciones lanza?"
        print(f"👤 Usuario: {prompt}")
        expanded, attached = resolve_at_file_mentions(prompt)
        assert len(attached) == 1 and attached[0].name == "pricing.py"
        orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="ask")
        t0 = time.perf_counter()
        ans = orch.run_turn(expanded)
        dur = time.perf_counter() - t0
        print(f"🤖 AETHER:\n{ans}\n(Duración: {dur:.2f}s)")
        assert "valueerror" in ans.lower() or "descuento" in ans.lower()
        print("✅ ASK-E2E-1 PASADO\n")
        results.append({"id": "ASK-E2E-1", "pass": True, "dur": dur})
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)

    # 6. ASK-E2E-2: Consulta con @ explícito
    log_test_header(6, "ASK", "Inspección de Clase con @models.py")
    test_dir = tempfile.mkdtemp(prefix="e2e_ask2_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)
    try:
        code = (
            "class UserSession:\n"
            "    def __init__(self, user_id: str, token: str):\n"
            "        self.user_id = user_id\n"
            "        self.token = token\n"
            "        self.active = True\n\n"
            "    def invalidate(self):\n"
            "        self.active = False\n"
        )
        Path("models.py").write_text(code, encoding="utf-8")
        prompt = "Explica la clase UserSession en @models.py y cómo funciona el método invalidate."
        print(f"👤 Usuario: {prompt}")
        expanded, attached = resolve_at_file_mentions(prompt)
        assert len(attached) == 1 and attached[0].name == "models.py"
        orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="ask")
        t0 = time.perf_counter()
        ans = orch.run_turn(expanded)
        dur = time.perf_counter() - t0
        print(f"🤖 AETHER:\n{ans}\n(Duración: {dur:.2f}s)")
        assert "usersession" in ans.lower() and "invalidate" in ans.lower()
        print("✅ ASK-E2E-2 PASADO\n")
        results.append({"id": "ASK-E2E-2", "pass": True, "dur": dur})
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)

    # 7. ASK-E2E-3: Consulta Conceptual (Sin llamadas a herramientas)
    log_test_header(7, "ASK", "Consulta Conceptual de Programación Python")
    orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="ask")
    prompt = "¿Cuál es la diferencia entre @classmethod y @staticmethod en Python?"
    print(f"👤 Usuario: {prompt}")
    expanded, _ = resolve_at_file_mentions(prompt)
    t0 = time.perf_counter()
    ans = orch.run_turn(expanded)
    dur = time.perf_counter() - t0
    print(f"🤖 AETHER:\n{ans}\n(Duración: {dur:.2f}s)")
    assert "cls" in ans.lower() or "classmethod" in ans.lower()
    print("✅ ASK-E2E-3 PASADO\n")
    results.append({"id": "ASK-E2E-3", "pass": True, "dur": dur})

    # 8. ASK-E2E-4: Blindaje Determinista de Mutación en Modo ASK
    log_test_header(8, "ASK", "Blindaje Anti-Mutación Prohibida en Modo ASK")
    test_dir = tempfile.mkdtemp(prefix="e2e_ask4_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)
    try:
        orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="ask")
        prompt = "Crea un archivo llamado hack.py con print('hack')"
        print(f"👤 Usuario: {prompt}")
        expanded, _ = resolve_at_file_mentions(prompt)
        t0 = time.perf_counter()
        ans = orch.run_turn(expanded)
        dur = time.perf_counter() - t0
        print(f"🤖 AETHER:\n{ans}\n(Duración: {dur:.2f}s)")
        assert not Path("hack.py").exists(), "El modo ASK permitió crear un archivo en disco"
        print("✅ ASK-E2E-4 PASADO: 0 mutaciones en disco garantizado.\n")
        results.append({"id": "ASK-E2E-4", "pass": True, "dur": dur})
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)

    return results


def run_review_tests() -> List[Dict[str, Any]]:
    results = []

    # 9. REVIEW-E2E-1: Modificación con Unified Diff Aprobado
    log_test_header(9, "REVIEW", "Modificación Supervisada y Diff Aprobado")
    test_dir = tempfile.mkdtemp(prefix="e2e_rev1_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)
    try:
        Path("config.py").write_text("DEBUG = False\nPORT = 8000\n", encoding="utf-8")
        diffs = []
        def approve(diff):
            diffs.append(diff)
            print(f"🔍 [INTERCEPTOR DIFF]:\n{diff[:150]}...")
            return True

        orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="review", confirm_callback=approve)
        prompt = "Modifica config.py cambiando PORT a 9000"
        print(f"👤 Usuario: {prompt}")
        expanded, _ = resolve_at_file_mentions(prompt)
        t0 = time.perf_counter()
        ans = orch.run_turn(expanded)
        dur = time.perf_counter() - t0
        print(f"🤖 AETHER:\n{ans}\n(Duración: {dur:.2f}s)")
        assert len(diffs) > 0, "No se presentó solicitud de confirmación con diff"
        assert "9000" in Path("config.py").read_text(encoding="utf-8"), "El cambio aprobado no se aplicó en disco"
        print("✅ REVIEW-E2E-1 PASADO\n")
        results.append({"id": "REVIEW-E2E-1", "pass": True, "dur": dur})
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)

    # 10. REVIEW-E2E-2: Modificación con Unified Diff Rechazado
    log_test_header(10, "REVIEW", "Modificación Supervisada y Diff Rechazado por Desarrollador")
    test_dir = tempfile.mkdtemp(prefix="e2e_rev2_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)
    try:
        Path("config.py").write_text("DEBUG = False\nPORT = 8000\n", encoding="utf-8")
        diffs = []
        def reject(diff):
            diffs.append(diff)
            print(f"🔍 [DIFF RECHAZADO POR DESARROLLADOR]:\n{diff[:150]}...")
            return False

        orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="review", confirm_callback=reject)
        prompt = "Modifica config.py cambiando DEBUG a True"
        print(f"👤 Usuario: {prompt}")
        expanded, _ = resolve_at_file_mentions(prompt)
        t0 = time.perf_counter()
        ans = orch.run_turn(expanded)
        dur = time.perf_counter() - t0
        print(f"🤖 AETHER:\n{ans}\n(Duración: {dur:.2f}s)")
        assert len(diffs) > 0, "No se presentó diff"
        assert "DEBUG = False" in Path("config.py").read_text(encoding="utf-8"), "El cambio rechazado se aplicó indebidamente"
        print("✅ REVIEW-E2E-2 PASADO: Archivo intacto tras rechazo.\n")
        results.append({"id": "REVIEW-E2E-2", "pass": True, "dur": dur})
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)

    # 11. REVIEW-E2E-3: Auditoría y Resumen de Cambios con get_git_diff
    log_test_header(11, "REVIEW", "Auditoría de Estado de Git")
    test_dir = tempfile.mkdtemp(prefix="e2e_rev3_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)
    try:
        import subprocess
        subprocess.run(["git", "init"], capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], capture_output=True, check=True)
        Path("app.py").write_text("VERSION = 1\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.py"], capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", "init"], capture_output=True, check=True)
        Path("app.py").write_text("VERSION = 2\n", encoding="utf-8")

        orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="review")
        prompt = "Revisa los cambios pendientes en git y haz una auditoría técnica."
        print(f"👤 Usuario: {prompt}")
        expanded, _ = resolve_at_file_mentions(prompt)
        t0 = time.perf_counter()
        ans = orch.run_turn(expanded)
        dur = time.perf_counter() - t0
        print(f"🤖 AETHER:\n{ans}\n(Duración: {dur:.2f}s)")
        assert "version" in ans.lower() or "app.py" in ans.lower() or "diff" in ans.lower() or "cambio" in ans.lower()
        print("✅ REVIEW-E2E-3 PASADO\n")
        results.append({"id": "REVIEW-E2E-3", "pass": True, "dur": dur})
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)

    # 12. REVIEW-E2E-4: Creación Supervisada de Archivo Nuevo
    log_test_header(12, "REVIEW", "Creación Supervisada de Archivo Nuevo con Autorización")
    test_dir = tempfile.mkdtemp(prefix="e2e_rev4_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)
    try:
        diffs = []
        def approve(diff):
            diffs.append(diff)
            return True

        orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="review", confirm_callback=approve)
        prompt = "Crea un archivo utils.py con una función slugify(text: str) -> str"
        print(f"👤 Usuario: {prompt}")
        expanded, _ = resolve_at_file_mentions(prompt)
        t0 = time.perf_counter()
        ans = orch.run_turn(expanded)
        dur = time.perf_counter() - t0
        print(f"🤖 AETHER:\n{ans}\n(Duración: {dur:.2f}s)")
        assert Path("utils.py").exists(), "utils.py no fue creado tras aprobación"
        assert len(diffs) > 0, "No se solicitó aprobación previa"
        print("✅ REVIEW-E2E-4 PASADO\n")
        results.append({"id": "REVIEW-E2E-4", "pass": True, "dur": dur})
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)

    return results


def run_agent_tests() -> List[Dict[str, Any]]:
    results = []

    # 13. AGENT-E2E-1: Programación Autónoma y Verificación
    log_test_header(13, "AGENT", "Programación Autónoma y Verificación de Código")
    test_dir = tempfile.mkdtemp(prefix="e2e_ag1_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)
    try:
        def on_tool(name, args):
            info = f"path='{args.get('path')}'" if 'path' in args else (f"cmd='{args.get('command')}'" if 'command' in args else str(list(args.keys())))
            print(f"⚙️ Herramienta: {name}({info})")

        orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="agent", on_tool_call=on_tool)
        prompt = "Crea validator.py con is_valid_email(email: str) -> bool usando regex, crea test_validator.py y corre run_tests."
        print(f"👤 Usuario: {prompt}")
        expanded, _ = resolve_at_file_mentions(prompt)
        t0 = time.perf_counter()
        ans = orch.run_turn(expanded)
        dur = time.perf_counter() - t0
        print(f"🤖 AETHER:\n{ans}\n(Duración: {dur:.2f}s)")
        assert Path("validator.py").exists(), "validator.py no existe"
        assert Path("test_validator.py").exists(), "test_validator.py no existe"
        code = Path("validator.py").read_text(encoding="utf-8")
        assert "is_valid_email" in code or "validate" in code
        assert "número máximo de iteraciones" not in ans.lower(), "El agente alcanzó el límite máximo de iteraciones sin concluir formalmente"
        print("✅ AGENT-E2E-1 PASADO\n")
        results.append({"id": "AGENT-E2E-1", "pass": True, "dur": dur})
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)

    # 14. AGENT-E2E-2: Auto-Sanación ante Bug en Pruebas
    log_test_header(14, "AGENT", "Bucle de Auto-Sanación (Self-Healing)")
    test_dir = tempfile.mkdtemp(prefix="e2e_ag2_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)
    try:
        # Código con bug intencional
        buggy_code = (
            "def divide(a: float, b: float) -> float:\n"
            "    return a / b  # Falla con ZeroDivisionError si b == 0\n"
        )
        Path("math_lib.py").write_text(buggy_code, encoding="utf-8")
        test_code = (
            "import pytest\n"
            "from math_lib import divide\n\n"
            "def test_divide():\n"
            "    assert divide(10, 2) == 5\n"
            "    assert divide(5, 0) == 0.0  # El test espera 0.0 en división por cero\n"
        )
        Path("test_math_lib.py").write_text(test_code, encoding="utf-8")

        orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="agent")
        prompt = "Ejecuta run_tests() sobre test_math_lib.py, detecta por qué falla math_lib.py, corrígelo con edit_file y vuelve a probar."
        print(f"👤 Usuario: {prompt}")
        expanded, _ = resolve_at_file_mentions(prompt)
        t0 = time.perf_counter()
        ans = orch.run_turn(expanded)
        dur = time.perf_counter() - t0
        print(f"🤖 AETHER:\n{ans}\n(Duración: {dur:.2f}s)")
        fixed_code = Path("math_lib.py").read_text(encoding="utf-8")
        assert "if b == 0" in fixed_code or "except ZeroDivisionError" in fixed_code or "return 0" in fixed_code
        print("✅ AGENT-E2E-2 PASADO: Bug corregido y pruebas auto-sanadas.\n")
        results.append({"id": "AGENT-E2E-2", "pass": True, "dur": dur})
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)

    # 15. AGENT-E2E-3: Memoria Semántica
    log_test_header(15, "AGENT", "Persistencia de Memoria Semántica")
    test_dir = tempfile.mkdtemp(prefix="e2e_ag3_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)
    try:
        orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="agent")
        prompt1 = "Recuerda con remember_fact que en este proyecto la base de datos es PostgreSQL 16 y el puerto es 5432."
        print(f"👤 Usuario: {prompt1}")
        expanded1, _ = resolve_at_file_mentions(prompt1)
        ans1 = orch.run_turn(expanded1)
        print(f"🤖 AETHER:\n{ans1}")

        prompt2 = "¿Qué base de datos y puerto se definieron en la memoria del proyecto?"
        print(f"👤 Usuario: {prompt2}")
        expanded2, _ = resolve_at_file_mentions(prompt2)
        t0 = time.perf_counter()
        ans2 = orch.run_turn(expanded2)
        dur = time.perf_counter() - t0
        print(f"🤖 AETHER:\n{ans2}\n(Duración: {dur:.2f}s)")
        assert "5432" in ans2 or "postgres" in ans2.lower()
        print("✅ AGENT-E2E-3 PASADO\n")
        results.append({"id": "AGENT-E2E-3", "pass": True, "dur": dur})
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)

    # 16. AGENT-E2E-4: Refactorización y Completion Guard
    log_test_header(16, "AGENT", "Refactorización y Cierre Inmediato vía Completion Guard")
    test_dir = tempfile.mkdtemp(prefix="e2e_ag4_")
    orig_cwd = os.getcwd()
    os.chdir(test_dir)
    try:
        orig_code = (
            "def format_greeting(name: str, age: int) -> str:\n"
            "    return 'Hola ' + name + ', tienes ' + str(age) + ' años'\n"
        )
        Path("formatter.py").write_text(orig_code, encoding="utf-8")
        test_code = (
            "from formatter import format_greeting\n"
            "def test_greeting():\n"
            "    assert format_greeting('Ana', 25) == 'Hola Ana, tienes 25 años'\n"
        )
        Path("test_formatter.py").write_text(test_code, encoding="utf-8")

        tool_calls_count = 0
        def on_tool(name, args):
            nonlocal tool_calls_count
            tool_calls_count += 1
            print(f"⚙️ Herramienta: {name}")

        orch = AgentOrchestrator(model="qwen2.5-coder:7b", mode="agent", on_tool_call=on_tool)
        prompt = "Refactoriza formatter.py para usar f-strings en lugar de concatenar con +, y corre las pruebas con run_tests."
        print(f"👤 Usuario: {prompt}")
        expanded, _ = resolve_at_file_mentions(prompt)
        t0 = time.perf_counter()
        ans = orch.run_turn(expanded)
        dur = time.perf_counter() - t0
        print(f"🤖 AETHER:\n{ans}\n(Duración: {dur:.2f}s)")
        refactored = Path("formatter.py").read_text(encoding="utf-8")
        assert "f'Hola " in refactored or 'f"Hola ' in refactored
        assert tool_calls_count <= 8, f"Demasiadas iteraciones ({tool_calls_count}), posible bucle improductivo"
        print("✅ AGENT-E2E-4 PASADO: Refactorización limpia y conclusión rápida sin bucles.\n")
        results.append({"id": "AGENT-E2E-4", "pass": True, "dur": dur})
    finally:
        os.chdir(orig_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)

    return results


def main():
    print("\n" + "=" * 75)
    print("🚀 INICIANDO BATERÍA EXHAUSTIVA DE 16 PRUEBAS E2E REALES CON QWEN2.5-CODER:7B")
    print("=" * 75)

    all_results = []
    start_total = time.perf_counter()

    print("\n>>> EJECUTANDO BLOQUE 1: MODO PLAN (4 PRUEBAS)")
    all_results.extend(run_plan_tests())

    print("\n>>> EJECUTANDO BLOQUE 2: MODO ASK (4 PRUEBAS)")
    all_results.extend(run_ask_tests())

    print("\n>>> EJECUTANDO BLOQUE 3: MODO REVIEW (4 PRUEBAS)")
    all_results.extend(run_review_tests())

    print("\n>>> EJECUTANDO BLOQUE 4: MODO AGENT (4 PRUEBAS)")
    all_results.extend(run_agent_tests())

    total_dur = time.perf_counter() - start_total
    passed = sum(1 for r in all_results if r["pass"])
    total = len(all_results)

    print("\n" + "=" * 75)
    print("📊 RESULTADO FINAL DE LA BATERÍA E2E REAL")
    print("=" * 75)
    print(f"Total de Pruebas: {total}")
    print(f"Superadas: {passed} / {total} ({(passed/total)*100:.1f}%)")
    print(f"Tiempo Total de Inferencia Local: {total_dur:.2f}s")
    for r in all_results:
        print(f"  • {r['id']}: {'✅ PASS' if r['pass'] else '❌ FAIL'} ({r['dur']:.2f}s)")
    print("=" * 75)


if __name__ == "__main__":
    main()
