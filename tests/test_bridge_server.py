import json
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
        with httpx.Client(base_url=base_url, timeout=5.0) as client:
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

            # 4. Chequeo de cancelación segura sin tarea activa
            res_cancel = client.post("/api/cancel", json={})
            assert res_cancel.status_code == 200
            assert res_cancel.json()["success"] is True

    finally:
        server.shutdown()
