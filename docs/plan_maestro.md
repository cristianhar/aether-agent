# ⚡ Plan Maestro de Arquitectura y Runtime Hardening: AETHER IDE

> **Guía Técnica de Implementación para el Agente Programador Autónomo Local (100% Offline).**  
> Inspirado en las arquitecturas públicas de **Claude Code**, **Cursor**, **Aider** y **Antigravity**.  
> Optimizado para **NVIDIA GeForce RTX 4060 Laptop (6 GB VRAM)**, 16 GB RAM y Windows 11 / PowerShell.

---

## 1. Visión y Objetivos de Producción

Transformar AETHER de un prototipo CLI con tool calling básico en un **sistema de programación autónomo, modular, extensible, seguro y recuperable**.

El agente opera en un bucle cerrado:
$$\text{Understand} \longrightarrow \text{Plan} \longrightarrow \text{Act} \longrightarrow \text{Observe} \longrightarrow \text{Verify}$$

Capaz de:
- Descubrir y mapear repositorios completos en ~300 tokens mediante AST.
- Aplicar parches atómicos y transaccionales sin riesgo de corrupción de archivos ni pérdida de trabajo del desarrollador.
- Ejecutar y monitorear pruebas y procesos prolongados en segundo plano con cancelación forzosa de procesos hijos en Windows.
- Gestionar memoria y presupuesto de contexto para evitar descarga de VRAM a RAM del sistema.
- Persistir sesiones y telemetría de rendimiento en SQLite.

---

## 2. Matriz de Evaluación del Repositorio (Repository Audit Matrix)

| Componente | Estado Actual | Capacidades Implementadas / Pendientes | Prioridad | Archivos Afectados |
| :--- | :---: | :--- | :---: | :--- |
| **Tool Registry Dinámico** | **IMPLEMENTED** | Esquemas OpenAPI / Pydantic, tipado estricto, 28 herramientas registradas, manejo de excepciones uniforme y tipado de resultados. | **P0** | `tools/registry.py`, `tools/base.py` |
| **Session Manager** | **IMPLEMENTED** | Base de datos SQLite (`.aether/sessions.db`), persistencia de mensajes, auditoría de herramientas, estados, reanudación con `/resume <id>`. | **P0** | `agent/session.py` |
| **Cancellation Manager** | **IMPLEMENTED** | `CancellationToken` thread-safe, interrupción limpia de generación Ollama, cancelación de procesos en background con `taskkill`. | **P0** | `agent/state.py`, `tools/process_manager.py` |
| **Permission Engine** | **IMPLEMENTED** | Jaula de límites de workspace (path jail), evaluación por categorías de riesgo, patrones destructivos y callback de aprobación interactiva. | **P0** | `agent/permissions.py` |
| **Patch Engine Transaccional** | **IMPLEMENTED** | Edición atómica (`.tmp` + `os.replace`), pre-condición SHA-256, tolerancia fuzzy, preservación CRLF/LF y rollback multi-archivo. | **P0** | `tools/patch_engine.py` |
| **Context Budget Manager** | **IMPLEMENTED** | Ventanas dinámicas (4K / 8K), compactación de turnos antiguos, truncamiento seguro de outputs extensos y perfiles de VRAM. | **P0** | `agent/memory.py`, `agent/orchestrator.py` |
| **Safe Checkpoint Manager** | **IMPLEMENTED** | Snapshots de pre-imagen en `.aether/checkpoints/<id>/manifest.json`, restauración quirúrgica sin `git reset --hard`. | **P0** | `agent/checkpoints.py` |
| **Structured Tool Results** | **IMPLEMENTED** | Clase `ToolResult` (éxito, salida, error, código de salida, metadatos, formateo para LLM). | **P0** | `tools/base.py` |
| **Project Instructions** | **IMPLEMENTED** | Ingestión de `AGENTS.md`, `AETHER.md`, `.aetherrules`, tratados como contexto no privilegiado frente al sistema. | **P1** | `tools/agent_tools.py` |
| **Hooks y Modos** | **IMPLEMENTED** | Pre/Post tool use hooks, modos operativos (`agent`, `ask`, `plan`), inyección de contexto de auto-sanación ante tracebacks. | **P1** | `agent/hooks.py` |
| **Observability & Tracing** | **IMPLEMENTED** | Telemetría estructurada JSON Lines (`.aether/telemetry.jsonl`), latencias por herramienta y resumen de turnos (`/telemetry`). | **P1** | `agent/telemetry.py` |
| **Subagentes y MCP** | **IMPLEMENTED** | Delegación de tareas a subagentes auxiliares con memoria limpia (`tools/subagent.py`) sin saturar contexto principal. | **P2** | `tools/subagent.py` |

---

## 3. Corrección de los 4 Errores Críticos de Arquitectura

### Error 1: Peligro de `git reset --hard HEAD~1`
- **Problema:** Destruye cambios no commiteados del usuario, elimina archivos sin seguimiento (*untracked*) y asume erróneamente que el último commit siempre pertenece a AETHER.
- **Solución implementada (`SafeCheckpointManager`):**
  - Crea un snapshot en `.aether/checkpoints/<snapshot_id>/` guardando copias físicas previas de los archivos afectados junto con un `manifest.json`.
  - La reversión restaura exclusivamente los archivos tocados por el agente, detecta si el usuario hizo modificaciones externas posteriores y borra únicamente los archivos basura creados por el agente, sin alterar el historial global de Git.

### Error 2: Insuficiencia de Listas Negras de Comandos
- **Problema:** Bloquear palabras como `rm -rf` o `format` es trivial de eludir mediante PowerShell (`Remove-Item -Recurse -Force`), scripts Python o ejecutables.
- **Solución implementada (`PermissionEngine`):**
  - **Aislamiento por Jaula de Workspace (Path Jail):** Toda operación de escritura (`WORKSPACE_WRITE`) debe resolver dentro del directorio de trabajo o en directorios autorizados explícitamente (`Path.resolve().relative_to()`).
  - **Categorización por Riesgo:** `READ_ONLY`, `WORKSPACE_WRITE`, `COMMAND_EXECUTE`, `ADMIN_DESTRUCTIVE`.
  - **Autorización Interactiva:** Acciones destructivas requieren aprobación explícita mediante callback al usuario antes de tocar el sistema operativo.

### Error 3: Presupuesto de VRAM para RTX 4060 Laptop (6 GB VRAM)
- **Problema:** Ejecutar `qwen2.5-coder:7b` con ventanas de contexto no controladas (16K+) desborda la VRAM de 6 GB, provocando offloading de capas a la memoria RAM del sistema con caídas de velocidad de 10x.
- **Solución implementada:**
  - Presupuesto base configurado en `num_ctx = 8192` para el modelo de 7B cuantizado (`q4_K_M`), ocupando ~4.5 GB de VRAM y dejando 1.5 GB libres para Windows DWM y buffers de pantalla.
  - Soporte de perfil ligero con `qwen2.5-coder:3b` y `num_ctx = 4096` para proyectos ultrarrápidos o multitarea intensiva.
  - Algoritmo de compactación de memoria (`compact_memory`) que resume turnos antiguos y trunca salidas de herramientas superiores a 600 caracteres.

### Error 4: Concurrencia y Ediciones Corruptas
- **Problema:** Si el usuario edita un archivo mientras el agente trabaja, las modificaciones se sobreescriben silenciosamente o se producen ediciones parciales/truncadas.
- **Solución implementada (`PatchEngine`):**
  - Verificación de pre-condición mediante hash SHA-256 del contenido previo. Si difiere, rechaza la operación informando del conflicto.
  - Reemplazo atómico con archivo temporal en el mismo sistema de archivos (`.tmp` + `os.replace` con `os.fsync`).
  - Transacciones multi-archivo con reversión total si falla la edición de algún componente en la cadena.

---

## 4. Las 8 Herramientas Fundamentales

AETHER incluye un catálogo integral de 28 herramientas, destacando las 8 esenciales para autonomía y seguridad:

| Herramienta | Categoría | Propósito Técnico |
| :--- | :--- | :--- |
| **`git_diff`** | Git | Inspecciona cambios propios frente al último commit con resaltado de sintaxis. |
| **`get_diagnostics`** | Code Intelligence | Valida sintaxis y extrae errores del AST en Python y JSON antes y después de editar. |
| **`apply_patch`** | Filesystem | Aplica parches transaccionales verificando SHA-256 y generando diffs unificados. |
| **`get_process_status`** | Execution | Consulta estado y logs de comandos largos sin congelar la interfaz. |
| **`cancel_process`** | Execution | Detiene forzosamente procesos iniciados por el agente (matando el árbol en Windows). |
| **`update_plan`** | Agent Management | Mantiene la lista de pasos, paso actual y criterios de aceptación visibles al usuario. |
| **`request_approval`** | Agent Management | Solicita confirmación explícita al usuario humano antes de acciones de alto impacto. |
| **`get_project_instructions`**| Agent Management | Carga reglas del repositorio (`AGENTS.md`, `.aetherrules`) como contexto no privilegiado. |

---

## 5. Máquina de Estados Formal del Agente

AETHER gestiona su ciclo de vida mediante un enum formal `AgentState` en lugar de flags booleanos dispersos:

```
  ┌──────┐
  │ IDLE │
  └──┬───┘
     │ (Solicitud de Usuario)
     ▼
┌──────────┐      (Acción Sensible)      ┌──────────────────┐
│ PLANNING │ ──────────────────────────► │ WAITING_APPROVAL │
└────┬─────┘                             └────────┬─────────┘
     │                                            │ (Aprobado)
     ▼                                            ▼
┌─────────┐      (Pruebas / Verificación) ┌───────────┐
│ RUNNING │ ────────────────────────────► │ VERIFYING │
└────┬────┘                               └─────┬─────┘
     │                                          │
     ├───────────────► ┌───────────┐ ◄──────────┤
     │  (Éxito)        │ COMPLETED │            │
     │                 └───────────┘            │
     ├───────────────► ┌───────────┐ ◄──────────┤
     │  (Fallo Fatal)  │  FAILED   │            │
     │                 └───────────┘            │
     └───────────────► ┌───────────┐ ◄──────────┘
        (Cancelación)  │ CANCELLED │
                       └───────────┘
```

---

## 6. Métricas de Pruebas y Validación (45 Tests Pasando)

El conjunto de pruebas automatizadas garantiza la robustez del sistema bajo Windows y PowerShell:

1. **`tests/test_agent_tools.py`**: Planes de ejecución, aprobación interactiva e ingestión de instrucciones (3 tests).
2. **`tests/test_checkpoints.py`**: Snapshots quirúrgicos, manifests y restauración no destructiva (2 tests).
3. **`tests/test_patch_engine.py`**: Reemplazo atómico, precondición SHA-256, ambigüedad y rollback (4 tests).
4. **`tests/test_permissions.py`**: Jaula de workspace, bloqueo de comandos peligrosos y callbacks (3 tests).
5. **`tests/test_process_manager.py`**: Ejecución en background, captura de buffers y terminación de árbol (2 tests).
6. **`tests/test_diagnostics.py`**: Parsing AST para Python y JSON (3 tests).
7. **`tests/test_session.py`**: Ciclo de vida relacional en SQLite y reanudación de mensajes (1 test).
8. **`tests/test_state_and_cancellation.py`**: Estados formales y cancelación thread-safe (3 tests).
9. **`tests/test_file_tools.py`**, **`test_git_tools.py`**, **`test_shell_tools.py`**, **`test_search_tools.py`**, **`test_hooks_and_modes.py`**, **`test_superpowers.py`**, **`test_orchestrator_parser.py`**, **`test_live_ollama.py`** (24 tests de integración).

**Resultado:** **45 / 45 pruebas pasadas (100% verde)**.
