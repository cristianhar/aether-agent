"""
Gestor de procesos asíncronos y cancelación en segundo plano para AETHER IDE.
Permite ejecutar servidores de desarrollo, watchers y pruebas prolongadas sin congelar al agente,
con capacidad de matar árboles de procesos en Windows (taskkill /F /T /PID) y Unix.
"""

from dataclasses import dataclass, field
from datetime import datetime
import os
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class ProcessInfo:
    process_id: str
    command: str
    pid: int
    started_at: datetime
    process: subprocess.Popen
    stdout_buffer: List[str] = field(default_factory=list)
    stderr_buffer: List[str] = field(default_factory=list)
    exit_code: Optional[int] = None
    is_running: bool = True


class ProcessManager:
    """
    Controlador central de procesos en segundo plano para AETHER.
    """

    _instance: Optional["ProcessManager"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self.processes: Dict[str, ProcessInfo] = {}
        self._initialized = True

    def start_process(self, command: str, cwd: Optional[str] = None) -> str:
        """Inicia un comando en segundo plano y retorna su identificador único process_id."""
        process_id = f"proc_{uuid.uuid4().hex[:8]}"

        popen_kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "cwd": cwd or os.getcwd(),
            "bufsize": 1,
            "stdin": subprocess.DEVNULL,
        }

        # En Windows creamos un grupo de procesos separado si es posible
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen(command, shell=True, **popen_kwargs)

        info = ProcessInfo(
            process_id=process_id,
            command=command,
            pid=proc.pid,
            started_at=datetime.now(),
            process=proc,
        )

        with self._lock:
            self.processes[process_id] = info

        # Hilos para consumir stdout y stderr y evitar deadlocks de buffer
        threading.Thread(target=self._reader_thread, args=(proc.stdout, info.stdout_buffer), daemon=True).start()
        threading.Thread(target=self._reader_thread, args=(proc.stderr, info.stderr_buffer), daemon=True).start()

        # Hilo monitor para detectar finalización
        threading.Thread(target=self._waiter_thread, args=(info,), daemon=True).start()

        return process_id

    def _reader_thread(self, pipe, buffer: List[str]):
        if not pipe:
            return
        try:
            for line in iter(pipe.readline, ""):
                if line:
                    buffer.append(line)
        except Exception:
            pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def _waiter_thread(self, info: ProcessInfo):
        info.process.wait()
        info.exit_code = info.process.returncode
        info.is_running = False

    def get_status(self, process_id: str, tail_lines: int = 50) -> Dict[str, Any]:
        """Obtiene el estado actual y las últimas líneas de salida del proceso."""
        with self._lock:
            info = self.processes.get(process_id)
            if not info:
                return {"success": False, "error": f"Proceso '{process_id}' no encontrado."}

            # Actualizar estado si ya finalizó
            if info.is_running and info.process.poll() is not None:
                info.exit_code = info.process.returncode
                info.is_running = False

            stdout_tail = "".join(info.stdout_buffer[-tail_lines:])
            stderr_tail = "".join(info.stderr_buffer[-tail_lines:])

            return {
                "success": True,
                "process_id": info.process_id,
                "command": info.command,
                "pid": info.pid,
                "is_running": info.is_running,
                "exit_code": info.exit_code,
                "runtime_seconds": (datetime.now() - info.started_at).total_seconds(),
                "stdout": stdout_tail,
                "stderr": stderr_tail,
            }

    def cancel_process(self, process_id: str) -> Dict[str, Any]:
        """Termina forzosamente el proceso y todo su árbol de subprocesos."""
        with self._lock:
            info = self.processes.get(process_id)
            if not info:
                return {"success": False, "error": f"Proceso '{process_id}' no encontrado."}

            if not info.is_running or info.process.poll() is not None:
                info.is_running = False
                return {"success": True, "message": f"El proceso '{process_id}' ya había finalizado."}

            pid = info.pid

        # 1. Intento de parada controlada / graceful shutdown
        try:
            info.process.terminate()
            info.process.wait(timeout=1.5)
            info.is_running = False
            info.exit_code = info.process.returncode
            return {"success": True, "message": f"Proceso '{process_id}' (PID {pid}) detenido de forma controlada (graceful termination)."}
        except (subprocess.TimeoutExpired, Exception):
            pass

        # 2. Si continúa en ejecución, escalar a terminación forzosa del árbol de procesos
        try:
            if sys.platform == "win32":
                subprocess.run(
                    f"taskkill /F /T /PID {pid}",
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            else:
                info.process.kill()
        except Exception as e:
            try:
                info.process.kill()
            except Exception:
                pass

        info.is_running = False
        info.exit_code = -9
        return {"success": True, "message": f"Proceso '{process_id}' (PID {pid}) terminado tras escalar a cierre forzoso."}

    def list_processes(self) -> List[Dict[str, Any]]:
        """Lista todos los procesos registrados."""
        with self._lock:
            summary = []
            for pid_id, info in self.processes.items():
                if info.is_running and info.process.poll() is not None:
                    info.exit_code = info.process.returncode
                    info.is_running = False
                summary.append(
                    {
                        "process_id": pid_id,
                        "command": info.command,
                        "pid": info.pid,
                        "is_running": info.is_running,
                        "exit_code": info.exit_code,
                    }
                )
            return summary
