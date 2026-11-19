"""
Cliente del Protocolo de Contexto de Modelo (Model Context Protocol - MCP) para AETHER IDE.
Permite conectar servidores MCP locales y remotos vía stdio JSON-RPC 2.0,
descubrir herramientas dinámicas (tools/list) y ejecutarlas (tools/call).
Compatible con la especificación oficial de MCP (2024-11-05).
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MCPToolDefinition:
    name: str
    description: str
    input_schema: Dict[str, Any]
    server_name: str


class MCPStdioClient:
    """Cliente JSON-RPC 2.0 sobre transporte stdio para un servidor MCP."""

    def __init__(self, server_name: str, command: str, args: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None):
        self.server_name = server_name
        self.command = command
        self.args = args or []
        self.env = env
        self.process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._lock = threading.Lock()
        self.tools: Dict[str, MCPToolDefinition] = {}
        self.is_connected = False

    def start_and_initialize(self, timeout: float = 10.0) -> bool:
        """Inicia el subproceso del servidor MCP y realiza el handshake initialize."""
        full_cmd = [self.command] + self.args
        env_vars = os.environ.copy()
        if self.env:
            env_vars.update(self.env)

        try:
            self.process = subprocess.Popen(
                full_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                env=env_vars,
                bufsize=1,
            )
        except Exception as e:
            return False

        # 1. Enviar handshake initialize
        init_payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": True}
                },
                "clientInfo": {
                    "name": "aether-ide",
                    "version": "0.3.0"
                }
            }
        }

        resp = self._send_and_receive(init_payload, timeout=timeout)
        if not resp or "error" in resp:
            self.stop()
            return False

        # 2. Enviar notificación initialized
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        self._send_notification(initialized_notification)

        self.is_connected = True

        # 3. Descubrir catálogo de herramientas (tools/list)
        self.refresh_tools(timeout=timeout)
        return True

    def _next_id(self) -> int:
        with self._lock:
            self._request_id += 1
            return self._request_id

    def _send_and_receive(self, message: Dict[str, Any], timeout: float = 10.0) -> Optional[Dict[str, Any]]:
        """Envía un mensaje JSON-RPC y espera la respuesta correspondiente."""
        if not self.process or not self.process.stdin or not self.process.stdout:
            return None

        line = json.dumps(message, ensure_ascii=False) + "\n"
        with self._lock:
            try:
                self.process.stdin.write(line)
                self.process.stdin.flush()
            except Exception:
                return None

            # Leer respuesta
            try:
                # Lectura de línea stdout
                resp_line = self.process.stdout.readline()
                if resp_line:
                    return json.loads(resp_line.strip())
            except Exception:
                return None
        return None

    def _send_notification(self, message: Dict[str, Any]):
        """Envía una notificación sin esperar respuesta."""
        if not self.process or not self.process.stdin:
            return
        line = json.dumps(message, ensure_ascii=False) + "\n"
        with self._lock:
            try:
                self.process.stdin.write(line)
                self.process.stdin.flush()
            except Exception:
                pass

    def refresh_tools(self, timeout: float = 5.0) -> List[MCPToolDefinition]:
        """Envía tools/list y actualiza el diccionario interno de herramientas."""
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/list",
            "params": {}
        }
        resp = self._send_and_receive(req, timeout=timeout)
        if not resp or "result" not in resp:
            return []

        result_data = resp["result"]
        tools_list = result_data.get("tools", [])

        self.tools.clear()
        for t in tools_list:
            name = t.get("name", "")
            desc = t.get("description", "")
            schema = t.get("inputSchema", {})
            if name:
                self.tools[name] = MCPToolDefinition(
                    name=name,
                    description=desc,
                    input_schema=schema,
                    server_name=self.server_name
                )
        return list(self.tools.values())

    def call_tool(self, tool_name: str, arguments: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
        """Ejecuta una herramienta remota en el servidor MCP vía tools/call."""
        if not self.is_connected or not self.process:
            return {"success": False, "error": f"Servidor MCP '{self.server_name}' desconectado."}

        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        resp = self._send_and_receive(req, timeout=timeout)
        if not resp:
            return {"success": False, "error": f"Timeout o fallo en tools/call para '{tool_name}'"}

        if "error" in resp:
            err = resp["error"]
            err_msg = err.get("message", "Error desconocido del servidor MCP")
            return {"success": False, "error": err_msg}

        result = resp.get("result", {})
        is_error = result.get("isError", False)
        content_items = result.get("content", [])

        # Extraer texto de respuesta
        text_outputs = []
        for c in content_items:
            if isinstance(c, dict) and c.get("type") == "text":
                text_outputs.append(c.get("text", ""))
            elif isinstance(c, str):
                text_outputs.append(c)

        final_text = "\n".join(text_outputs) if text_outputs else str(result)

        return {
            "success": not is_error,
            "output": final_text,
            "raw": result
        }

    def stop(self):
        """Detiene de forma limpia el servidor MCP."""
        self.is_connected = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None


class MCPServerManager:
    """Gestor de múltiples servidores MCP configurados en .aether/mcp_servers.json."""

    _instance: Optional["MCPServerManager"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, workspace_root: Optional[Path] = None):
        if getattr(self, "_initialized", False):
            return
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.config_file = self.workspace_root / ".aether" / "mcp_servers.json"
        self.clients: Dict[str, MCPStdioClient] = {}
        self._initialized = True

    def add_server_config(self, name: str, command: str, args: Optional[List[str]] = None, env: Optional[Dict[str, str]] = None):
        """Registra la configuración de un servidor en .aether/mcp_servers.json."""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        configs = self._read_configs()
        configs[name] = {
            "command": command,
            "args": args or [],
            "env": env or {}
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(configs, f, indent=2, ensure_ascii=False)

    def _read_configs(self) -> Dict[str, Any]:
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def connect_all(self) -> Dict[str, bool]:
        """Inicia y conecta todos los servidores MCP configurados."""
        configs = self._read_configs()
        status = {}
        for name, cfg in configs.items():
            client = MCPStdioClient(
                server_name=name,
                command=cfg.get("command", ""),
                args=cfg.get("args", []),
                env=cfg.get("env")
            )
            ok = client.start_and_initialize()
            if ok:
                self.clients[name] = client
            status[name] = ok
        return status

    def list_all_tools(self) -> List[MCPToolDefinition]:
        """Retorna todas las herramientas descubiertas a través de todos los servidores MCP activos."""
        all_tools = []
        for client in self.clients.values():
            if client.is_connected:
                all_tools.extend(client.tools.values())
        return all_tools

    def call_mcp_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Invoca una herramienta en el servidor MCP indicado."""
        client = self.clients.get(server_name)
        if not client or not client.is_connected:
            return f"❌ Error: Servidor MCP '{server_name}' no está conectado o no existe."

        res = client.call_tool(tool_name, arguments)
        if res.get("success"):
            return f"✅ [MCP {server_name}/{tool_name}]:\n{res.get('output', '')}"
        return f"❌ Fallo en MCP {server_name}/{tool_name}: {res.get('error', 'Error desconocido')}"

    def shutdown_all(self):
        """Detiene todos los servidores MCP activos."""
        for client in self.clients.values():
            client.stop()
        self.clients.clear()


def list_mcp_tools() -> str:
    """Superpoder MCP: Descubre y lista todas las herramientas exportadas por servidores MCP conectados."""
    mgr = MCPServerManager()
    tools = mgr.list_all_tools()
    if not tools:
        return (
            "ℹ️ No hay servidores MCP conectados actualmente (configúralos en .aether/mcp_servers.json).\n"
            "• [AYUDA AUTOMÁTICA]: Si tu intención era consultar o listar los archivos o carpetas del proyecto local, "
            "debes llamar a 'list_directory(path=\".\")' o 'get_repo_map()'."
        )
    output = [f"🔌 **Herramientas MCP Descubiertas ({len(tools)} disponibles):**"]
    for t in tools:
        output.append(f"  • `{t.server_name}/{t.name}`: {t.description}")
    return "\n".join(output)


def call_mcp_tool_wrapper(server_name: str, tool_name: str, arguments: Any = None) -> str:
    """Superpoder MCP: Ejecuta una herramienta en un servidor MCP externo conectado."""
    mgr = MCPServerManager()
    args_dict = arguments if isinstance(arguments, dict) else {}
    return mgr.call_mcp_tool(server_name, tool_name, args_dict)

