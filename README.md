# AETHER IDE — Local Agentic Developer (100% Offline)

> **Agente Programador Autónomo Local estilo Aider / Claude Code / Antigravity CLI impulsado por Ollama y optimizado para NVIDIA RTX 4060 (6 GB VRAM).**

---

## 🚀 Inicio Rápido

### 1. Requisitos Previos
- **Ollama** instalado y en ejecución en Windows.
- **Python 3.11+** o **3.12+**.
- **Git** configurado.

### 2. Descargar el Modelo Recomendado
En tu terminal de PowerShell:
```powershell
# Modelo de código de 7B (Óptimo para razonamiento de ingeniería y tool-calling)
ollama pull qwen2.5-coder:7b

# Opcional (versión ultra ligera de 3B para menor consumo de VRAM)
ollama pull qwen2.5-coder:3b
```

### 3. Ejecutar el Agente
Puedes iniciarlo de dos formas:

**Opción A — Lanzador directo (Windows):**
```powershell
.\aether.bat
```

**Opción B — Manualmente desde tu terminal:**
```powershell
# Activar entorno virtual
.venv\Scripts\activate

# Ejecutar CLI interactiva
python main.py
```

---

## 🛠️ Herramientas Nativas del Agente

El agente cuenta con un bucle ReAct (*Think -> Act -> Observe -> Verify*) gobernado por herramientas atómicas tipadas con Pydantic y JSON Schema:

| Herramienta | Función |
| :--- | :--- |
| `read_file(path, start_line, end_line)` | Lee fragmentos con numeración de líneas sin saturar la VRAM. |
| `edit_file(path, target, replacement)` | Modificación atómica por coincidencia exacta de caracteres e indentación. |
| `write_file(path, content)` | Creación de archivos nuevos asegurando directorios padre. |
| `run_command(command, cwd)` | Ejecución controlada en PowerShell (captura `stdout`, `stderr` y códigos de salida con timeout de seguridad). |
| `search_codebase(query, path)` | Búsqueda léxica ultra rápida mediante `ripgrep` o fallback en Python. |
| `list_directory(path, max_depth)` | Exploración del árbol de carpetas ignorando dependencias y temporales. |
| `create_checkpoint(message)` | Punto de restauración Git antes de cambios extensos. |
| `undo_checkpoint()` | Reversión instantánea al estado seguro anterior. |
| `get_git_diff()` | Inspección de diferencias en código modificado. |

---

## ⌨️ Comandos Especiales en la CLI

Dentro de la sesión interactiva `AETHER ❯`:

* `/diff` — Muestra el diff de cambios no commiteados con resaltado de sintaxis.
* `/status` — Lista los archivos modificados o creados.
* `/checkpoint [mensaje]` — Guarda un snapshot manual con Git.
* `/undo` — Deshace los cambios del agente y restaura el proyecto en 1 segundo.
* `/model <nombre>` — Cambia el modelo de Ollama en caliente (ej: `/model qwen2.5-coder:3b`).
* `/clear` — Limpia el historial de conversación actual.
* `/help` — Muestra la lista de comandos.
* `/exit` — Cierra la sesión.

---

## 🧪 Pruebas Automatizadas (Quality Gate)

El proyecto incluye una suite de pruebas unitarias para garantizar la confiabilidad del bucle de edición y seguridad:

```powershell
.venv\Scripts\python -m pytest tests/ -v
```

---

## 📁 Estructura del Proyecto

```text
IDE/
├── agent/
│   ├── memory.py            # Gestor de historial y recorte dinámico de contexto
│   ├── orchestrator.py      # Bucle ReAct y comunicación con Ollama
│   ├── prompts.py           # System prompts de ingeniería de software
│   └── safety.py            # Filtro de comandos peligrosos
├── tools/
│   ├── file_tools.py        # read_file, edit_file, write_file
│   ├── git_tools.py         # create_checkpoint, undo_checkpoint, get_git_diff
│   ├── registry.py          # Catálogo OpenAPI de herramientas y despachador
│   ├── search_tools.py      # list_directory y search_codebase
│   └── shell_tools.py       # run_command con sandbox y timeouts
├── tests/
│   ├── test_file_tools.py
│   ├── test_git_tools.py
│   ├── test_search_tools.py
│   └── test_shell_tools.py
├── aether.bat               # Lanzador para Windows
├── main.py                  # Consola interactiva enriquecida (Rich CLI)
├── requirements.txt         # Dependencias
└── README.md
```

