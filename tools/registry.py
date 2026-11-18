"""
Registro central de herramientas para el LLM.
Define esquemas OpenAPI / JSON Schema compatibles con la API de Ollama y el despachador de ejecución.
"""

import json
from typing import Any, Callable, Dict, List

from tools.file_tools import delete_file, edit_file, move_file, read_file, write_file
from tools.git_tools import create_checkpoint, get_git_diff, get_git_status, undo_checkpoint
from tools.repomap import generate_repo_map
from tools.search_tools import list_directory, search_codebase, get_file_outline
from tools.shell_tools import run_command
from tools.subagent import delegate_task, delegate_research, delegate_test
from tools.web_tools import search_web, fetch_web_page
from tools.diagnostics import get_diagnostics
from tools.patch_engine import PatchEngine
from tools.process_manager import ProcessManager
from tools.agent_tools import (
    update_plan,
    get_plan,
    request_approval,
    get_project_instructions,
    remember_fact,
    search_memory,
    list_memories
)
from tools.code_intel import find_definition, find_references, get_dependencies
from tools.vram_monitor import get_hardware_vram_status
from tools.mcp_client import list_mcp_tools, call_mcp_tool_wrapper

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
            "description": "Busca ocurrencias de texto, símbolos o patrones en todos los archivos del proyecto (estilo ripgrep / grep).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Texto, símbolo o palabra clave a buscar (también acepta 'pattern')."
                    },
                    "path": {
                        "type": "string",
                        "description": "Directorio base de búsqueda (por defecto '.')."
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "Patrón de archivos a filtrar, ej: '*.py' o '*.ts'."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "grep_search",
            "description": "Búsqueda grep en el código base. Busca texto o patrones en archivos con filtrado por extensión.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Texto o patrón a buscar."
                    },
                    "path": {
                        "type": "string",
                        "description": "Ruta o directorio a buscar."
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "Filtro de archivos (ej: '*.py')."
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
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_research",
            "description": "[SUBAGENTE RESEARCHER ANTIGRAVITY] Delega una investigación o análisis de código a un subagente especializado en modo de SOLO LECTURA. No tiene permisos de escritura ni mutación en disco.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Pregunta técnica o aspecto del código a investigar."
                    },
                    "target_dir": {
                        "type": "string",
                        "description": "Directorio objetivo (por defecto '.')."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delegate_test",
            "description": "[SUBAGENTE TESTER] Delega la ejecución y diagnóstico de una suite de pruebas a un subagente especializado de auditoría.",
            "parameters": {
                "type": "object",
                "properties": {
                    "test_command": {
                        "type": "string",
                        "description": "Comando de testing (por defecto 'pytest')."
                    },
                    "target_file": {
                        "type": "string",
                        "description": "Archivo de prueba específico a auditar."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Elimina de forma segura un archivo existente en el disco.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Ruta del archivo a eliminar."
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "move_file",
            "description": "Mueve o renombra un archivo existente a una nueva ruta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Ruta del archivo original."
                    },
                    "destination": {
                        "type": "string",
                        "description": "Nueva ruta o nombre de destino."
                    }
                },
                "required": ["source", "destination"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_patch",
            "description": "Aplica una edición atómica y transaccional verificando SHA256 o similitud fuzzy, generando diff unificado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Ruta del archivo a modificar."
                    },
                    "target": {
                        "type": "string",
                        "description": "Texto exacto o bloque de código que se va a sustituir."
                    },
                    "replacement": {
                        "type": "string",
                        "description": "Nuevo texto o bloque de código que reemplazará al objetivo."
                    },
                    "expected_sha256": {
                        "type": "string",
                        "description": "Hash SHA-256 opcional para prevenir colisiones o ediciones concurrentes."
                    }
                },
                "required": ["path", "target", "replacement"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_diagnostics",
            "description": "Inspecciona el AST y la sintaxis de un archivo (Python, JSON) para detectar errores antes o después de editar.",
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
            "name": "run_tests",
            "description": "Ejecuta las pruebas unitarias del proyecto de forma automatizada (por defecto con pytest).",
            "parameters": {
                "type": "object",
                "properties": {
                    "test_target": {
                        "type": "string",
                        "description": "Ruta o archivo específico de tests a ejecutar (opcional)."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "start_background_process",
            "description": "Inicia un comando persistente en segundo plano (servidor de desarrollo, watcher, script largo) y retorna un process_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Comando a ejecutar en segundo plano."
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
            "name": "get_process_status",
            "description": "Consulta el estado, salida estándar y errores de un proceso en segundo plano por su process_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {
                        "type": "string",
                        "description": "ID del proceso retornado por start_background_process."
                    }
                },
                "required": ["process_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_process",
            "description": "Termina y cancela de forma forzosa un proceso en segundo plano y todo su árbol de procesos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_id": {
                        "type": "string",
                        "description": "ID del proceso a cancelar."
                    }
                },
                "required": ["process_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "safe_checkpoint",
            "description": "Guarda un punto de restauración seguro a nivel de archivo sin usar git reset --hard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Descripción del punto de restauración."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "safe_undo_checkpoint",
            "description": "Restaura quirúrgicamente los archivos modificados desde el último checkpoint seguro.",
            "parameters": {
                "type": "object",
                "properties": {
                    "snapshot_id": {
                        "type": "string",
                        "description": "ID opcional del checkpoint específico a restaurar."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_plan",
            "description": "Actualiza la lista de pasos, el paso actual en progreso y los criterios de aceptación para resolver la tarea.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plan_steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista secuencial de pasos a realizar."
                    },
                    "current_step": {
                        "type": "integer",
                        "description": "Índice (1-based) del paso actual en ejecución."
                    },
                    "acceptance_criteria": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Criterios observables que definirán que la tarea está completa."
                    },
                    "is_completed": {
                        "type": "boolean",
                        "description": "Indica si todos los pasos y criterios han sido completados y verificados con éxito."
                    }
                },
                "required": ["plan_steps"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_plan",
            "description": "[ARTEFACTO PLAN] Consulta y lee el plan de ejecución activo y los criterios de aceptación definidos para la tarea actual.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "remember_fact",
            "description": "[MEMORIA SEMÁNTICA PERSISTENTE] Almacena hechos arquitectónicos, decisiones clave o reglas del usuario en SQLite con embeddings vectoriales locales para recordarlos entre diferentes sesiones.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Identificador único o concepto clave (ej: 'auth_jwt_algorithm')."
                    },
                    "content": {
                        "type": "string",
                        "description": "Detalle técnico, decisión o regla a recordar."
                    },
                    "category": {
                        "type": "string",
                        "description": "Categoría conceptual (ej: 'project', 'architecture', 'user_preference')."
                    }
                },
                "required": ["key", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_memory",
            "description": "[BÚSQUEDA SEMÁNTICA VECTORIAL] Busca hechos, contexto histórico y decisiones arquitectónicas previas en milisegundos mediante similitud de embeddings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Pregunta o término conceptual a buscar en la memoria semántica."
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Número máximo de resultados a recuperar (por defecto 3)."
                    },
                    "category": {
                        "type": "string",
                        "description": "Filtrar por categoría opcional."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_memories",
            "description": "[LISTADO DE MEMORIA] Lista todas las directivas y hechos almacenados en la memoria semántica persistente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Filtrar por categoría opcional."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "request_approval",
            "description": "Solicita autorización explícita al desarrollador antes de realizar una acción de alto impacto o destructiva.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action_description": {
                        "type": "string",
                        "description": "Descripción clara de la acción que se desea ejecutar y por qué."
                    },
                    "risk_level": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Nivel de riesgo estimado."
                    }
                },
                "required": ["action_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_instructions",
            "description": "Carga las instrucciones, guías de estilo y convenciones del repositorio (AGENTS.md, AETHER.md, .aetherrules).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Ruta opcional del directorio raíz del proyecto (por defecto '.')."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_definition",
            "description": "Code Intelligence: Encuentra la definición de una función, método o clase en el código Python usando el AST.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Nombre de la función, clase o método a localizar."
                    },
                    "root_dir": {
                        "type": "string",
                        "description": "Directorio raíz donde buscar (por defecto '.')."
                    }
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "find_references",
            "description": "Code Intelligence: Encuentra todas las llamadas y usos de un símbolo en los archivos del proyecto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Nombre del símbolo a buscar."
                    },
                    "root_dir": {
                        "type": "string",
                        "description": "Directorio base de búsqueda (por defecto '.')."
                    }
                },
                "required": ["symbol"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_dependencies",
            "description": "Code Intelligence: Mapea los imports y el gráfico de dependencias locales y externas de un archivo.",
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
            "name": "get_hardware_vram_status",
            "description": "Hardware Monitor: Consulta el estado en tiempo real de la GPU (VRAM de 6 GB, modelos cargados en Ollama y CPU offloading).",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_skill",
            "description": "Skills Runtime: Ejecuta habilidades complejas automatizadas ('review' para auditoría de calidad, 'test_gen' para generar pruebas, 'dependencies' para acoplamiento).",
            "parameters": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "enum": ["review", "test_gen", "dependencies"],
                        "description": "Nombre de la habilidad a ejecutar."
                    },
                    "target": {
                        "type": "string",
                        "description": "Archivo o directorio objetivo."
                    }
                },
                "required": ["skill_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_mcp_tools",
            "description": "MCP Client: Descubre y lista todas las herramientas disponibles exportadas por servidores MCP configurados.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "call_mcp_tool",
            "description": "MCP Client: Ejecuta una herramienta externa en un servidor MCP conectado vía JSON-RPC 2.0.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server_name": {
                        "type": "string",
                        "description": "Nombre del servidor MCP registrado."
                    },
                    "tool_name": {
                        "type": "string",
                        "description": "Nombre de la herramienta en el servidor MCP."
                    },
                    "arguments": {
                        "type": "object",
                        "description": "Diccionario de argumentos para la herramienta."
                    }
                },
                "required": ["server_name", "tool_name"]
            }
        }
    }
]

# Funciones puente para herramientas extendidas
def apply_patch_tool(path: str, target: str, replacement: str, expected_sha256: str = None) -> str:
    res = PatchEngine.apply_single_patch(path, target, replacement, expected_sha256)
    if res.success:
        diff_str = res.diff if res.diff else "(sin cambios textuales en diff)"
        return f"✅ Parche transaccional aplicado con éxito en '{res.filepath.name}'.\nSHA256: {res.old_sha256[:8]} -> {res.new_sha256[:8]}\n\nDiff unificado:\n{diff_str}"
    return f"❌ Fallo al aplicar parche en '{path}': {res.error}"


def run_tests_tool(test_target: str = None) -> str:
    import time
    from pathlib import Path
    target = test_target.strip() if test_target else ""
    if not target:
        recent_root_tests = [
            p for p in Path.cwd().glob("test_*.py")
            if (time.time() - p.stat().st_mtime) < 3600
        ]
        if recent_root_tests:
            recent_root_tests.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            target = " ".join(p.name for p in recent_root_tests)
        else:
            root_tests = list(Path.cwd().glob("test_*.py"))
            if root_tests:
                root_tests.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                target = root_tests[0].name
            else:
                target = "."
    cmd = f"pytest -v -o testpaths=. {target}"
    return run_command(cmd)


def conclude_turn_tool(message: str = "Tarea concluida", **kwargs) -> str:
    return f"🏁 Turno concluido: {message}"


def start_background_process_tool(command: str, cwd: str = None) -> str:
    pm = ProcessManager()
    pid_id = pm.start_process(command, cwd)
    return f"🚀 Proceso iniciado en segundo plano con ID '{pid_id}'. Consulta su estado con get_process_status('{pid_id}')."


def get_process_status_tool(process_id: str) -> str:
    pm = ProcessManager()
    status = pm.get_status(process_id)
    if not status.get("success"):
        return f"❌ Error: {status.get('error')}"
    state = "🟢 EN EJECUCIÓN" if status["is_running"] else f"⚪ FINALIZADO (Código {status['exit_code']})"
    output = f"Estado de {status['process_id']} ({state}) [PID: {status['pid']}]:\n"
    if status.get("stdout"):
        output += f"--- STDOUT ---\n{status['stdout']}\n"
    if status.get("stderr"):
        output += f"--- STDERR ---\n{status['stderr']}\n"
    return output.strip()


def cancel_process_tool(process_id: str) -> str:
    pm = ProcessManager()
    res = pm.cancel_process(process_id)
    if res.get("success"):
        return f"🛑 {res.get('message')}"
    return f"❌ Error: {res.get('error')}"


def safe_checkpoint_tool(message: str = "Punto de control automático") -> str:
    from agent.checkpoints import SafeCheckpointManager
    mgr = SafeCheckpointManager()
    snap_id = mgr.create_checkpoint(message)
    return f"✅ Checkpoint seguro creado: '{snap_id}' ({message})."


def safe_undo_checkpoint_tool(snapshot_id: str = None) -> str:
    from agent.checkpoints import SafeCheckpointManager
    mgr = SafeCheckpointManager()
    if not snapshot_id:
        checkpoints = mgr.list_checkpoints()
        if not checkpoints:
            return "❌ No existen checkpoints seguros registrados para restaurar."
        snapshot_id = checkpoints[0]["snapshot_id"]
    success, msg = mgr.restore_checkpoint(snapshot_id)
    if success:
        return f"✅ {msg}"
    return f"❌ Fallo al restaurar checkpoint: {msg}"


def execute_skill_tool(skill_name: str, target: str = None) -> str:
    from agent.skills import execute_skill
    return execute_skill(skill_name, target)


# Mapa de ejecutores en Python
TOOL_HANDLERS: Dict[str, Callable[..., Any]] = {
    "read_file": read_file,
    "cat": read_file,
    "view_file": read_file,
    "edit_file": edit_file,
    "write_file": write_file,
    "create_file": write_file,
    "new_file": write_file,
    "save_file": write_file,
    "delete_file": delete_file,
    "move_file": move_file,
    "run_command": run_command,
    "exec": run_command,
    "execute_command": run_command,
    "bash": run_command,
    "sh": run_command,
    "terminal": run_command,
    "search_codebase": search_codebase,
    "grep_search": search_codebase,
    "grep": search_codebase,
    "list_directory": list_directory,
    "get_file_outline": get_file_outline,
    "get_repo_map": generate_repo_map,
    "delegate_task": delegate_task,
    "delegate_research": delegate_research,
    "delegate_test": delegate_test,
    "search_web": search_web,
    "fetch_web_page": fetch_web_page,
    "create_checkpoint": create_checkpoint,
    "undo_checkpoint": undo_checkpoint,
    "get_git_diff": get_git_diff,
    "get_git_status": get_git_status,
    "apply_patch": apply_patch_tool,
    "get_diagnostics": get_diagnostics,
    "run_tests": run_tests_tool,
    "pytest": run_tests_tool,
    "test": run_tests_tool,
    "test_runner": run_tests_tool,
    "conclude_turn": conclude_turn_tool,
    "finish_turn": conclude_turn_tool,
    "complete_task": conclude_turn_tool,
    "finish": conclude_turn_tool,
    "done": conclude_turn_tool,
    "start_background_process": start_background_process_tool,
    "get_process_status": get_process_status_tool,
    "cancel_process": cancel_process_tool,
    "safe_checkpoint": safe_checkpoint_tool,
    "safe_undo_checkpoint": safe_undo_checkpoint_tool,
    "update_plan": update_plan,
    "get_plan": get_plan,
    "remember_fact": remember_fact,
    "search_memory": search_memory,
    "list_memories": list_memories,
    "request_approval": request_approval,
    "get_project_instructions": get_project_instructions,
    "find_definition": find_definition,
    "find_references": find_references,
    "get_dependencies": get_dependencies,
    "get_hardware_vram_status": get_hardware_vram_status,
    "execute_skill": execute_skill_tool,
    "list_mcp_tools": list_mcp_tools,
    "call_mcp_tool": call_mcp_tool_wrapper,
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

    # Normalización de alias comunes de parámetros enviados por LLMs locales
    if "path" not in arguments:
        for p_alias in ["file_path", "filepath", "filename", "file"]:
            if p_alias in arguments:
                arguments["path"] = arguments.pop(p_alias)
                break

    if "content" not in arguments:
        for c_alias in ["text", "code", "body"]:
            if c_alias in arguments and name in ["write_file", "create_file", "new_file", "save_file"]:
                arguments["content"] = arguments.pop(c_alias)
                break

    if "command" not in arguments:
        for cmd_alias in ["cmd", "script", "instruction"]:
            if cmd_alias in arguments and name in ["run_command", "exec", "execute_command", "bash", "sh", "terminal"]:
                arguments["command"] = arguments.pop(cmd_alias)
                break

    if "test_target" not in arguments:
        for t_alias in ["target", "path", "file"]:
            if t_alias in arguments and name in ["run_tests", "pytest", "test", "test_runner"]:
                arguments["test_target"] = arguments.pop(t_alias)
                break

    try:
        result = handler(**arguments)
        return str(result)
    except TypeError as te:
        return f"Error en los parámetros de la herramienta '{name}': {str(te)}"
    except Exception as e:
        return f"Error durante la ejecución de la herramienta '{name}': {str(e)}"


def execute_tools_parallel(calls: List[tuple], max_workers: int = 4) -> List[str]:
    """
    Ejecuta un lote de herramientas pasivas concurrentemente usando un ThreadPoolExecutor.
    Inspirado en la ejecución concurrente de Antigravity para reducir la latencia de lectura multi-archivo.
    """
    from concurrent.futures import ThreadPoolExecutor
    if not calls:
        return []
    if len(calls) == 1:
        name, args = calls[0]
        return [execute_tool(name, args)]

    results: List[Any] = [None] * len(calls)
    with ThreadPoolExecutor(max_workers=min(max_workers, len(calls))) as executor:
        futures = {
            executor.submit(execute_tool, name, args): idx
            for idx, (name, args) in enumerate(calls)
        }
        for f in futures:
            idx = futures[f]
            results[idx] = f.result()
    return [str(r) for r in results]

