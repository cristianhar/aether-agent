"""
Pruebas exhaustivas para el Cliente del Protocolo de Contexto de Modelo (MCP) en AETHER IDE.
Valida:
1. Conexión y Handshake JSON-RPC 2.0 ('initialize')
2. Descubrimiento de herramientas ('tools/list')
3. Ejecución de herramientas ('tools/call')
4. Manejo de errores y desconexión limpia
"""

import json
import sys
import tempfile
from pathlib import Path
from tools.mcp_client import MCPStdioClient, MCPServerManager, list_mcp_tools, call_mcp_tool_wrapper

# Script que actúa como servidor MCP sobre stdio
MOCK_MCP_SERVER_CODE = """
import sys
import json

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        msg = json.loads(line)
    except Exception:
        continue

    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        resp = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "mock-mcp-server", "version": "1.0.0"}
            }
        }
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()

    elif method == "tools/list":
        resp = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [
                    {
                        "name": "echo",
                        "description": "Retorna el texto enviado",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"message": {"type": "string"}},
                            "required": ["message"]
                        }
                    },
                    {
                        "name": "add",
                        "description": "Suma dos números",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                            "required": ["a", "b"]
                        }
                    }
                ]
            }
        }
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()

    elif method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "echo":
            out = f"ECHO: {args.get('message', '')}"
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": out}],
                    "isError": False
                }
            }
        elif tool_name == "add":
            total = args.get("a", 0) + args.get("b", 0)
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": str(total)}],
                    "isError": False
                }
            }
        else:
            resp = {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Herramienta '{tool_name}' no encontrada"}
            }
        sys.stdout.write(json.dumps(resp) + "\\n")
        sys.stdout.flush()
"""


def test_mcp_stdio_client_lifecycle():
    with tempfile.TemporaryDirectory() as tmp_dir:
        server_script = Path(tmp_dir) / "server.py"
        server_script.write_text(MOCK_MCP_SERVER_CODE, encoding="utf-8")

        client = MCPStdioClient(
            server_name="test-server",
            command=sys.executable,
            args=[str(server_script)]
        )

        try:
            # 1. Iniciar y handshake initialize
            connected = client.start_and_initialize(timeout=5.0)
            assert connected is True
            assert client.is_connected is True

            # 2. Verificar descubrimiento de herramientas (tools/list)
            assert "echo" in client.tools
            assert "add" in client.tools
            assert client.tools["echo"].description == "Retorna el texto enviado"

            # 3. Ejecutar herramientas (tools/call)
            res_echo = client.call_tool("echo", {"message": "Hola MCP!"})
            assert res_echo["success"] is True
            assert "ECHO: Hola MCP!" in res_echo["output"]

            res_add = client.call_tool("add", {"a": 25, "b": 75})
            assert res_add["success"] is True
            assert "100" in res_add["output"]

            # 4. Error en herramienta inexistente
            res_bad = client.call_tool("nonexistent", {})
            assert res_bad["success"] is False
            assert "no encontrada" in res_bad["error"]

        finally:
            client.stop()
            assert client.is_connected is False


def test_mcp_server_manager_integration():
    with tempfile.TemporaryDirectory() as tmp_dir:
        ws = Path(tmp_dir)
        server_script = ws / "mcp_srv.py"
        server_script.write_text(MOCK_MCP_SERVER_CODE, encoding="utf-8")

        mgr = MCPServerManager(workspace_root=ws)
        # Registrar servidor en la configuración
        mgr.add_server_config(
            name="local_mock",
            command=sys.executable,
            args=[str(server_script)]
        )

        try:
            status = mgr.connect_all()
            assert status.get("local_mock") is True

            tools = mgr.list_all_tools()
            tool_names = [t.name for t in tools]
            assert "echo" in tool_names
            assert "add" in tool_names

            # Llamar a través del wrapper del gestor
            output = mgr.call_mcp_tool("local_mock", "add", {"a": 10, "b": 20})
            assert "30" in output
            assert "✅ [MCP local_mock/add]" in output

        finally:
            mgr.shutdown_all()
