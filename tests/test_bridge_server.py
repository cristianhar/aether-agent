import time
import httpx
from bridge.server import start_bridge_server


def test_bridge_server_endpoints():
    # Iniciar servidor en puerto de prueba
    port = 18765
    server = start_bridge_server(host="127.0.0.1", port=port)
    time.sleep(0.5)

    base_url = f"http://127.0.0.1:{port}"

    try:
        with httpx.Client(base_url=base_url, timeout=10.0) as client:
            # 1. Chequeo de status
            res_status = client.get("/api/status")
            assert res_status.status_code == 200
            data_status = res_status.json()
            assert data_status["status"] == "online"
            assert "model" in data_status
            assert "session_id" in data_status

            # 2. Chequeo de árbol de repositorio
            res_tree = client.get("/api/tree")
            assert res_tree.status_code == 200
            assert "repo_map" in res_tree.json()

            # 3. Chequeo de diff
            res_diff = client.get("/api/diff")
            assert res_diff.status_code == 200
            assert "diff" in res_diff.json()

            # 3.1 Chequeo de artefactos, skills y subagentes
            res_arts = client.get("/api/artifacts")
            assert res_arts.status_code == 200
            assert "artifacts" in res_arts.json()

            res_skills = client.get("/api/skills")
            assert res_skills.status_code == 200
            assert "skills" in res_skills.json()

            res_subs = client.get("/api/subagents")
            assert res_subs.status_code == 200
            assert "subagents" in res_subs.json()

            # 3.2 Chequeo de preguntas pendientes
            res_q = client.get("/api/question/pending")
            assert res_q.status_code == 200
            assert "pending" in res_q.json()

            res_ans = client.post("/api/question/answer", json={"answers": [{"question": "test", "selected": ["opt1"]}]})
            assert res_ans.status_code == 200
            assert res_ans.json()["success"] is True

            # 3.3 Chequeo de endpoints de idioma y modo
            res_lang_get = client.get("/api/language")
            assert res_lang_get.status_code == 200
            assert res_lang_get.json()["language"] in ["es", "en"]

            res_lang_post = client.post("/api/language", json={"language": "en"})
            assert res_lang_post.status_code == 200
            assert res_lang_post.json()["language"] == "en"

            res_mode_post = client.post("/api/mode", json={"mode": "review"})
            assert res_mode_post.status_code == 200
            assert res_mode_post.json()["mode"] == "review"

            # 4. Chequeo de cancelación segura sin tarea activa
            res_cancel = client.post("/api/cancel", json={})
            assert res_cancel.status_code == 200
            assert res_cancel.json()["success"] is True

            # 5. Chequeo de slash commands
            res_vram = client.post("/api/chat", json={"prompt": "/vram"})
            assert res_vram.status_code == 200
            assert res_vram.json()["is_command"] is True

            res_mode = client.post("/api/chat", json={"prompt": "/mode plan"})
            assert res_mode.status_code == 200
            assert res_mode.json()["mode"] == "plan"

            res_cmd_skills = client.post("/api/chat", json={"prompt": "/skills"})
            assert res_cmd_skills.status_code == 200
            assert res_cmd_skills.json()["is_command"] is True

            res_cmd_subs = client.post("/api/chat", json={"prompt": "/subagents"})
            assert res_cmd_subs.status_code == 200
            assert res_cmd_subs.json()["is_command"] is True

            res_cmd_arts = client.post("/api/chat", json={"prompt": "/artifacts"})
            assert res_cmd_arts.status_code == 200
            assert res_cmd_arts.json()["is_command"] is True

            res_cmd_lang = client.post("/api/chat", json={"prompt": "/language es"})
            assert res_cmd_lang.status_code == 200
            assert res_cmd_lang.json()["is_command"] is True

            res_cmd_cancel = client.post("/api/chat", json={"prompt": "/cancel"})
            assert res_cmd_cancel.status_code == 200
            assert res_cmd_cancel.json()["is_command"] is True

    finally:
        server.shutdown()
        server.server_close()
