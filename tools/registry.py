"""
Registro central de herramientas para el LLM.
Define esquemas OpenAPI / JSON Schema compatibles con la API de Ollama y el despachador de ejecución.
"""

import json
from typing import Any, Callable, Dict, List

from tools.file_tools import edit_file, read_file, write_file
from tools.git_tools import create_checkpoint, get_git_diff, get_git_status, undo_checkpoint
from tools.repomap import generate_repo_map
from tools.search_tools import list_directory, search_codebase, get_file_outline
from tools.shell_tools import run_command
from tools.subagent import delegate_task
from tools.web_tools import search_web, fetch_web_page

# Esquemas de herramientas compatibles con Ollama / OpenAI
TOOLS_SCHEMA: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lee un rango de líneas de un archivo de código con números de línea para no desbordar el contexto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Ruta relativa o absoluta del archivo a leer."
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "Línea inicial a leer (por defecto 1)."
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Línea final a leer (por defecto 200)."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Reemplaza exactamente una sección de texto existente (target) por nuevo código (replacement). Requiere indentación exacta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Ruta del archivo a editar."
                    },
                    "target": {
                        "type": "string",
                        "description": "Texto exacto que se desea reemplazar, incluyendo espacios y sangrías."
                    },
                    "replacement": {
                        "type": "string",
                        "description": "Nuevo texto que sustituirá a 'target'."
                    }
                },
                "required": ["path", "target", "replacement"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Crea un archivo nuevo o reemplaza por completo el contenido de uno existente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Ruta del archivo a crear o sobrescribir."
                    },
                    "content": {
                        "type": "string",
                        "description": "Contenido completo del archivo."
                    }
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Ejecuta un comando en la consola (PowerShell en Windows) para correr tests, instalar dependencias o compilar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Comando a ejecutar en la terminal (ej. 'pytest', 'npm test')."
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Directorio de trabajo opcional."
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_codebase",
            "description": "Busca ocurrencias de texto o símbolos en todos los archivos del proyecto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Texto o palabra clave a buscar."
                    },
                    "path": {
                        "type": "string",
                        "description": "Directorio base de búsqueda (por defecto '.')."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "Muestra el árbol de carpetas y archivos del proyecto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directorio a explorar (por defecto '.')."
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Profundidad máxima de recursión (por defecto 2)."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_checkpoint",
            "description": "Guarda un punto de restauración con Git antes de realizar modificaciones profundas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Descripción del checkpoint."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "undo_checkpoint",
            "description": "Revierte las modificaciones realizadas volviendo al último checkpoint seguro.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_git_diff",
            "description": "Obtiene la lista de cambios y diferencias de código realizadas respecto al último commit.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_file_outline",
            "description": "Superpoder: Extrae el esquema sintáctico (AST) de clases, métodos y funciones de un archivo para entender su estructura sin consumir tokens leyendo todo el código.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Ruta del archivo a inspeccionar."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Superpoder: Realiza una búsqueda web en tiempo real para encontrar documentación técnica de librerías, foros o ejemplos de código.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Término o pregunta técnica a buscar."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Cantidad de resultados a retornar (por defecto 5)."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_web_page",
            "description": "Superpoder: Descarga y extrae el texto limpio y legible de una URL o documentación técnica en la web.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL de la página web a leer."
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Límite máximo de caracteres a extraer (por defecto 4000)."
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_repo_map",
            "description": "[SUPERPODER REPO-MAP] Retorna el mapa arquitectónico completo del repositorio con archivos, clases, métodos y firmas en solo ~300 tokens. Úsalo como primer paso para entender cualquier proyecto desconocido.",
            "parameters": {
                "type": "object",
                "properties": {
                    "root_dir": {
                        "type": "string",
                        "description": "Directorio raíz a mapear (por defecto '.')."
                    },
                    "max_files": {
                        "type": "integer",
                        "description": "Número máximo de archivos a listar (por defecto 40)."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_task",
            "description": "[SUBAGENTE CLAUDE-CODE] Delega una subtarea de investigación, análisis o verificación a un subagente auxiliar con contexto de memoria limpio. No satura la memoria del agente principal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Instrucción clara y específica para el subagente (ej: 'Revisa qué funciones exporta core/stt.py')."
                    }
                },
                "required": ["task_description"]
            }
        }
    }
]

# Mapa de ejecutores en Python
TOOL_HANDLERS: Dict[str, Callable[..., Any]] = {
    "read_file": read_file,
    "edit_file": edit_file,
    "write_file": write_file,
    "run_command": run_command,
    "search_codebase": search_codebase,
    "list_directory": list_directory,
    "get_file_outline": get_file_outline,
    "get_repo_map": generate_repo_map,
    "delegate_task": delegate_task,
    "search_web": search_web,
    "fetch_web_page": fetch_web_page,
    "create_checkpoint": create_checkpoint,
    "undo_checkpoint": undo_checkpoint,
    "get_git_diff": get_git_diff,
    "get_git_status": get_git_status,
}


def execute_tool(name: str, arguments: Any) -> str:
    """
    Ejecuta una herramienta por nombre validando y normalizando sus argumentos.
    """
    if name not in TOOL_HANDLERS:
        return f"Error: La herramienta '{name}' no existe en el catálogo registrado."

    handler = TOOL_HANDLERS[name]

    # Asegurar que arguments sea un diccionario
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except Exception:
            return f"Error: No se pudo decodificar el JSON de argumentos para '{name}': {arguments}"

    if not isinstance(arguments, dict):
        arguments = {}

    try:
        result = handler(**arguments)
        return str(result)
    except TypeError as te:
        return f"Error en los parámetros de la herramienta '{name}': {str(te)}"
    except Exception as e:
        return f"Error durante la ejecución de la herramienta '{name}': {str(e)}"

