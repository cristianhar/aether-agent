import sys
import time
from tools.process_manager import ProcessManager


def test_process_manager_background_execution_and_status():
    pm = ProcessManager()

    # Ejecutar un comando que produce salida en consola sin buffer
    cmd = f'"{sys.executable}" -u -c "import time; print(\'STARTED_PROCESS\'); time.sleep(0.5); print(\'FINISHED_PROCESS\')"'
    proc_id = pm.start_process(cmd)
    assert proc_id.startswith("proc_")

    # Esperar hasta que el proceso termine y capture stdout (hasta 6 segundos en Windows)
    for _ in range(60):
        time.sleep(0.1)
        status = pm.get_status(proc_id)
        if not status.get("is_running", True) and "FINISHED_PROCESS" in status.get("stdout", ""):
            break

    status = pm.get_status(proc_id)
    assert status["success"] is True
    assert "STARTED_PROCESS" in status["stdout"], f"Stderr was: {status.get('stderr')}"
    assert "FINISHED_PROCESS" in status["stdout"]
    assert status["is_running"] is False
    assert status["exit_code"] == 0


def test_process_manager_cancellation():
    pm = ProcessManager()

    # Iniciar un proceso que duerme largo tiempo
    cmd = f'"{sys.executable}" -c "import time; time.sleep(10)"'
    proc_id = pm.start_process(cmd)

    # Cancelar el proceso
    res = pm.cancel_process(proc_id)
    assert res["success"] is True

    status = pm.get_status(proc_id)
    assert status["is_running"] is False
