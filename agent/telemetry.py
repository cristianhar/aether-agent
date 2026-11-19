"""
Módulo de Telemetría y Auditoría Estructurada para AETHER IDE.
Registra métricas de rendimiento, latencia de inferencia, uso de herramientas
y eventos de seguridad en .aether/telemetry.jsonl.
"""

from datetime import datetime
import json
from pathlib import Path
import threading
from typing import Any, Dict, Optional


class TelemetryLogger:
    """
    Logger de telemetría de alta eficiencia en formato JSON Lines.
    """

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.telemetry_dir = self.workspace_root / ".aether"
        self.telemetry_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.telemetry_dir / "telemetry.jsonl"
        self._lock = threading.Lock()

    def record_turn(
        self,
        session_id: str,
        turn_index: int,
        model: str,
        duration_seconds: float,
        tool_calls_count: int,
        tool_failures_count: int,
        user_prompt_length: int,
        agent_response_length: int,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Registra una interacción completa en el archivo de telemetría."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "event": "agent_turn",
            "session_id": session_id,
            "turn_index": turn_index,
            "model": model,
            "duration_seconds": round(duration_seconds, 3),
            "tool_calls_count": tool_calls_count,
            "tool_failures_count": tool_failures_count,
            "user_prompt_chars": user_prompt_length,
            "agent_response_chars": agent_response_length,
            "metadata": metadata or {},
        }
        self._write_record(record)

    def record_tool_execution(
        self,
        session_id: str,
        tool_name: str,
        category: str,
        duration_ms: float,
        success: bool,
        error: Optional[str] = None,
    ):
        """Registra la ejecución individual de una herramienta."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "event": "tool_execution",
            "session_id": session_id,
            "tool_name": tool_name,
            "category": category,
            "duration_ms": round(duration_ms, 2),
            "success": success,
            "error": error,
        }
        self._write_record(record)

    def _write_record(self, record: Dict[str, Any]):
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock:
            try:
                with open(self.log_file, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception:
                pass

    def get_summary(self) -> Dict[str, Any]:
        """Calcula un resumen estadístico de las ejecuciones registradas."""
        if not self.log_file.exists():
            return {
                "total_turns": 0,
                "total_tool_calls": 0,
                "tool_failures": 0,
                "tool_failure_rate": 0.0,
                "tool_failure_rate_percent": 0.0,
                "average_turn_duration_seconds": 0.0,
            }

        total_turns = 0
        total_duration = 0.0
        total_tools = 0
        total_failures = 0

        with self._lock:
            try:
                with open(self.log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            if data.get("event") == "agent_turn":
                                total_turns += 1
                                total_duration += data.get("duration_seconds", 0.0)
                            elif data.get("event") == "tool_execution":
                                total_tools += 1
                                if not data.get("success", True):
                                    total_failures += 1
                        except Exception:
                            continue
            except Exception:
                pass

        avg_duration = round(total_duration / total_turns, 2) if total_turns > 0 else 0.0
        failure_rate = round((total_failures / total_tools) * 100, 2) if total_tools > 0 else 0.0

        return {
            "total_turns": total_turns,
            "total_tool_calls": total_tools,
            "tool_failures": total_failures,
            "tool_failure_rate": failure_rate,
            "tool_failure_rate_percent": failure_rate,
            "average_turn_duration_seconds": avg_duration,
        }
