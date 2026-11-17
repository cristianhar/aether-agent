# Plan Maestro de Implementación: Local Agentic IDE / CLI (100% Offline)

> **Agente Programador Autónomo Local estilo Aider / Claude Code / Antigravity CLI impulsado por Ollama y optimizado para NVIDIA RTX 4060 (6 GB VRAM).**

---

## 1. Visión y Objetivos del Proyecto

Construir una herramienta autónoma de ingeniería de software en terminal (CLI interactiva enriquecida) similar a **Aider**, **Claude Code** o **Antigravity CLI**, capaz de:

- **Inspeccionar código:** Explorar repositorios, listar árboles de archivos y buscar definiciones mediante búsqueda semántica o `ripgrep`.
- **Editar archivos con precisión atómica:** Aplicar modificaciones mediante búsqueda de cadenas exactas y reemplazo de bloques diff, evitando sobreescribir archivos enteros o truncar código.
- **Ejecutar terminal interactiva:** Correr tests unitarios, instalar paquetes, compilar y capturar salidas de error en tiempo real para autocorrección continua en un bucle cerrado.
- **Seguridad y reversibilidad instantánea:** Crear puntos de restauración automáticos con Git (*checkpoints/snapshots*) para deshacer cualquier cambio defectuoso con un solo comando (`undo`).
- **Cero costo de API:** 100% impulsado por `qwen2.5-coder:7b` sobre Ollama localmente.

---

## 2. Asignación Óptima de Hardware (NVIDIA RTX 4060 Laptop — 6 GB VRAM)

| Componente | Modelo / Tecnología | Memoria VRAM | Cómputo |
| :--- | :--- | :--- | :--- |
| **Cerebro (LLM)** | `qwen2.5-coder:7b-instruct-q4_K_M` | ~4.4 – 4.7 GB VRAM | GPU CUDA |
| **Context Window** | 8,192 – 16,384 tokens con Flash Attention | Dinámica / VRAM residual | GPU |
| **Búsqueda & Parser** | `ripgrep` + Python `ast` / `tree-sitter` | 0 MB VRAM | CPU (1–2 núcleos) |
| **Checkpoints & Git** | Git CLI nativo | 0 MB VRAM | Disco SSD NVMe |
| **Margen libre GPU** | Windows DWM + Display | ~1.3 – 1.5 GB VRAM | GPU |

> [!NOTE]
> `qwen2.5-coder:7b` es el estándar actual de la industria open-source para código: supera a CodeLlama-34B y compite estrechamente con GPT-4o-mini en generación de diffs precisos y tool-calling en formato JSON.

---

## 3. Fases de Desarrollo Paso a Paso

### Fase 1: Entorno y Configuración del Modelo
1. Instalar y verificar Ollama en Windows (`ollama serve`).
2. Descargar el modelo de código cuantizado:
   ```powershell
   ollama pull qwen2.5-coder:7b
   ```
3. Validar compatibilidad de tool-calling nativo con la API de Ollama (`/api/chat`).
4. Configurar entorno virtual Python 3.11/3.12 con dependencias mínimas:
   ```text
   ollama>=0.4.0
   rich>=13.7.0
   pydantic>=2.0.0
   prompt_toolkit>=3.0.0
   colorama>=0.4.6
   ```

---

### Fase 2: Suite Atómica de Herramientas del Agente (`tools/`)

El agente se rige por herramientas atómicas estrictamente tipadas con esquemas JSON OpenAPI / Pydantic:

1. **`read_file(path: str, start_line: int = 1, end_line: int = 200)`**
   - Lee fragmentos de código específicos para no desbordar la ventana de contexto de 8k tokens.
2. **`edit_file(path: str, target: str, replacement: str)`**
   - Búsqueda exacta de caracteres incluyendo sangría (`target`) y reemplazo en caliente (`replacement`). Si `target` no existe o aparece duplicado sin desambiguar, rechaza la edición con un error explícito para que el LLM rectifique.
3. **`write_file(path: str, content: str)`**
   - Crea archivos nuevos asegurando la creación recursiva de directorios padre.
4. **`run_command(command: str, cwd: str = ".")`**
   - Ejecuta comandos de terminal en PowerShell (ej: `pytest`, `npm test`, `git status`) con timeout de seguridad (ej. 30 segundos) y captura de `stdout` y `stderr`.
5. **`search_codebase(query: str, path: str = ".")`**
   - Búsqueda ultrarrápida usando `ripgrep` (`rg -n --column`) o fallback en Python puro.
6. **`list_directory(path: str, max_depth: int = 2)`**
   - Muestra el árbol de archivos excluyendo `.git`, `node_modules`, `venv`, `__pycache__`.

---

### Fase 3: Orquestador y Bucle ReAct (`agent/orchestrator.py`)

Ciclo continuo de resolución de tareas:
```
[Solicitud de Usuario]
         │
         ▼
 ┌───────────────┐
 │    THINK      │ ──▶ El LLM analiza el estado y emite razonamiento previo.
 └───────┬───────┘
         │
         ▼
 ┌───────────────┐
 │   ACT / CALL  │ ──▶ Invocación estructurada a herramienta (read, edit, run).
 └───────┬───────┘
         │
         ▼
 ┌───────────────┐
 │    OBSERVE    │ ──▶ Captura de output real del sistema de archivos o consola.
 └───────┬───────┘
         │
         ▼
 ┌───────────────┐
 │  SELF-CORRECT │ ──▶ Si hay error (stderr / test fail), itera hasta corregir.
 └───────────────┘
```

#### Reglas de Oro del System Prompt:
- **Piensa antes de actuar:** Explica brevemente qué archivo vas a inspeccionar y por qué.
- **Minimiza cambios:** Nunca reescribas un archivo de 500 líneas si solo vas a cambiar 3; utiliza `edit_file`.
- **Verifica siempre:** Tras modificar código, ejecuta las pruebas unitarias o comandos de verificación pertinentes con `run_command`.

---

### Fase 4: Seguridad, Checkpoints y Control de Versiones (`agent/safety.py`)

1. **Git Checkpoints Automáticos:**
   - Antes de iniciar la tarea, crea un commit temporal o stash: `git stash create` o commit con tag temporal `checkpoint-pre-task`.
   - Si el usuario solicita cancelar o el agente entra en un ciclo defectuoso, el comando `undo` ejecuta `git reset --hard HEAD~1` devolviendo el repositorio a su estado intacto en 1 segundo.
2. **Guardián de Comandos Peligrosos:**
   - Lista negra interactiva que exige confirmación explícita del usuario: `rm -rf`, `git reset --hard`, `format`, `drop database`, `taskkill /F`.

---

### Fase 5: Interfaz de Usuario CLI Enriquecida (`main.py`)

Interfaz de consola construida con `rich` y `prompt_toolkit`:
- **Paneles de estado:** Muestra el archivo activo, tokens consumidos y VRAM libre en GPU.
- **Diffs coloreados en vivo:** Imprime cambios en verde (`+`) y rojo (`-`) cuando el agente invoca `edit_file`.
- **Streaming de razonamiento:** Muestra la cadena de pensamiento del modelo en tiempo real antes de ejecutar una acción.

---

## 4. Estructura del Repositorio

```text
local-agentic-ide/
├── agent/
│   ├── __init__.py
│   ├── orchestrator.py      # Bucle ReAct principal y control de turnos
│   ├── prompts.py           # System prompts de programación y rol de ingeniero
│   ├── memory.py            # Gestor de historial y recorte dinámico de contexto
│   └── safety.py            # Filtro de comandos peligrosos y confirmaciones
├── tools/
│   ├── __init__.py
│   ├── file_tools.py        # read_file, edit_file, write_file
│   ├── shell_tools.py       # run_command con captura de stdout/stderr
│   ├── search_tools.py      # ripgrep wrapper y list_directory
│   └── git_tools.py         # Creación de checkpoints y rollback instantáneo
├── tests/
│   ├── test_file_tools.py
│   ├── test_shell_tools.py
│   └── test_agent_loop.py
├── main.py                  # Punto de entrada de la consola interactiva CLI
├── requirements.txt
└── README.md
```

---

## 5. Verificación y Casos de Prueba (Quality Gate)

1. **Test 1 — Exploración y lectura:**
   - *Prompt:* `"Explica qué hace la función X en este proyecto y en qué archivo está"`.
   - *Criterio:* Debe usar `search_codebase` y `read_file` sin inventar rutas.
2. **Test 2 — Modificación y Diff:**
   - *Prompt:* `"Crea una función auxiliar que calcule factoriales en utils.py y agrégala a las exportaciones"`.
   - *Criterio:* Debe usar `edit_file` aplicando el cambio con sangría exacta.
3. **Test 3 — Autocorrección autónoma en bucle cerrado:**
   - *Prompt:* `"Escribe un test que intencionalmente falle, corre el test, lee el fallo y corrígelo hasta que pase"`.
   - *Criterio:* Debe ejecutar `run_command("pytest")`, recibir el `stderr`, entender el fallo y realizar un nuevo `edit_file` hasta obtener código de salida `0`.

