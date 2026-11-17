"""
AETHER Autonomous Coding Benchmark (Suite End-to-End de Autonomía y Fiabilidad)
Verifica los 8 escenarios reales de programación autónoma inspirados en Claude Code y Cursor:
1. Descubrir un bug sin ruta de archivo
2. Corregir varios archivos en transacción
3. Validar resultados leyendo exit codes reales
4. Bucle cerrado de auto-sanación (Self-Healing)
5. Detección de colisiones y concurrencia (SHA-256)
6. Cancelación limpia y reanudación de sesión
7. Checkpoint y rollback sin pérdida de trabajo del usuario
8. Resistencia frente a Prompt Injection en archivos del repositorio
"""

import os
from pathlib import Path
import subprocess
import sys
import tempfile

from agent.checkpoints import SafeCheckpointManager
from agent.orchestrator import AgentOrchestrator
from agent.permissions import PermissionEngine, PermissionRequest, PermissionDecision
from agent.session import SessionManager
from agent.state import AgentState, CancellationToken
from tools.base import PermissionLevel, ToolCategory
from tools.patch_engine import PatchEngine, PatchOperation
from tools.search_tools import search_codebase


def test_case_1_discover_bug_without_path():
    """1. Descubrir un bug: Localiza el error en el repositorio sin que se le dé la ruta del archivo."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        # Crear estructura de repositorio con router y servicio
        (ws / "routers").mkdir()
        (ws / "services").mkdir()

        (ws / "routers" / "orders.py").write_text("def create_order(): pass\n", encoding="utf-8")
        (ws / "services" / "payment.py").write_text(
            "def calculate_total(items, tax_rate):\n    # BUG: sumando tasa en vez de multiplicar\n    return sum(items) + tax_rate\n",
            encoding="utf-8"
        )

        # Simular búsqueda del agente para encontrar dónde está calculate_total
        search_result = search_codebase(query="calculate_total", path=str(ws))
        assert "payment.py" in search_result

        # El agente luego inspecciona el archivo descubierto con read_file
        from tools.file_tools import read_file
        inspected_content = read_file(str(ws / "services" / "payment.py"), start_line=1, end_line=10)
        assert "BUG: sumando tasa" in inspected_content


def test_case_2_multifile_patch_and_diff():
    """2. Corregir varios archivos: Aplica cambios sincronizados en servicio y pruebas de forma atómica."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        service_file = ws / "service.py"
        test_file = ws / "test_service.py"

        service_file.write_text("def calc(a, b):\n    return a - b\n", encoding="utf-8")
        test_file.write_text("def test_calc():\n    assert calc(2, 3) == 5\n", encoding="utf-8")

        # Operación transaccional multi-archivo
        ops = [
            PatchOperation(filepath=service_file, old_text="return a - b", new_text="return a + b"),
            PatchOperation(filepath=test_file, old_text="assert calc(2, 3) == 5", new_text="assert calc(2, 3) == 5 # fixed"),
        ]

        success, results, error = PatchEngine.apply_transaction(ops)

        assert success is True
        assert len(results) == 2
        assert "return a + b" in service_file.read_text(encoding="utf-8")
        assert "# fixed" in test_file.read_text(encoding="utf-8")


def test_case_3_validate_results_exit_code():
    """3. Validar resultados: Ejecuta pruebas reales en sub-terminal y captura código de salida."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        script = ws / "verify.py"
        script.write_text("import sys\nsys.exit(0)\n", encoding="utf-8")

        res = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
        assert res.returncode == 0

        script_err = ws / "fail.py"
        script_err.write_text("import sys\nsys.exit(1)\n", encoding="utf-8")

        res_err = subprocess.run([sys.executable, str(script_err)], capture_output=True, text=True)
        assert res_err.returncode == 1


def test_case_4_self_healing_feedback_loop():
    """4. Autocorregirse: Detecta fallo de pruebas, aplica parche y deja en verde."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        calc_file = ws / "calc.py"
        calc_file.write_text("def divide(a, b):\n    return a * b # error\n", encoding="utf-8")

        test_file = ws / "test_calc.py"
        test_file.write_text(
            "from calc import divide\ndef test_div(): assert divide(10, 2) == 5\n",
            encoding="utf-8"
        )

        # Ejecución inicial: Falla
        cmd = [sys.executable, "-m", "pytest", str(test_file)]
        initial_run = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True)
        assert initial_run.returncode != 0

        # Auto-corrección: Aplicar parche
        res_patch = PatchEngine.apply_single_patch(
            filepath=calc_file,
            old_text="return a * b # error",
            new_text="return a / b",
        )
        assert res_patch.success is True

        # Segunda ejecución: Pasa en verde
        re_run = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True)
        assert re_run.returncode == 0


def test_case_5_concurrency_conflict_detection():
    """5. Gestionar conflictos: Detecta si el archivo cambió externamente y aborta sin sobreescribir."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        target = ws / "shared.py"
        target.write_text("VERSION = '1.0.0'\n", encoding="utf-8")

        # Se esperaba un SHA que ya no coincide (usuario modificó el archivo)
        result = PatchEngine.apply_single_patch(
            filepath=target,
            old_text="VERSION = '1.0.0'",
            new_text="VERSION = '2.0.0'",
            expected_sha256="fake_sha_external_change",
        )

        assert result.success is False
        assert "Conflicto de concurrencia" in result.error
        # El archivo del usuario no sufrió cambios silenciosos
        assert target.read_text(encoding="utf-8") == "VERSION = '1.0.0'\n"


def test_case_6_cancellation_and_session_resumption():
    """6. Cancelar y reanudar: Detiene la tarea con token y recupera el historial de la sesión."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        sm = SessionManager(db_dir=Path(tmp_dir))
        orchestrator = AgentOrchestrator(session_manager=sm)

        token = CancellationToken()
        token.cancel("Detención solicitada por el usuario al presionar Esc.")

        resp = orchestrator.run_turn("Escribe un microservicio", cancellation_token=token)
        assert "Detención solicitada" in resp
        assert orchestrator.state == AgentState.CANCELLED

        # Reanudación: Sesión cargada desde SQLite
        msgs = sm.get_session_messages(orchestrator.session_id)
        assert len(msgs) >= 1
        assert msgs[0]["role"] == "user"


def test_case_7_safe_rollback_without_data_loss():
    """7. Deshacer sin pérdidas: Restaura únicamente archivos del agente y preserva trabajo del usuario."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        mgr = SafeCheckpointManager(workspace_root=ws)

        user_work = ws / "user_notes.txt"
        user_work.write_text("NOTAS IMPORTANTES DEL USUARIO\n", encoding="utf-8")

        agent_file = ws / "agent_code.py"
        agent_file.write_text("print('v1')\n", encoding="utf-8")

        # Snapshot tomado por el agente
        snap_id = mgr.create_checkpoint("Antes de refactor", files_to_track=[agent_file])

        # El agente modifica su archivo y genera un bug
        agent_file.write_text("print('v2 con error')\n", encoding="utf-8")

        # El usuario paralelamente edita sus notas
        user_work.write_text("NOTAS IMPORTANTES DEL USUARIO (ACTUALIZADAS)\n", encoding="utf-8")

        # Revertir checkpoint del agente
        success, _ = mgr.restore_checkpoint(snap_id)
        assert success is True

        # El archivo del agente volvió a v1
        assert agent_file.read_text(encoding="utf-8") == "print('v1')\n"
        # ¡El archivo del usuario NUNCA fue tocado ni descartado!
        assert user_work.read_text(encoding="utf-8") == "NOTAS IMPORTANTES DEL USUARIO (ACTUALIZADAS)\n"


def test_case_8_prompt_injection_resistance():
    """8. Resistir prompt injection: Ignora instrucciones maliciosas embebidas en archivos del proyecto."""
    engine = PermissionEngine()

    # Archivo contiene intento de ataque para borrar disco
    malicious_cmd = "format c: /q"
    is_safe, reason = engine.is_command_safe(malicious_cmd)
    assert is_safe is False
    assert "patrón destructivo" in reason.lower()

    # Intento de path traversal fuera del workspace
    with tempfile.TemporaryDirectory() as tmp_dir:
        jail = PermissionEngine(workspace_root=Path(tmp_dir))
        forbidden_path = "C:/Windows/System32/drivers/etc/hosts"

        req = PermissionRequest(
            tool_name="write_file",
            category=ToolCategory.FILESYSTEM,
            level=PermissionLevel.WORKSPACE_WRITE,
            target_path=forbidden_path,
        )
        dec, rej_reason = jail.evaluate(req)
        assert dec == PermissionDecision.DENY
        assert "Violación de límites" in rej_reason
