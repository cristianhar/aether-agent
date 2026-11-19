"""
Esquemas de herramientas para el dominio: Intelligence.
"""

from typing import Any, Dict, List

INTELLIGENCE_TOOLS: List[Dict[str, Any]] = [
    {
        "function": {
            "description": "[SUPERPODER REPO-MAP] Retorna el mapa arquitectónico completo del repositorio con archivos, clases, métodos y firmas en solo ~300 tokens. Úsalo como primer paso para entender cualquier proyecto desconocido.",
            "name": "get_repo_map",
            "parameters": {
                "properties": {
                    "max_files": {
                        "description": "Número máximo de archivos a listar (por defecto 40).",
                        "type": "integer"
                    },
                    "root_dir": {
                        "description": "Directorio raíz a mapear (por defecto '.').",
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
            "description": "Superpoder: Extrae el esquema sintáctico (AST) de clases, métodos y funciones de un archivo para entender su estructura sin consumir tokens leyendo todo el código.",
            "name": "get_file_outline",
            "parameters": {
                "properties": {
                    "path": {
                        "description": "Ruta del archivo a inspeccionar.",
                        "type": "string"
                    }
                },
                "required": [
                    "path"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "Busca ocurrencias de texto, símbolos o patrones en todos los archivos del proyecto (estilo ripgrep / grep).",
            "name": "search_codebase",
            "parameters": {
                "properties": {
                    "file_pattern": {
                        "description": "Patrón de archivos a filtrar, ej: '*.py' o '*.ts'.",
                        "type": "string"
                    },
                    "path": {
                        "description": "Directorio base de búsqueda (por defecto '.').",
                        "type": "string"
                    },
                    "query": {
                        "description": "Texto, símbolo o palabra clave a buscar (también acepta 'pattern').",
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
            "description": "Búsqueda grep en el código base. Busca texto o patrones en archivos con filtrado por extensión.",
            "name": "grep_search",
            "parameters": {
                "properties": {
                    "file_pattern": {
                        "description": "Filtro de archivos (ej: '*.py').",
                        "type": "string"
                    },
                    "path": {
                        "description": "Ruta o directorio a buscar.",
                        "type": "string"
                    },
                    "query": {
                        "description": "Texto o patrón a buscar.",
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
            "description": "Inspecciona el AST y la sintaxis de un archivo (Python, JSON) para detectar errores antes o después de editar.",
            "name": "get_diagnostics",
            "parameters": {
                "properties": {
                    "path": {
                        "description": "Ruta del archivo a inspeccionar.",
                        "type": "string"
                    }
                },
                "required": [
                    "path"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "Code Intelligence: Encuentra la definición de una función, método o clase en el código Python usando el AST.",
            "name": "find_definition",
            "parameters": {
                "properties": {
                    "root_dir": {
                        "description": "Directorio raíz donde buscar (por defecto '.').",
                        "type": "string"
                    },
                    "symbol": {
                        "description": "Nombre de la función, clase o método a localizar.",
                        "type": "string"
                    }
                },
                "required": [
                    "symbol"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "Code Intelligence: Encuentra todas las llamadas y usos de un símbolo en los archivos del proyecto.",
            "name": "find_references",
            "parameters": {
                "properties": {
                    "root_dir": {
                        "description": "Directorio base de búsqueda (por defecto '.').",
                        "type": "string"
                    },
                    "symbol": {
                        "description": "Nombre del símbolo a buscar.",
                        "type": "string"
                    }
                },
                "required": [
                    "symbol"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "Code Intelligence: Mapea los imports y el gráfico de dependencias locales y externas de un archivo.",
            "name": "get_dependencies",
            "parameters": {
                "properties": {
                    "path": {
                        "description": "Ruta del archivo a inspeccionar.",
                        "type": "string"
                    }
                },
                "required": [
                    "path"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "Carga las instrucciones, guías de estilo y convenciones del repositorio (AGENTS.md, AETHER.md, .aetherrules).",
            "name": "get_project_instructions",
            "parameters": {
                "properties": {
                    "path": {
                        "description": "Ruta opcional del directorio raíz del proyecto (por defecto '.').",
                        "type": "string"
                    }
                },
                "type": "object"
            }
        },
        "type": "function"
    }
]
