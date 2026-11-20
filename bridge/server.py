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
from typing import Any, Dict, List, Optional
import urllib.parse

# Asegurar que la raíz del proyecto esté en sys.path independientemente de dónde se ejecute
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

def _safe_resolve(rel_path: str) -> Optional[Path]:
    """Resuelve rutas relativas contra _REPO_ROOT de manera segura y sin escapes de jaula."""
    if not rel_path:
        return None
    clean = rel_path.strip().replace("\\", "/").lstrip("/")
    target = (_REPO_ROOT / clean).resolve()
    if not str(target).startswith(str(_REPO_ROOT)):
        return None
    return target


def _list_workspace_files(root: Path) -> List[str]:
    """Lista todos los archivos navegables del proyecto excluyendo dependencias y cachés."""
    ignore_dirs = {".git", ".venv", "venv", "node_modules", ".pytest_cache", "__pycache__", "dist", "build", "target"}
    results = []
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ignore_dirs and not d.startswith(".")]
        for f in files:
            if f.startswith("."):
                continue
            full = Path(cur) / f
            rel = str(full.relative_to(root)).replace("\\", "/")
            results.append(rel)
    return sorted(results)

from agent.orchestrator import AgentOrchestrator
from agent.session import SessionManager
from agent.state import CancellationToken
from tools.git_tools import get_git_diff, get_git_status
from tools.repomap import generate_repo_map
from tools.vram_monitor import get_hardware_vram_status

_ACTIVE_ORCHESTRATOR: Optional[AgentOrchestrator] = None
_ACTIVE_TOKEN: Optional[CancellationToken] = None
_LOCK = threading.Lock()

# Soporte de preguntas interactivas (ask_question) para Desktop
_PENDING_QUESTION: Optional[List[Dict[str, Any]]] = None
_QUESTION_EVENT = threading.Event()
_QUESTION_ANSWER: Optional[List[Dict[str, Any]]] = None


def bridge_ask_question_callback(questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Intercepta preguntas interactivas para que el Desktop pueda responderlas."""
    global _PENDING_QUESTION, _QUESTION_ANSWER
    _PENDING_QUESTION = questions
    _QUESTION_EVENT.clear()
    _QUESTION_ANSWER = None

    # Esperar hasta 45 segundos la interacción del usuario en la UI
    answered = _QUESTION_EVENT.wait(timeout=45.0)
    if answered and _QUESTION_ANSWER:
        ans = _QUESTION_ANSWER
    else:
        # Fallback a opción recomendada
        ans = []
        for q in questions:
            opts = q.get("options", [])
            chosen = opts[0] if opts else "Sí"
            ans.append({"question": q.get("question", ""), "selected": [chosen]})

    _PENDING_QUESTION = None
    return ans


def get_or_create_orchestrator(model: str = "qwen2.5-coder:7b") -> AgentOrchestrator:
    global _ACTIVE_ORCHESTRATOR
    with _LOCK:
        if _ACTIVE_ORCHESTRATOR is None:
            from tools.agent_tools import set_ask_question_callback
            set_ask_question_callback(bridge_ask_question_callback)
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
            from agent.i18n import get_current_language
            vram = get_hardware_vram_status()
            self._send_json({
                "status": "online",
                "state": orch.state.value,
                "model": orch.model,
                "session_id": orch.session_id,
                "mode": getattr(orch.hooks, "mode", "agent"),
                "language": get_current_language(),
                "cwd": str(_REPO_ROOT),
                "vram_info": vram,
            })

        elif path == "/api/tree":
            repo_map = generate_repo_map(root_dir=str(_REPO_ROOT), max_files=80)
            file_list = _list_workspace_files(_REPO_ROOT)
            self._send_json({
                "cwd": str(_REPO_ROOT),
                "repo_map": repo_map,
                "files": file_list,
            })

        elif path == "/api/file":
            filepath_param = params.get("path", [""])[0]
            if not filepath_param:
                self._send_json({"error": "Parámetro 'path' requerido."}, 400)
                return

            p = _safe_resolve(filepath_param)
            if not p or not p.exists() or not p.is_file():
                self._send_json({"error": f"Archivo '{filepath_param}' no encontrado en el repositorio."}, 404)
                return

            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                rel_path = str(p.relative_to(_REPO_ROOT)).replace("\\", "/")
                self._send_json({"path": rel_path, "content": content})
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

        elif path == "/api/artifacts":
            from agent.artifacts import ArtifactManager
            mgr = ArtifactManager(session_id=orch.session_id)
            artifacts = mgr.list_artifacts()
            for a in artifacts:
                if "artifact_id" in a and "id" not in a:
                    a["id"] = a["artifact_id"]
            self._send_json({"artifacts": artifacts})

        elif path == "/api/artifact":
            art_id = params.get("id", [""])[0] or params.get("artifact_id", [""])[0]
            if not art_id or art_id == "undefined":
                self._send_json({"error": "Parámetro 'id' requerido."}, 400)
                return
            from agent.artifacts import ArtifactManager
            mgr = ArtifactManager(session_id=orch.session_id)
            try:
                data = mgr.read_artifact(art_id)
                self._send_json(data)
            except Exception as e:
                self._send_json({"error": str(e)}, 404)

        elif path == "/api/skills":
            from agent.skills import get_global_skill_registry
            reg = get_global_skill_registry()
            self._send_json({"skills": reg.list_skills()})

        elif path == "/api/subagents":
            from agent.subagents import get_global_subagent_manager
            mgr = get_global_subagent_manager()
            self._send_json({"subagents": mgr.list_subagents()})

        elif path == "/api/question/pending":
            self._send_json({
                "pending": _PENDING_QUESTION is not None,
                "questions": _PENDING_QUESTION or []
            })

        elif path == "/api/language":
            from agent.i18n import get_current_language
            self._send_json({"language": get_current_language()})

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
            active_file = body.get("active_file", "main.py")
            if not prompt:
                self._send_json({"error": "El campo 'prompt' es obligatorio."}, 400)
                return

            # Manejo directo de Slash Commands instantáneos
            if prompt.startswith("/"):
                cmd_parts = prompt.split(maxsplit=1)
                cmd = cmd_parts[0].lower()
                arg = cmd_parts[1].strip() if len(cmd_parts) > 1 else ""

                if cmd == "/test":
                    import subprocess
                    res = subprocess.run([sys.executable, "-m", "pytest", "-v"], cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=60)
                    out = res.stdout.strip()
                    tail = out[-1200:] if len(out) > 1200 else out
                    status_text = "✅ Todas las pruebas pasaron exitosamente." if res.returncode == 0 else "❌ Se detectaron fallos en las pruebas."
                    answer = f"🧪 **Resultados de las pruebas automatizadas (pytest):**\n```text\n{tail}\n```\n{status_text}"
                    self._send_json({"success": True, "answer": answer, "state": "IDLE", "session_id": orch.session_id, "is_command": True})
                    return

                elif cmd == "/diff":
                    diff = get_git_diff()
                    st = get_git_status()
                    answer = f"📋 **Estado de Git y Cambios:**\n```text\n{st}\n```\n```diff\n{diff or '# No hay cambios pendientes de commit.'}\n```"
                    self._send_json({"success": True, "answer": answer, "state": "IDLE", "session_id": orch.session_id, "is_command": True, "action": "open_diff"})
                    return

                elif cmd == "/vram":
                    vram = get_hardware_vram_status()
                    self._send_json({"success": True, "answer": vram, "state": "IDLE", "session_id": orch.session_id, "is_command": True})
                    return

                elif cmd == "/mode":
                    target_mode = arg.lower() or "agent"
                    if target_mode in ["ask", "agent", "plan", "review"]:
                        orch.hooks.set_mode(target_mode)
                        desc = {
                            "agent": "Modo Autónomo Total (lectura, escritura y ejecución libre de herramientas).",
                            "ask": "Modo Seguro (requiere confirmación para modificar archivos y ejecutar comandos).",
                            "plan": "Modo Planificador (solo análisis arquitectónico y razonamiento, sin modificar archivos).",
                            "review": "Modo Auditoría AST y Code Review riguroso."
                        }.get(target_mode, "")
                        answer = f"🛡️ **Modo cambiado a `{target_mode.upper()}`:**\n{desc}"
                        self._send_json({"success": True, "answer": answer, "state": "IDLE", "session_id": orch.session_id, "mode": target_mode, "is_command": True})
                        return
                    else:
                        answer = "⚠️ Modo no reconocido. Opciones válidas: `/mode agent`, `/mode ask`, `/mode plan`, `/mode review`."
                        self._send_json({"success": True, "answer": answer, "state": "IDLE", "session_id": orch.session_id, "is_command": True})
                        return

                elif cmd in ["/cancel", "/stop"]:
                    with _LOCK:
                        if _ACTIVE_TOKEN:
                            _ACTIVE_TOKEN.cancel("Cancelado por comando.")
                    self._send_json({"success": True, "answer": "🛑 Tarea activa cancelada con éxito.", "state": "IDLE", "session_id": orch.session_id, "is_command": True})
                    return

                elif cmd == "/language":
                    from agent.i18n import set_current_language, get_current_language
                    target = arg.lower()
                    if target in ["es", "en"]:
                        set_current_language(target)
                        ans = f"🌐 Idioma del sistema actualizado a **{target.upper()}**."
                    else:
                        ans = f"🌐 Idioma actual: **{get_current_language().upper()}**.\nUsa `/language es` o `/language en`."
                    self._send_json({"success": True, "answer": ans, "state": "IDLE", "session_id": orch.session_id, "language": get_current_language(), "is_command": True})
                    return

                elif cmd == "/skills":
                    from agent.skills import get_global_skill_registry
                    reg = get_global_skill_registry()
                    skills = reg.list_skills()
                    if not skills:
                        ans = "ℹ️ No hay habilidades (skills) registradas en el catálogo."
                    else:
                        lines = ["🧩 **Habilidades (Skills) Disponibles:**\n"]
                        for s in skills:
                            lines.append(f"- **`{s.get('name')}`** (v{s.get('version', '1.0')}): {s.get('description', 'Sin descripción')}")
                        ans = "\n".join(lines)
                    self._send_json({"success": True, "answer": ans, "state": "IDLE", "session_id": orch.session_id, "is_command": True})
                    return

                elif cmd == "/subagents":
                    from agent.subagents import get_global_subagent_manager
                    mgr = get_global_subagent_manager()
                    subs = mgr.list_subagents()
                    if not subs:
                        ans = "ℹ️ No hay subagentes activos ni definidos en la sesión actual."
                    else:
                        lines = ["🤖 **Subagentes Activos:**\n"]
                        for s in subs:
                            lines.append(f"- **`{s.get('id')}`** [{s.get('role')}]: Estado `{s.get('status')}`")
                        ans = "\n".join(lines)
                    self._send_json({"success": True, "answer": ans, "state": "IDLE", "session_id": orch.session_id, "is_command": True})
                    return

                elif cmd == "/artifacts":
                    from agent.artifacts import ArtifactManager
                    mgr = ArtifactManager(session_id=orch.session_id)
                    arts = mgr.list_artifacts()
                    if not arts:
                        ans = "ℹ️ No se han generado artefactos persistentes en esta sesión."
                    else:
                        lines = ["📦 **Artefactos en esta sesión:**\n"]
                        for a in arts:
                            lines.append(f"- **`{a.get('id')}`** ({a.get('type')}): {a.get('title')}")
                        ans = "\n".join(lines)
                    self._send_json({"success": True, "answer": ans, "state": "IDLE", "session_id": orch.session_id, "is_command": True})
                    return

                elif cmd == "/checkpoint":
                    from agent.checkpoints import SafeCheckpointManager
                    desc = arg or "Snapshot manual desde Desktop"
                    cm = SafeCheckpointManager(workspace_root=str(_REPO_ROOT))
                    chk_id = cm.create_checkpoint(description=desc)
                    answer = f"💾 **Punto de restauración seguro creado con éxito:**\n- **ID:** `{chk_id}`\n- **Descripción:** {desc}"
                    self._send_json({"success": True, "answer": answer, "state": "IDLE", "session_id": orch.session_id, "is_command": True})
                    return

                elif cmd == "/undo":
                    from agent.checkpoints import SafeCheckpointManager
                    cm = SafeCheckpointManager(workspace_root=str(_REPO_ROOT))
                    checkpoints = cm.list_checkpoints()
                    if not checkpoints:
                        answer = "⚠️ No hay checkpoints disponibles para restaurar."
                    else:
                        last_id = checkpoints[-1]["snapshot_id"]
                        res = cm.restore_checkpoint(last_id, force=True)
                        answer = f"⏪ **Restauración completada al checkpoint `{last_id}`:**\n{res}"
                    self._send_json({"success": True, "answer": answer, "state": "IDLE", "session_id": orch.session_id, "is_command": True, "action": "reload_file"})
                    return

                elif cmd == "/review":
                    from agent.skills import SkillRegistry
                    target = arg or active_file or "main.py"
                    review_res = SkillRegistry().run_code_review(target)
                    self._send_json({"success": True, "answer": review_res, "state": "IDLE", "session_id": orch.session_id, "is_command": True})
                    return

            with _LOCK:
                if _ACTIVE_TOKEN and not _ACTIVE_TOKEN.is_cancelled:
                    _ACTIVE_TOKEN.cancel("Cancelado por nuevo turno de usuario.")
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
            finally:
                with _LOCK:
                    if _ACTIVE_TOKEN is token:
                        _ACTIVE_TOKEN = None

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

            p = _safe_resolve(filepath)
            if not p:
                self._send_json({"error": f"Ruta '{filepath}' no permitida fuera del repositorio."}, 403)
                return

            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8", newline="")
                rel_path = str(p.relative_to(_REPO_ROOT)).replace("\\", "/")
                self._send_json({"success": True, "path": rel_path, "message": f"Archivo '{p.name}' guardado correctamente."})
            except Exception as e:
                self._send_json({"success": False, "error": str(e)}, 500)

        elif path == "/api/question/answer":
            global _QUESTION_ANSWER
            answers = body.get("answers", [])
            _QUESTION_ANSWER = answers
            _QUESTION_EVENT.set()
            self._send_json({"success": True, "message": "Respuesta enviada al agente."})

        elif path == "/api/language":
            from agent.i18n import set_current_language
            target = body.get("language", "").lower()
            if target in ["es", "en"]:
                set_current_language(target)
                self._send_json({"success": True, "language": target})
            else:
                self._send_json({"error": "Idioma no soportado. Usa 'es' o 'en'."}, 400)

        elif path == "/api/mode":
            mode = body.get("mode", "").lower()
            if mode in ["agent", "ask", "plan", "review"]:
                orch.hooks.set_mode(mode)
                self._send_json({"success": True, "mode": mode})
            else:
                self._send_json({"error": "Modo inválido. Opciones: agent, ask, plan, review"}, 400)

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
