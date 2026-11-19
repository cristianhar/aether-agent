"""
Navegación Web Ligera vía Chrome DevTools Protocol (CDP) para AETHER IDE.
100% CERO Playwright y CERO dependencias pesadas:
- Conexión nativa mediante protocolo WebSocket (RFC 6455) sobre sockets estándar de Python.
- Utiliza la instalación local existente de Google Chrome o Microsoft Edge.
- Soporta renderizado dinámico de JavaScript, clics en elementos, tipeo de texto y capturas de pantalla.
"""

import base64
from datetime import datetime
import json
import os
from pathlib import Path
import platform
import socket
import struct
import subprocess
import time
from typing import Any, Dict, List, Optional
import urllib.parse
import urllib.request


def find_chromium_binary(custom_candidates: Optional[List[Path]] = None) -> Optional[Path]:
    """Localiza el binario ejecutable de Google Chrome o Microsoft Edge en el sistema."""
    if custom_candidates is not None:
        for p in custom_candidates:
            if p.is_file():
                return p
        return None

    system = platform.system()

    if system == "Windows":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "C:\\Users")) / "Google" / "Chrome" / "Application" / "chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        ]
    elif system == "Darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
    else:  # Linux / Unix
        candidates = [
            Path("/usr/bin/google-chrome"),
            Path("/usr/bin/google-chrome-stable"),
            Path("/usr/bin/chromium"),
            Path("/usr/bin/chromium-browser"),
            Path("/usr/bin/microsoft-edge"),
        ]

    for p in candidates:
        if p.is_file():
            return p
    return None


def is_cdp_alive(port: int = 9222, host: str = "127.0.0.1") -> bool:
    """Verifica de forma ultra-rápida (socket TCP sin spawn) si el puerto CDP está abierto."""
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except (OSError, ConnectionRefusedError):
        return False


class MinimalWebSocket:
    """
    Cliente WebSocket RFC 6455 minimalista implementado en sockets Python puros.
    Cero dependencias externas para máxima portabilidad y velocidad.
    """

    def __init__(self, ws_url: str, timeout: float = 8.0):
        self.ws_url = ws_url
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self._connect()

    def _connect(self):
        clean = self.ws_url.replace("ws://", "").replace("wss://", "")
        parts = clean.split("/", 1)
        host_port = parts[0].split(":")
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 80
        path = "/" + parts[1] if len(parts) > 1 else "/"

        self.sock = socket.create_connection((host, port), timeout=self.timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")

        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        self.sock.sendall(handshake.encode("ascii"))

        header_buf = b""
        while b"\r\n\r\n" not in header_buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("Fallo en el handshake de WebSocket con Chrome CDP.")
            header_buf += chunk

        first_line = header_buf.splitlines()[0].decode("ascii", errors="replace")
        if " 101 " not in first_line:
            raise ConnectionError(f"Chrome CDP rechazó la actualización WebSocket: {first_line}")

    def send(self, message: str):
        if not self.sock:
            raise ConnectionError("Socket no conectado.")

        payload = message.encode("utf-8")
        length = len(payload)
        header = bytearray([0x81])  # FIN + Opcode 1 (text)
        mask = os.urandom(4)

        if length <= 125:
            header.append(0x80 | length)
        elif length <= 65535:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))

        header.extend(mask)
        masked_payload = bytearray(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(header + masked_payload)

    def recv(self) -> str:
        if not self.sock:
            raise ConnectionError("Socket no conectado.")

        def recv_exact(n: int) -> bytes:
            buf = bytearray()
            while len(buf) < n:
                chunk = self.sock.recv(n - len(buf))
                if not chunk:
                    raise ConnectionError("Conexión cerrada por el servidor CDP.")
                buf.extend(chunk)
            return bytes(buf)

        while True:
            b0, b1 = struct.unpack("!BB", recv_exact(2))
            opcode = b0 & 0x0F
            is_masked = bool(b1 & 0x80)
            plen = b1 & 0x7F

            if plen == 126:
                plen = struct.unpack("!H", recv_exact(2))[0]
            elif plen == 127:
                plen = struct.unpack("!Q", recv_exact(8))[0]

            mask_key = recv_exact(4) if is_masked else None
            data = recv_exact(plen)
            if is_masked and mask_key:
                data = bytes(b ^ mask_key[i % 4] for i, b in enumerate(data))

            # Opcode 1 = Text frame
            if opcode == 1:
                return data.decode("utf-8", errors="replace")
            # Opcode 8 = Close frame
            elif opcode == 8:
                self.close()
                raise ConnectionResetError("Servidor CDP cerró la conexión WebSocket.")

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None


class CDPBrowserController:
    """Controlador de automatización de navegador ligero mediante Chrome DevTools Protocol."""

    def __init__(self, port: int = 9222, host: str = "127.0.0.1"):
        self.port = port
        self.host = host
        self.browser_proc: Optional[subprocess.Popen] = None
        self.ws_client: Optional[MinimalWebSocket] = None
        self.target_id: Optional[str] = None
        self.msg_id_counter = 0

    def ensure_browser(self, headless: bool = True) -> bool:
        """Asegura que el navegador Chromium esté ejecutándose con el puerto de depuración activo."""
        if is_cdp_alive(self.port, self.host):
            return True

        binary = find_chromium_binary()
        if not binary:
            return False

        profile_dir = Path.home() / ".aether" / "cdp_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)

        args = [
            str(binary),
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={profile_dir}",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-sync",
        ]
        if headless:
            args.append("--headless=new")

        try:
            self.browser_proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            return False

        # Esperar hasta 4 segundos a que el socket responda
        for _ in range(40):
            time.sleep(0.1)
            if is_cdp_alive(self.port, self.host):
                return True
        return False

    def _call_cdp_command(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Envía un comando JSON-RPC al tab activo y espera su respuesta sincronizada."""
        if not self.ws_client:
            self._connect_active_tab()

        self.msg_id_counter += 1
        call_id = self.msg_id_counter
        payload = {"id": call_id, "method": method, "params": params or {}}

        self.ws_client.send(json.dumps(payload))

        start = time.time()
        while time.time() - start < 10.0:
            raw = self.ws_client.recv()
            try:
                data = json.loads(raw)
                if data.get("id") == call_id:
                    return data
            except Exception:
                pass
        return {"error": {"message": f"Timeout esperando respuesta para {method} (id={call_id})"}}

    def _connect_active_tab(self):
        """Conecta el cliente WebSocket a la pestaña activa o crea una nueva."""
        url_list = f"http://{self.host}:{self.port}/json/list"
        req = urllib.request.Request(url_list)
        try:
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                tabs = json.loads(resp.read().decode("utf-8"))
        except Exception:
            tabs = []

        page_tabs = [t for t in tabs if t.get("type") == "page"]
        if page_tabs:
            chosen = page_tabs[0]
        else:
            # Crear nueva pestaña
            url_new = f"http://{self.host}:{self.port}/json/new?about:blank"
            req_new = urllib.request.Request(url_new, method="PUT")
            with urllib.request.urlopen(req_new, timeout=2.0) as resp_new:
                chosen = json.loads(resp_new.read().decode("utf-8"))

        self.target_id = chosen.get("id")
        ws_url = chosen.get("webSocketDebuggerUrl")
        if not ws_url:
            raise ConnectionError("No se obtuvo webSocketDebuggerUrl del tab CDP.")

        self.ws_client = MinimalWebSocket(ws_url)
        # Habilitar dominios clave
        self.ws_client.send(json.dumps({"id": 9991, "method": "Page.enable"}))
        self.ws_client.send(json.dumps({"id": 9992, "method": "Runtime.enable"}))

    def navigate(self, url: str) -> Dict[str, Any]:
        """Navega a la URL especificada y espera la estabilización de carga del DOM."""
        if not self.ensure_browser():
            return {"success": False, "error": "No se encontró Chrome o Edge instalado en el sistema."}

        target_url = url.strip()
        if not target_url.startswith(("http://", "https://", "file://", "about:")):
            target_url = f"https://{target_url}"

        res = self._call_cdp_command("Page.navigate", {"url": target_url})
        if "error" in res:
            return {"success": False, "error": res["error"].get("message", "Error de navegación")}

        time.sleep(1.0)  # Breve margen para estabilización de renderizado

        title_res = self._call_cdp_command("Runtime.evaluate", {"expression": "document.title"})
        title = title_res.get("result", {}).get("result", {}).get("value", "")

        return {
            "success": True,
            "url": target_url,
            "title": title or "Sin título",
        }

    def get_content(self, selector: Optional[str] = None, max_chars: int = 4000) -> str:
        """Extrae el contenido textual legible del DOM tras el renderizado de JavaScript."""
        if not self.ensure_browser():
            return "❌ Error: Navegador no disponible."

        if selector:
            expr = f"document.querySelector('{selector}') ? document.querySelector('{selector}').innerText : 'Elemento no encontrado'"
        else:
            expr = "document.body ? document.body.innerText : ''"

        res = self._call_cdp_command("Runtime.evaluate", {"expression": expr})
        val = res.get("result", {}).get("result", {}).get("value", "")
        if not val:
            return "(Página vacía o sin contenido textual renderizado)"

        if len(val) > max_chars:
            return val[:max_chars] + f"\n\n... [Truncado a {max_chars} caracteres de {len(val)}]"
        return val

    def click_element(self, selector: str) -> str:
        """Ejecuta un clic sobre el elemento que coincida con el selector CSS."""
        if not self.ensure_browser():
            return "❌ Error: Navegador no disponible."

        expr = f"""
        (() => {{
            const el = document.querySelector('{selector}');
            if (!el) return 'NOT_FOUND';
            el.scrollIntoView({{ behavior: 'instant', block: 'center' }});
            el.click();
            return 'CLICKED';
        }})()
        """
        res = self._call_cdp_command("Runtime.evaluate", {"expression": expr})
        val = res.get("result", {}).get("result", {}).get("value", "")
        if val == "CLICKED":
            time.sleep(0.5)
            return f"✅ Clic ejecutado exitosamente en '{selector}'."
        elif val == "NOT_FOUND":
            return f"❌ No se encontró ningún elemento en la página con el selector '{selector}'."
        return f"⚠️ Resultado del clic en '{selector}': {val}"

    def type_text(self, selector: str, text: str) -> str:
        """Introduce texto en un campo de formulario o input y despacha eventos de cambio."""
        if not self.ensure_browser():
            return "❌ Error: Navegador no disponible."

        escaped = json.dumps(text)
        expr = f"""
        (() => {{
            const el = document.querySelector('{selector}');
            if (!el) return 'NOT_FOUND';
            el.focus();
            el.value = {escaped};
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            return 'TYPED';
        }})()
        """
        res = self._call_cdp_command("Runtime.evaluate", {"expression": expr})
        val = res.get("result", {}).get("result", {}).get("value", "")
        if val == "TYPED":
            return f"✅ Texto introducido en '{selector}' ({len(text)} caracteres)."
        elif val == "NOT_FOUND":
            return f"❌ No se encontró el campo con selector '{selector}'."
        return f"⚠️ Resultado de escritura en '{selector}': {val}"

    def take_screenshot(self, output_path: Optional[str] = None) -> str:
        """Captura de pantalla visual de la página activa y guardado en disco."""
        if not self.ensure_browser():
            return "❌ Error: Navegador no disponible."

        res = self._call_cdp_command("Page.captureScreenshot", {"format": "png"})
        b64_data = res.get("result", {}).get("data", "")
        if not b64_data:
            return "❌ Error al capturar la imagen de la pantalla mediante CDP."

        img_bytes = base64.b64decode(b64_data)

        if output_path:
            dest = Path(output_path).resolve()
        else:
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest = Path.cwd() / ".aether" / "screenshots" / f"screenshot_{stamp}.png"

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(img_bytes)
        return f"📸 Captura de pantalla guardada exitosamente en: `{dest}` ({len(img_bytes)} bytes)."

    def close(self):
        """Cierra el socket y termina el subproceso del navegador si fue abierto por AETHER."""
        if self.ws_client:
            self.ws_client.close()
            self.ws_client = None

        if self.browser_proc:
            try:
                self.browser_proc.terminate()
                self.browser_proc.wait(timeout=2.0)
            except Exception:
                pass
            self.browser_proc = None


_GLOBAL_CDP_BROWSER: Optional[CDPBrowserController] = None


def get_global_cdp_browser() -> CDPBrowserController:
    """Obtiene o crea la instancia global del controlador CDP."""
    global _GLOBAL_CDP_BROWSER
    if _GLOBAL_CDP_BROWSER is None:
        _GLOBAL_CDP_BROWSER = CDPBrowserController()
    return _GLOBAL_CDP_BROWSER


# --- Herramientas de Alto Nivel para el Agente LLM ---

def browser_open(url: str) -> str:
    """
    [NAVEGADOR CDP] Abre y navega a una URL en el navegador Chrome/Edge local.
    Soporta sitios dinámicos JavaScript (React, Vue, SPAs). CERO Playwright.
    """
    ctrl = get_global_cdp_browser()
    res = ctrl.navigate(url)
    if not res.get("success"):
        return f"❌ Error abriendo '{url}': {res.get('error')}"
    return f"🌐 Página cargada con éxito:\n• URL: {res['url']}\n• Título: {res['title']}"


def browser_get_content(selector: Optional[str] = None, max_chars: int = 4000) -> str:
    """
    [NAVEGADOR CDP] Extrae el texto legible de la página activa o de un selector específico.
    """
    ctrl = get_global_cdp_browser()
    return ctrl.get_content(selector=selector, max_chars=max_chars)


def browser_click(selector: str) -> str:
    """
    [NAVEGADOR CDP] Hace clic en un botón, enlace o elemento interactivo por selector CSS.
    """
    ctrl = get_global_cdp_browser()
    return ctrl.click_element(selector)


def browser_type(selector: str, text: str) -> str:
    """
    [NAVEGADOR CDP] Escribe texto en un campo de entrada o formulario por selector CSS.
    """
    ctrl = get_global_cdp_browser()
    return ctrl.type_text(selector, text)


def browser_screenshot(output_path: Optional[str] = None) -> str:
    """
    [NAVEGADOR CDP] Toma una captura de pantalla visual PNG de la página web actual.
    """
    ctrl = get_global_cdp_browser()
    return ctrl.take_screenshot(output_path)
