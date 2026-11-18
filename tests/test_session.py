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


def test_semantic_memory_crud_and_search():
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_dir = Path(tmp_dir)
        sm = SessionManager(db_dir=db_dir)

        v1 = [1.0, 0.0, 0.0]
        v2 = [0.0, 1.0, 0.0]
        sm.store_semantic_memory(
            "jwt_secret",
            "El secreto de JWT debe leerse de la variable JWT_SECRET",
            category="security",
            embedding=v1,
        )
        sm.store_semantic_memory(
            "db_port",
            "El puerto de Postgres es 5432",
            category="infra",
            embedding=v2,
        )

        # Búsqueda vectorial
        res = sm.search_semantic_memory("jwt", top_k=2, query_embedding=[1.0, 0.0, 0.0])
        assert len(res) >= 1
        assert res[0]["key"] == "jwt_secret"
        assert res[0]["score"] > 0.9

        # Búsqueda léxica (fallback)
        res_lex = sm.search_semantic_memory("Postgres", top_k=1)
        assert len(res_lex) >= 1
        assert res_lex[0]["key"] == "db_port"

        # Listado
        all_mems = sm.get_all_semantic_memories()
        assert len(all_mems) == 2

        # Borrado
        deleted = sm.delete_semantic_memory("jwt_secret")
        assert deleted is True
        assert len(sm.get_all_semantic_memories()) == 1


def test_embeddings_math_helpers():
    from agent.embeddings import cosine_similarity, lexical_overlap_score

    # Coseno idéntico
    assert abs(cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) - 1.0) < 1e-5
    # Coseno ortogonal
    assert abs(cosine_similarity([1.0, 0.0], [0.0, 1.0])) < 1e-5
    # Longitudes distintas
    assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0
    # Vector cero
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    # Léxico
    score = lexical_overlap_score("hola mundo python", "mundo python desarrollo")
    assert score > 0.0

