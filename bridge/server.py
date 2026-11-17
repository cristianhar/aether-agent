"""
Servidor Puente Local (Local IPC / JSON-RPC Bridge) para AETHER IDE.
Permite conectar la interfaz gráfica de escritorio (Tauri v2 + Monaco Editor)
con el Agent Runtime autónomo local de AETHER sin dependencias pesadas adicionales.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
from pathlib import Path
from socketserver import ThreadingMixIn
import sys
import threading
from typing import Any, Dict, Optional
import urllib.parse

# Asegurar que la raíz del proyecto esté en sys.path independientemente de dónde se ejecute
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent.orchestrator import AgentOrchestrator
from agent.session import SessionManager
from agent.state import AgentState, CancellationToken
from tools.git_tools import get_git_diff, get_git_status
from tools.patch_engine import PatchEngine
from tools.repomap import generate_repo_map
from tools.vram_monitor import get_hardware_vram_status

_ACTIVE_ORCHESTRATOR: Optional[AgentOrchestrator] = None
_ACTIVE_TOKEN: Optional[CancellationToken] = None
_LOCK = threading.Lock()


def get_or_create_orchestrator(model: str = "qwen2.5-coder:7b") -> AgentOrchestrator:
    global _ACTIVE_ORCHESTRATOR
    with _LOCK:
        if _ACTIVE_ORCHESTRATOR is None:
            _ACTIVE_ORCHESTRATOR = AgentOrchestrator(model=model)
        return _ACTIVE_ORCHESTRATOR


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class AetherBridgeHandler(BaseHTTPRequestHandler):
    """Manejador HTTP/JSON-RPC para comunicación de alta velocidad con Tauri."""

    def _set_cors_headers(self, status: int = 200, content_type: str = "application/json", content_length: int = 0):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_cors_headers(200, content_length=0)

    def _read_json_body(self) -> Dict[str, Any]:
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                body = self.rfile.read(content_length).decode("utf-8")
                return json.loads(body)
        except Exception:
            pass
        return {}

    def _send_json(self, data: Any, status: int = 200):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._set_cors_headers(status=status, content_type="application/json; charset=utf-8", content_length=len(payload))
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        orch = get_or_create_orchestrator()

        if path == "/api/status":
            vram = get_hardware_vram_status()
            self._send_json({
                "status": "online",
                "state": orch.state.value,
                "model": orch.model,
                "session_id": orch.session_id,
                "cwd": str(Path.cwd()),
                "vram_info": vram,
            })

        elif path == "/api/tree":
            repo_map = generate_repo_map(max_files=50)
            self._send_json({
                "cwd": str(Path.cwd()),
                "repo_map": repo_map,
            })

        elif path == "/api/file":
            filepath_param = params.get("path", [""])[0]
            if not filepath_param:
                self._send_json({"error": "Parámetro 'path' requerido."}, 400)
                return

            p = Path(filepath_param).resolve()
            if not p.exists() or not p.is_file():
                self._send_json({"error": f"Archivo '{filepath_param}' no encontrado."}, 404)
                return

            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                self._send_json({"path": str(p), "content": content})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif path == "/api/diff":
            diff = get_git_diff()
            git_st = get_git_status()
            self._send_json({"diff": diff, "status": git_st})

        elif path == "/api/sessions":
            sm = SessionManager()
            sessions = sm.list_sessions(limit=20)
            self._send_json({"sessions": sessions})

        else:
            self._send_json({"error": "Endpoint no encontrado."}, 404)

    def do_POST(self):
        global _ACTIVE_TOKEN
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json_body()

        orch = get_or_create_orchestrator()

        if path == "/api/chat":
            prompt = body.get("prompt", "").strip()
            if not prompt:
                self._send_json({"error": "El campo 'prompt' es obligatorio."}, 400)
                return

            with _LOCK:
                _ACTIVE_TOKEN = CancellationToken()
                token = _ACTIVE_TOKEN

            try:
                answer = orch.run_turn(prompt, cancellation_token=token)
                self._send_json({
                    "success": True,
                    "answer": answer,
                    "state": orch.state.value,
                    "session_id": orch.session_id,
                })
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)

        elif path == "/api/cancel":
            with _LOCK:
                if _ACTIVE_TOKEN:
                    _ACTIVE_TOKEN.cancel("Cancelado desde la interfaz de usuario.")
                    self._send_json({"success": True, "message": "Solicitud de cancelación enviada."})
                else:
                    self._send_json({"success": True, "message": "No hay tarea activa en ejecución."})

        elif path == "/api/file":
            filepath = body.get("path")
            content = body.get("content")
            if not filepath or content is None:
                self._send_json({"error": "Campos 'path' y 'content' requeridos."}, 400)
                return

            p = Path(filepath).resolve()
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8", newline="")
                self._send_json({"success": True, "message": f"Archivo '{p.name}' guardado correctamente."})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)

        else:
            self._send_json({"error": "Endpoint no encontrado."}, 404)


def start_bridge_server(host: str = "127.0.0.1", port: int = 8765) -> ThreadedHTTPServer:
    """Inicia el servidor puente en segundo plano."""
    server = ThreadedHTTPServer((host, port), AetherBridgeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    print(f"⚡ AETHER Desktop Bridge Server escuchando en http://127.0.0.1:{port}")
    server = ThreadedHTTPServer(("127.0.0.1", port), AetherBridgeHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando servidor puente...")
        server.shutdown()
