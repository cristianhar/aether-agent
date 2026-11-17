import tempfile
from pathlib import Path
from agent.session import SessionManager


def test_session_manager_lifecycle():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_dir = Path(tmp_dir)
        sm = SessionManager(db_dir=db_dir)

        # 1. Crear sesión
        session_id = sm.create_session(model="qwen2.5-coder:7b", cwd=str(db_dir))
        assert session_id.startswith("ses_")

        # 2. Actualizar estado
        sm.update_session_state(session_id, "RUNNING")

        # 3. Guardar mensajes
        sm.save_message(session_id, turn_index=1, role="user", content="Hola AETHER")
        sm.save_message(session_id, turn_index=1, role="assistant", content="Hola, en qué te ayudo?", tool_calls=[])

        # 4. Registrar ejecución de herramienta
        sm.record_tool_execution(
            session_id=session_id,
            tool_name="read_file",
            args={"path": "main.py"},
            result="print('ok')",
            success=True,
            latency_ms=12.5,
        )

        # 5. Recuperar mensajes
        msgs = sm.get_session_messages(session_id)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == "Hola AETHER"
        assert msgs[1]["role"] == "assistant"

        # 6. Listar sesiones
        sessions = sm.list_sessions()
        assert len(sessions) >= 1
        assert sessions[0]["session_id"] == session_id
        assert sessions[0]["state"] == "RUNNING"
