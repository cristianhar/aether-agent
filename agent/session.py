"""
Gestor de sesiones y persistencia transaccional con SQLite para AETHER IDE.
Permite reanudar tareas interrumpidas, auditar llamadas a herramientas y mantener estado entre reinicios.
Garantiza el cierre adecuado de conexiones para evitar bloqueos en Windows.
"""

from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
import uuid


class SessionManager:
    def __init__(self, db_dir: Optional[Path] = None):
        base_dir = db_dir or (Path.cwd() / ".aether")
        base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = base_dir / "sessions.db"
        self._init_db()

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self):
        with self._connection() as conn:
            cursor = conn.cursor()
            # Tabla de sesiones
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                state TEXT NOT NULL,
                model TEXT NOT NULL,
                cwd TEXT NOT NULL,
                metadata_json TEXT DEFAULT '{}'
            )
            """)
            # Tabla de mensajes de conversación
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_index INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT DEFAULT '',
                tool_calls_json TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions (session_id)
            )
            """)
            # Tabla de auditoría de herramientas
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS tool_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                args_json TEXT NOT NULL,
                result_json TEXT NOT NULL,
                success INTEGER NOT NULL,
                latency_ms REAL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions (session_id)
            )
            """)
            # Tabla de checkpoints de seguridad
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                snapshot_id TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT '',
                files_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions (session_id)
            )
            """)

    def create_session(self, model: str = "qwen2.5-coder:7b", cwd: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
        session_id = f"ses_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        now = datetime.now().isoformat()
        cwd_str = str(Path(cwd).resolve()) if cwd else str(Path.cwd().resolve())

        with self._connection() as conn:
            conn.execute(
                "INSERT INTO sessions (session_id, created_at, updated_at, state, model, cwd, metadata_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, now, now, "IDLE", model, cwd_str, json.dumps(metadata or {}))
            )
        return session_id

    def update_session_state(self, session_id: str, state: str):
        now = datetime.now().isoformat()
        with self._connection() as conn:
            conn.execute(
                "UPDATE sessions SET state = ?, updated_at = ? WHERE session_id = ?",
                (state, now, session_id)
            )

    def save_message(self, session_id: str, turn_index: int, role: str, content: str = "", tool_calls: Optional[List[Dict[str, Any]]] = None):
        now = datetime.now().isoformat()
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, turn_index, role, content, tool_calls_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, turn_index, role, content, json.dumps(tool_calls or []), now)
            )
            conn.execute("UPDATE sessions SET updated_at = ? WHERE session_id = ?", (now, session_id))

    def record_tool_execution(
        self,
        session_id: str,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
        success: bool = True,
        latency_ms: float = 0.0
    ):
        now = datetime.now().isoformat()
        result_str = str(result)
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO tool_executions (session_id, tool_name, args_json, result_json, success, latency_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (session_id, tool_name, json.dumps(args), result_str, 1 if success else 0, latency_ms, now)
            )

    def get_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT role, content, tool_calls_json FROM messages WHERE session_id = ? ORDER BY id ASC",
                (session_id,)
            ).fetchall()

        messages = []
        for r in rows:
            msg: Dict[str, Any] = {"role": r["role"], "content": r["content"]}
            tc = json.loads(r["tool_calls_json"])
            if tc:
                msg["tool_calls"] = tc
            messages.append(msg)
        return messages

    def list_sessions(self, limit: int = 15) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT session_id, created_at, updated_at, state, model, cwd FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def record_checkpoint(self, session_id: str, snapshot_id: str, description: str, files: List[str]):
        now = datetime.now().isoformat()
        with self._connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO checkpoints (session_id, snapshot_id, description, files_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, snapshot_id, description, json.dumps(files), now)
            )
