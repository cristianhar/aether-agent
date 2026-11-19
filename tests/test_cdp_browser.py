import base64
import json
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch

from tools.cdp_browser import (
    CDPBrowserController,
    MinimalWebSocket,
    browser_click,
    browser_get_content,
    browser_open,
    browser_screenshot,
    browser_type,
    find_chromium_binary,
    is_cdp_alive,
)
from tools.registry import execute_tool


def test_find_chromium_binary():
    # En esta máquina Windows, Chrome o Edge están instalados
    binary = find_chromium_binary()
    assert binary is not None
    assert binary.is_file()
    assert binary.name.lower() in ("chrome.exe", "msedge.exe")


def test_is_cdp_alive_mock():
    # Con un puerto que no está escuchando
    assert is_cdp_alive(port=59123) is False


def test_websocket_frame_roundtrip():
    # Probar codificación y decodificación de tramas sin red real
    mock_socket = MagicMock()

    # Simular handshake HTTP 101
    mock_socket.recv.side_effect = [
        b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n\r\n",
        # Simular trama de texto entrante del servidor CDP: opcode 1, longitud 5, 'hello'
        b"\x81\x05",
        b"hello",
    ]

    with patch("socket.create_connection", return_value=mock_socket):
        ws = MinimalWebSocket("ws://127.0.0.1:9222/devtools/page/1234")
        assert ws.sock is not None

        # Enviar mensaje
        ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
        assert mock_socket.sendall.called

        # Recibir mensaje
        msg = ws.recv()
        assert msg == "hello"

        ws.close()
        assert ws.sock is None


def test_cdp_browser_controller_mock_flow():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws_root = Path(tmp_dir)

        controller = CDPBrowserController(port=9222)

        # Mocking de _call_cdp_command y ensure_browser
        controller.ensure_browser = MagicMock(return_value=True)

        def mock_call(method, params=None):
            if method == "Page.navigate":
                return {"id": 1, "result": {"frameId": "F1"}}
            elif method == "Runtime.evaluate":
                expr = params.get("expression", "")
                if "document.title" in expr:
                    return {"id": 2, "result": {"result": {"value": "AETHER Testing Page"}}}
                elif "document.body" in expr:
                    return {"id": 3, "result": {"result": {"value": "Welcome to AETHER IDE Docs"}}}
                elif "CLICKED" in expr:
                    return {"id": 4, "result": {"result": {"value": "CLICKED"}}}
                elif "TYPED" in expr:
                    return {"id": 5, "result": {"result": {"value": "TYPED"}}}
            elif method == "Page.captureScreenshot":
                dummy_b64 = base64.b64encode(b"\x89PNG\r\n\x1a\nFakeImageData").decode("ascii")
                return {"id": 6, "result": {"data": dummy_b64}}
            return {"id": 99, "result": {}}

        controller._call_cdp_command = MagicMock(side_effect=mock_call)

        # 1. Navigate
        nav = controller.navigate("https://example.com")
        assert nav["success"] is True
        assert nav["title"] == "AETHER Testing Page"

        # 2. Get Content
        content = controller.get_content()
        assert "Welcome to AETHER IDE Docs" in content

        # 3. Click
        click_res = controller.click_element("button.cta")
        assert "Clic ejecutado exitosamente" in click_res

        # 4. Type
        type_res = controller.type_text("input#search", "query test")
        assert "Texto introducido" in type_res

        # 5. Screenshot
        shot_path = ws_root / "test_shot.png"
        shot_res = controller.take_screenshot(str(shot_path))
        assert "Captura de pantalla guardada" in shot_res
        assert shot_path.exists()
        assert shot_path.read_bytes().startswith(b"\x89PNG")


def test_high_level_browser_tools_dispatch():
    mock_ctrl = MagicMock()
    mock_ctrl.navigate.return_value = {"success": True, "url": "https://test.local", "title": "Local Test"}
    mock_ctrl.get_content.return_value = "Contenido de prueba local renderizado."
    mock_ctrl.click_element.return_value = "✅ Clic ejecutado en '#btn'."
    mock_ctrl.type_text.return_value = "✅ Texto introducido en '#inp'."
    mock_ctrl.take_screenshot.return_value = "📸 Captura guardada."

    with patch("tools.cdp_browser.get_global_cdp_browser", return_value=mock_ctrl):
        assert "Página cargada con éxito" in browser_open("https://test.local")
        assert "Contenido de prueba" in browser_get_content()
        assert "Clic ejecutado" in browser_click("#btn")
        assert "Texto introducido" in browser_type("#inp", "hola")
        assert "Captura guardada" in browser_screenshot()

        # Tool registry dispatch
        reg_nav = execute_tool("browser_open", {"url": "https://test.local"})
        assert "Página cargada con éxito" in reg_nav

        reg_click = execute_tool("click", {"selector": "#btn"})  # via alias
        assert "Clic ejecutado" in reg_click


def test_browser_fallback_when_unavailable():
    mock_ctrl = MagicMock()
    mock_ctrl.ensure_browser.return_value = False
    mock_ctrl.navigate.return_value = {"success": False, "error": "No se encontró Chrome o Edge instalado en el sistema."}

    with patch("tools.cdp_browser.get_global_cdp_browser", return_value=mock_ctrl):
        res = browser_open("https://google.com")
        assert "❌ Error abriendo" in res
        assert "No se encontró Chrome o Edge" in res
