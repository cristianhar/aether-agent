"""
Esquemas de herramientas para el dominio: Agentic.
"""

from typing import Any, Dict, List

AGENTIC_TOOLS: List[Dict[str, Any]] = [
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
            "description": "[MEMORIA SEMÁNTICA PERSISTENTE] Almacena hechos arquitectónicos, decisiones clave o reglas del usuario en SQLite con embeddings vectoriales locales para recordarlos entre diferentes sesiones.",
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
            "description": "[BÚSQUEDA SEMÁNTICA VECTORIAL] Busca hechos, contexto histórico y decisiones arquitectónicas previas en milisegundos mediante similitud de embeddings.",
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
