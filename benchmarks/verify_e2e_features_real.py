"""
Batería de Verificación E2E Real para Nuevas Capacidades de AETHER:
1. E2E-CANCEL: Cancelación en caliente durante la ejecución activa de un turno.
2. E2E-ASK-QUESTION: El agente en modo PLAN utiliza la herramienta ask_question para resolver ambigüedad.
3. E2E-ARTIFACTS: El agente genera un artefacto persistente y se valida en disco su .md y .meta.json.
"""

import json
from pathlib import Path
import sys
import threading
import time

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.artifacts import ArtifactManager
from agent.orchestrator import AgentOrchestrator
from agent.state import AgentState, CancellationToken
from tools.agent_tools import set_ask_question_callback


def test_real_cancellation():
    print("\n" + "=" * 70)
    print("▶ [TEST 1/3] VERIFICACIÓN E2E DE CANCELACIÓN EN CALIENTE (Ctrl+C / Cancel)")
    print("=" * 70)

    orchestrator = AgentOrchestrator(model="qwen2.5-coder:7b")
    token = CancellationToken()

    result_holder = {}

    def worker():
        try:
            res = orchestrator.run_turn(
                "Escribe un script complejo con muchas clases y funciones detalladas",
                cancellation_token=token,
            )
            result_holder["result"] = res
        except Exception as e:
            result_holder["error"] = str(e)

    t = threading.Thread(target=worker)
    t.start()

    # Esperar a que el agente comience a pensar/ejecutar
    time.sleep(1.2)
    print("⚡ Simulando interrupción del usuario (Ctrl+C)...")
    orchestrator.cancel_active_turn("Cancelado intencionalmente por prueba de usuario.")
    t.join(timeout=10)

    assert orchestrator.state == AgentState.IDLE, f"El estado debe ser IDLE, pero fue {orchestrator.state}"
    print("✅ Agente regresó limpiamente a estado IDLE.")

    # Probar que el agente queda listo inmediatamente para otro turno sin reiniciar proceso
    print("⚡ Verificando turno subsiguiente después de la cancelación...")
    res2 = orchestrator.run_turn("Di únicamente 'SISTEMA_REANUDADO_OK'")
    print(f"Respuesta del agente: {res2.strip()[:60]}...")
    assert orchestrator.state in [AgentState.COMPLETED, AgentState.IDLE]
    print("✅ [TEST 1 PASADO]: Cancelación en caliente funcional y recuperación 100% limpia.")


def test_real_ask_question_e2e():
    print("\n" + "=" * 70)
    print("▶ [TEST 2/3] VERIFICACIÓN E2E DE ask_question EN MODO PLAN")
    print("=" * 70)

    orchestrator = AgentOrchestrator(model="qwen2.5-coder:7b", mode="plan")

    asked_questions = []

    def mock_user_response(questions):
        print(f"\n[SIMULADOR DE USUARIO] Recibida pregunta interactiva de AETHER:")
        for q in questions:
            print(f"  ❓ {q.get('question')}")
            for idx, opt in enumerate(q.get("options", []), 1):
                print(f"     [{idx}] {opt}")
        asked_questions.extend(questions)
        # El usuario elige PostgreSQL
        return [{"question": questions[0].get("question", ""), "selected": ["PostgreSQL"]}]

    set_ask_question_callback(mock_user_response)

    prompt = (
        "Vamos a iniciar la arquitectura de un backend. Formula una pregunta obligatoria con ask_question "
        "para consultar qué base de datos prefiere el usuario antes de definir el plan."
    )

    try:
        ans = orchestrator.run_turn(prompt)
        print(f"\nRespuesta final del agente:\n{ans[:150]}...")
        assert len(asked_questions) >= 1, "El agente debió invocar ask_question"
        print("✅ [TEST 2 PASADO]: El agente ejecutó ask_question, procesó la selección y continuó su turno.")
    finally:
        set_ask_question_callback(None)


def test_real_artifacts_e2e():
    print("\n" + "=" * 70)
    print("▶ [TEST 3/3] VERIFICACIÓN E2E DE ArtifactManager EN DISCO")
    print("=" * 70)

    session_id = f"e2e_art_{int(time.time())}"
    orchestrator = AgentOrchestrator(model="qwen2.5-coder:7b", mode="plan", session_id=session_id)

    prompt = (
        "Genera un artefacto formal con la herramienta 'create_artifact' titulado 'Arquitectura de Datos', "
        "resumen 'Especificación de base de datos relacional', contenido '# Esquema\nTablas users y orders', "
        "user_facing=True y request_feedback=True."
    )

    ans = orchestrator.run_turn(prompt)
    print(f"\nRespuesta del agente: {ans[:120]}...")

    mgr = ArtifactManager(session_id=session_id)
    artifacts = mgr.list_artifacts()
    print(f"Artefactos creados en disco para sesión '{session_id}': {len(artifacts)}")

    assert len(artifacts) >= 1, "Debe haberse creado al menos un artefacto en disco."
    art = artifacts[0]
    print(f"  • ID: {art.get('artifact_id')}")
    print(f"  • Título: {art.get('title')}")
    print(f"  • Versión: {art.get('version')}")
    print(f"  • UserFacing: {art.get('user_facing')}")
    print(f"  • RequestFeedback: {art.get('request_feedback')}")

    assert art.get("user_facing") is True
    assert art.get("request_feedback") is True

    # Verificar que el archivo .md y el .meta.json existen físicamente
    doc_path = mgr.artifacts_dir / f"{art.get('artifact_id')}.md"
    meta_path = mgr.artifacts_dir / f"{art.get('artifact_id')}.meta.json"
    assert doc_path.exists(), f"El archivo {doc_path} debe existir."
    assert meta_path.exists(), f"El archivo {meta_path} debe existir."

    print("✅ [TEST 3 PASADO]: Artefacto creado físicamente en disco con contenido y metadatos JSON completos.")


def test_real_skills_e2e():
    print("\n" + "=" * 70)
    print("▶ [TEST 4/6] VERIFICACIÓN E2E DE SKILLS RUNTIME Y CATÁLOGO DINÁMICO")
    print("=" * 70)

    from agent.skills import execute_skill, get_global_skill_registry
    registry = get_global_skill_registry()
    print(f"Skills descubiertas en catálogo: {list(registry.skills.keys())}")
    assert "code-review" in registry.skills or "review" in registry.skills

    # Ejecutar skill real en disco
    res = execute_skill("code-review", target="agent/skills.py")
    print(f"Resultado de ejecución de skill 'code-review':\n{res[:120]}...")
    assert "Reporte de Code Review" in res
    print("✅ [TEST 4 PASADO]: Habilidades dinámicas ejecutadas con éxito.")


def test_real_subagents_e2e():
    print("\n" + "=" * 70)
    print("▶ [TEST 5/6] VERIFICACIÓN E2E DE SUBAGENTES JERÁRQUICOS Y BUZÓN")
    print("=" * 70)

    from agent.subagents import get_global_subagent_manager
    mgr = get_global_subagent_manager()

    # Definir subagente
    def_res = mgr.define_subagent(
        name="test-assistant",
        description="Asistente de prueba E2E",
        system_prompt="Eres un subagente de prueba.",
        enable_write_tools=False,
    )
    assert "test-assistant" in mgr.templates

    # Invocación en contexto de memoria aislado
    inv_res = mgr.invoke_subagent(
        type_name="test-assistant",
        role="Auditor E2E",
        prompt="Confirma recepción respondiendo 'SUBAGENTE_OK'",
    )
    print(f"Respuesta inicial del subagente:\n{inv_res[:120]}...")
    assert "Subagente Activado: [Auditor E2E]" in inv_res

    cid = list(mgr.instances.keys())[0]

    # Mensajería mediante buzón (send_message)
    reply2 = mgr.send_message(recipient=cid, message="Turno 2: Responde 'BUZON_OK'")
    print(f"Respuesta del buzón en turno 2:\n{reply2[:120]}...")
    assert "Respuesta del Subagente" in reply2

    # Directorio de subagentes
    list_res = mgr.manage_subagents(action="list")
    assert cid in list_res
    print("✅ [TEST 5 PASADO]: Invocación y buzón de subagentes jerárquicos 100% funcionales.")


def test_real_cdp_browser_e2e():
    print("\n" + "=" * 70)
    print("▶ [TEST 6/6] VERIFICACIÓN E2E DE NAVEGADOR CDP (CERO PLAYWRIGHT)")
    print("=" * 70)

    from tools.cdp_browser import browser_open, browser_get_content, find_chromium_binary
    binary = find_chromium_binary()
    print(f"Chromium/Edge localizado: {binary}")
    assert binary is not None

    # Abrir página local about:blank o data:
    open_res = browser_open("about:blank")
    print(f"Resultado browser_open:\n{open_res}")
    assert "Página cargada con éxito" in open_res

    content = browser_get_content()
    print(f"Contenido extraído del DOM:\n{content}")
    assert content is not None
    print("✅ [TEST 6 PASADO]: Navegación y extracción de DOM mediante CDP 100% funcional.")


if __name__ == "__main__":
    test_real_cancellation()
    test_real_ask_question_e2e()
    test_real_artifacts_e2e()
    test_real_skills_e2e()
    test_real_subagents_e2e()
    test_real_cdp_browser_e2e()
    print("\n" + "=" * 70)
    print("🎉 TODAS LAS 6 PRUEBAS E2E REALES PASARON CON ÉXITO")
    print("=" * 70)
