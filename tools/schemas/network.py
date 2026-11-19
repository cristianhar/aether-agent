"""
Esquemas de herramientas para el dominio: Network.
"""

from typing import Any, Dict, List

NETWORK_TOOLS: List[Dict[str, Any]] = [
    {
        "function": {
            "description": "Superpoder: Realiza una búsqueda web en tiempo real para encontrar documentación técnica de librerías, foros o ejemplos de código.",
            "name": "search_web",
            "parameters": {
                "properties": {
                    "max_results": {
                        "description": "Cantidad de resultados a retornar (por defecto 5).",
                        "type": "integer"
                    },
                    "query": {
                        "description": "Término o pregunta técnica a buscar.",
                        "type": "string"
                    }
                },
                "required": [
                    "query"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "Superpoder: Descarga y extrae el texto limpio y legible de una URL o documentación técnica en la web.",
            "name": "fetch_web_page",
            "parameters": {
                "properties": {
                    "max_chars": {
                        "description": "Límite máximo de caracteres a extraer (por defecto 4000).",
                        "type": "integer"
                    },
                    "url": {
                        "description": "URL de la página web a leer.",
                        "type": "string"
                    }
                },
                "required": [
                    "url"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "MCP Client ÚNICAMENTE: Consulta herramientas externas en servidores MCP remotos. NUNCA uses esta herramienta para listar archivos, carpetas o código del proyecto local; para ver archivos del proyecto usa 'list_directory' o 'get_repo_map'.",
            "name": "list_mcp_tools",
            "parameters": {
                "properties": {},
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "MCP Client: Ejecuta una herramienta externa en un servidor MCP conectado vía JSON-RPC 2.0.",
            "name": "call_mcp_tool",
            "parameters": {
                "properties": {
                    "arguments": {
                        "description": "Diccionario de argumentos para la herramienta.",
                        "type": "object"
                    },
                    "server_name": {
                        "description": "Nombre del servidor MCP registrado.",
                        "type": "string"
                    },
                    "tool_name": {
                        "description": "Nombre de la herramienta en el servidor MCP.",
                        "type": "string"
                    }
                },
                "required": [
                    "server_name",
                    "tool_name"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "[NAVEGADOR CDP] Abre y navega a una URL en el navegador Chromium local (Chrome/Edge). Renderiza JavaScript dinámico. CERO Playwright.",
            "name": "browser_open",
            "parameters": {
                "properties": {
                    "url": {
                        "description": "URL completa a cargar (ej: 'https://docs.python.org' o 'http://localhost:8000').",
                        "type": "string"
                    }
                },
                "required": [
                    "url"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "[NAVEGADOR CDP] Extrae el texto legible de la página web activa o de un elemento CSS específico tras el renderizado de JavaScript.",
            "name": "browser_get_content",
            "parameters": {
                "properties": {
                    "max_chars": {
                        "description": "Máximo número de caracteres a extraer (por defecto 4000).",
                        "type": "integer"
                    },
                    "selector": {
                        "description": "Selector CSS opcional para limitar la extracción (ej: '#main', 'article', '.content').",
                        "type": "string"
                    }
                },
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "[NAVEGADOR CDP] Hace clic en un botón, enlace o elemento interactivo de la página por su selector CSS.",
            "name": "browser_click",
            "parameters": {
                "properties": {
                    "selector": {
                        "description": "Selector CSS del elemento a hacer clic (ej: 'button.submit', '#login-btn', 'a.nav-link').",
                        "type": "string"
                    }
                },
                "required": [
                    "selector"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "[NAVEGADOR CDP] Escribe texto en un campo de formulario, input o textarea identificado por su selector CSS.",
            "name": "browser_type",
            "parameters": {
                "properties": {
                    "selector": {
                        "description": "Selector CSS del campo de texto (ej: 'input[name=\"q\"]', '#username', 'textarea').",
                        "type": "string"
                    },
                    "text": {
                        "description": "Texto a escribir en el campo.",
                        "type": "string"
                    }
                },
                "required": [
                    "selector",
                    "text"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "[NAVEGADOR CDP] Captura una imagen de la pantalla actual (screenshot PNG) para inspección visual o pruebas de UI.",
            "name": "browser_screenshot",
            "parameters": {
                "properties": {
                    "output_path": {
                        "description": "Ruta de destino opcional para el archivo PNG (por defecto se guarda en .aether/screenshots/).",
                        "type": "string"
                    }
                },
                "type": "object"
            }
        },
        "type": "function"
    }
]
