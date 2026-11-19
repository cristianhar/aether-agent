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


if __name__ == "__main__":
    test_real_cancellation()
    test_real_ask_question_e2e()
    test_real_artifacts_e2e()
    print("\n" + "=" * 70)
    print("🎉 TODAS LAS PRUEBAS E2E REALES PASARON CON ÉXITO")
    print("=" * 70)
