"""
Esquemas de herramientas para el dominio: Agentic.
"""

from typing import Any, Dict, List

AGENTIC_TOOLS: List[Dict[str, Any]] = [
    {
        "function": {
            "description": "Formula una o más preguntas interactivas de opción múltiple al usuario para aclarar requisitos técnicos o decisiones clave de diseño y espera su selección.",
            "name": "ask_question",
            "parameters": {
                "properties": {
                    "questions": {
                        "description": "Lista de preguntas estructuradas con sus opciones.",
                        "items": {
                            "properties": {
                                "is_multi_select": {
                                    "description": "Indica si el usuario puede seleccionar múltiples opciones (True) o solo una (False).",
                                    "type": "boolean"
                                },
                                "options": {
                                    "description": "Lista de opciones disponibles. La primera opción debe ser la recomendada con el prefijo '(Recommended)'.",
                                    "items": {
                                        "type": "string"
                                    },
                                    "type": "array"
                                },
                                "question": {
                                    "description": "La pregunta clara y directa que se presentará al usuario.",
                                    "type": "string"
                                }
                            },
                            "required": [
                                "question",
                                "options"
                            ],
                            "type": "object"
                        },
                        "type": "array"
                    }
                },
                "required": [
                    "questions"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "Actualiza la lista de pasos, el paso actual en progreso y los criterios de aceptación para resolver la tarea.",
            "name": "update_plan",
            "parameters": {
                "properties": {
                    "acceptance_criteria": {
                        "description": "Criterios observables que definirán que la tarea está completa.",
                        "items": {
                            "type": "string"
                        },
                        "type": "array"
                    },
                    "current_step": {
                        "description": "Índice (1-based) del paso actual en ejecución.",
                        "type": "integer"
                    },
                    "is_completed": {
                        "description": "Indica si todos los pasos y criterios han sido completados y verificados con éxito.",
                        "type": "boolean"
                    },
                    "plan_steps": {
                        "description": "Lista secuencial de pasos a realizar.",
                        "items": {
                            "type": "string"
                        },
                        "type": "array"
                    }
                },
                "required": [],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "[ARTEFACTO PLAN] Consulta y lee el plan de ejecución activo y los criterios de aceptación definidos para la tarea actual.",
            "name": "get_plan",
            "parameters": {
                "properties": {},
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "Crea un artefacto o documento estructurado persistente en .aether/artifacts/ (planes de arquitectura, especificaciones, diagramas Mermaid) con metadatos JSON.",
            "name": "create_artifact",
            "parameters": {
                "properties": {
                    "content": {
                        "description": "Contenido completo del artefacto en formato Markdown.",
                        "type": "string"
                    },
                    "request_feedback": {
                        "description": "True si el artefacto requiere revisión y autorización explícita del usuario.",
                        "type": "boolean"
                    },
                    "summary": {
                        "description": "Resumen conciso del contenido y propósito del artefacto.",
                        "type": "string"
                    },
                    "tags": {
                        "description": "Etiquetas temáticas opcionales (ej: ['architecture', 'backend']).",
                        "items": {
                            "type": "string"
                        },
                        "type": "array"
                    },
                    "title": {
                        "description": "Título descriptivo del artefacto.",
                        "type": "string"
                    },
                    "user_facing": {
                        "description": "True si el documento debe presentarse y ser visible para el usuario en la UI.",
                        "type": "boolean"
                    }
                },
                "required": [
                    "title",
                    "content",
                    "summary"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "Actualiza el contenido o metadatos de un artefacto existente incrementando su versión.",
            "name": "update_artifact",
            "parameters": {
                "properties": {
                    "artifact_id": {
                        "description": "Identificador único del artefacto a actualizar.",
                        "type": "string"
                    },
                    "content": {
                        "description": "Nuevo contenido Markdown del artefacto.",
                        "type": "string"
                    },
                    "request_feedback": {
                        "description": "Actualiza el flag de solicitud de feedback del usuario.",
                        "type": "boolean"
                    },
                    "summary": {
                        "description": "Nuevo resumen descriptivo del cambio o propósito.",
                        "type": "string"
                    }
                },
                "required": [
                    "artifact_id",
                    "content"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "Lee el contenido Markdown y los metadatos de un artefacto persistente.",
            "name": "read_artifact",
            "parameters": {
                "properties": {
                    "artifact_id": {
                        "description": "Identificador único del artefacto a consultar.",
                        "type": "string"
                    }
                },
                "required": [
                    "artifact_id"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "Lista todos los artefactos persistentes registrados en el proyecto con sus metadatos.",
            "name": "list_artifacts",
            "parameters": {
                "properties": {},
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "[GUARDAR EN MEMORIA] Almacena hechos arquitectónicos, decisiones clave o configuraciones en SQLite. NUNCA uses esta herramienta para responder preguntas ni consultar datos existentes; para consultar la memoria usa 'search_memory'.",
            "name": "remember_fact",
            "parameters": {
                "properties": {
                    "category": {
                        "description": "Categoría conceptual (ej: 'project', 'architecture', 'user_preference').",
                        "type": "string"
                    },
                    "content": {
                        "description": "Detalle técnico, decisión o regla a recordar.",
                        "type": "string"
                    },
                    "key": {
                        "description": "Identificador único o concepto clave (ej: 'auth_jwt_algorithm').",
                        "type": "string"
                    }
                },
                "required": [
                    "key",
                    "content"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "[CONSULTAR MEMORIA DEL PROYECTO] Consulta y busca hechos, decisiones o configuraciones previamente guardadas en la memoria semántica cuando el usuario pregunte por ellas.",
            "name": "search_memory",
            "parameters": {
                "properties": {
                    "category": {
                        "description": "Filtrar por categoría opcional.",
                        "type": "string"
                    },
                    "query": {
                        "description": "Pregunta o término conceptual a buscar en la memoria semántica.",
                        "type": "string"
                    },
                    "top_k": {
                        "description": "Número máximo de resultados a recuperar (por defecto 3).",
                        "type": "integer"
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
            "description": "[LISTADO DE MEMORIA] Lista todas las directivas y hechos almacenados en la memoria semántica persistente.",
            "name": "list_memories",
            "parameters": {
                "properties": {
                    "category": {
                        "description": "Filtrar por categoría opcional.",
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
            "description": "Guarda un punto de restauración con Git antes de realizar modificaciones profundas.",
            "name": "create_checkpoint",
            "parameters": {
                "properties": {
                    "message": {
                        "description": "Descripción del checkpoint.",
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
            "description": "Revierte las modificaciones realizadas volviendo al último checkpoint seguro.",
            "name": "undo_checkpoint",
            "parameters": {
                "properties": {},
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "Guarda un punto de restauración seguro a nivel de archivo sin usar git reset --hard.",
            "name": "safe_checkpoint",
            "parameters": {
                "properties": {
                    "message": {
                        "description": "Descripción del punto de restauración.",
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
            "description": "Restaura quirúrgicamente los archivos modificados desde el último checkpoint seguro.",
            "name": "safe_undo_checkpoint",
            "parameters": {
                "properties": {
                    "snapshot_id": {
                        "description": "ID opcional del checkpoint específico a restaurar.",
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
            "description": "Obtiene la lista de cambios y diferencias de código realizadas respecto al último commit.",
            "name": "get_git_diff",
            "parameters": {
                "properties": {},
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "Solicita autorización explícita al desarrollador antes de realizar una acción de alto impacto o destructiva.",
            "name": "request_approval",
            "parameters": {
                "properties": {
                    "action_description": {
                        "description": "Descripción clara de la acción que se desea ejecutar y por qué.",
                        "type": "string"
                    },
                    "risk_level": {
                        "description": "Nivel de riesgo estimado.",
                        "enum": [
                            "low",
                            "medium",
                            "high",
                            "critical"
                        ],
                        "type": "string"
                    }
                },
                "required": [
                    "action_description"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "[SUBAGENTE CLAUDE-CODE] Delega una subtarea de investigación, análisis o verificación a un subagente auxiliar con contexto de memoria limpio. No satura la memoria del agente principal.",
            "name": "delegate_task",
            "parameters": {
                "properties": {
                    "task_description": {
                        "description": "Instrucción clara y específica para el subagente (ej: 'Revisa qué funciones exporta core/stt.py').",
                        "type": "string"
                    }
                },
                "required": [
                    "task_description"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "[SUBAGENTE RESEARCHER ANTIGRAVITY] Delega una investigación o análisis de código a un subagente especializado en modo de SOLO LECTURA. No tiene permisos de escritura ni mutación en disco.",
            "name": "delegate_research",
            "parameters": {
                "properties": {
                    "query": {
                        "description": "Pregunta técnica o aspecto del código a investigar.",
                        "type": "string"
                    },
                    "target_dir": {
                        "description": "Directorio objetivo (por defecto '.').",
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
            "description": "[SUBAGENTE TESTER] Delega la ejecución y diagnóstico de una suite de pruebas a un subagente especializado de auditoría.",
            "name": "delegate_test",
            "parameters": {
                "properties": {
                    "target_file": {
                        "description": "Archivo de prueba específico a auditar.",
                        "type": "string"
                    },
                    "test_command": {
                        "description": "Comando de testing (por defecto 'pytest').",
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
            "description": "Skills Runtime: Ejecuta habilidades complejas automatizadas ('review' para auditoría de calidad, 'test_gen' para generar pruebas, 'dependencies' para acoplamiento).",
            "name": "execute_skill",
            "parameters": {
                "properties": {
                    "skill_name": {
                        "description": "Nombre de la habilidad a ejecutar.",
                        "enum": [
                            "review",
                            "test_gen",
                            "dependencies"
                        ],
                        "type": "string"
                    },
                    "target": {
                        "description": "Archivo o directorio objetivo.",
                        "type": "string"
                    }
                },
                "required": [
                    "skill_name"
                ],
                "type": "object"
            }
        },
        "type": "function"
    },
    {
        "function": {
            "description": "Hardware Monitor: Consulta el estado en tiempo real de la GPU (VRAM de 6 GB, modelos cargados en Ollama y CPU offloading).",
            "name": "get_hardware_vram_status",
            "parameters": {
                "properties": {},
                "type": "object"
            }
        },
        "type": "function"
    }
]
