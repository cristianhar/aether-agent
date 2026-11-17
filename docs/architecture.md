# AETHER IDE — Local-First Agentic Development Environment

> **Tu propio Cursor / Antigravity con IA local y capacidades de ingeniería inversa.**

---

## 📋 Resumen del Proyecto

**AETHER IDE** es un entorno de desarrollo integrado (IDE) de escritorio diseñado bajo el paradigma **local-first**. Integra agentes autónomos de programación, ejecución local de modelos de lenguaje (LLM) y herramientas especializadas de ingeniería inversa, eliminando la dependencia de suscripciones comerciales y protegiendo la privacidad total del código fuente.

No busca ser únicamente un clon visual de Cursor, sino una plataforma modular y extensible capaz de:
- Programar y refactorizar código de forma autónoma.
- Analizar repositorios y comprender el contexto del proyecto.
- Ejecutar pruebas unitarias y corregir bugs en un bucle cerrado.
- Analizar aplicaciones compiladas (binarios, ejecutables, DLLs, APKs).

### Perfil de Hardware Objetivo
- **GPU:** NVIDIA GeForce RTX 4060 Laptop (6 GB VRAM)
- **RAM:** 16 GB DDR4/DDR5
- **Entorno:** 100% Local y Offline-capable
- **Costo:** $0 USD en suscripciones recurrentes

---

## 1. Capacidades Principales

1. **IDE Profesional:**
   - Editor de código basado en **Monaco Editor** (el núcleo de VS Code).
   - Explorador de archivos en árbol, pestañas múltiples y diff viewer.
   - Terminal integrada multiplataforma.
   - Integración nativa con Git (staging, diff, commits, checkpoints).
   - Soporte para Language Server Protocol (LSP) para autocompletado y diagnósticos.

2. **AI Chat Contextual:**
   - Diálogo interactivo con contexto semántico del repositorio activo.
   - Inyección inteligente de archivos, símbolos y fragmentos relevantes.

3. **AI Agent (Programador Autónomo):**
   - Creación y edición precisa de múltiples archivos mediante diffs.
   - Ejecución de comandos de consola autorizados en un sandbox seguro.
   - Diagnóstico iterativo de errores y auto-reparación de código.

4. **Agent Planning (Planificación Estructurada):**
   - Descomposición de tareas complejas en pasos secuenciales verificables.
   - Criterios de aceptación explícitos por cada subtarea.
   - Modo de aprobación humana previo a la aplicación de cambios destructivos.

5. **Local AI Runtime:**
   - Inferencia local acelerada por GPU mediante **Ollama** o **llama.cpp**.
   - Soporte nativo para streaming, tool calling y salidas estructuradas JSON/Pydantic.

6. **Reverse Engineering Workspace:**
   - Descompilación y análisis estático automatizado de binarios, ejecutables (.exe, ELF), librerías dinámicas (.dll, .so) y paquetes móviles (.apk).
   - Orquestación headless de herramientas especializadas: **Ghidra**, **ILSpy CLI**, **JADX**.

---

## 2. Arquitectura General del Sistema

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       DESKTOP APPLICATION                               │
│            Electron + React + TypeScript + TailwindCSS                  │
│                                                                         │
│   ┌─────────────────┬─────────────────┬─────────────────────────────┐   │
│   │ File Explorer   │ Monaco Editor   │ AI Chat & Agent Panel       │   │
│   │ Git & Diff View │ Tab Management  │ Planning / Task Checkpoints │   │
│   ├─────────────────┴─────────────────┴─────────────────────────────┤   │
│   │ Integrated Terminal (xterm.js + node-pty)                       │   │
│   └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ WebSocket / Local IPC
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      LOCAL BACKEND (FastAPI / Python)                   │
│                                                                         │
│  ┌───────────────────────┐  ┌────────────────────────────────────────┐  │
│  │   Agent Orchestrator  │  │            Context Engine              │  │
│  │  • Planner (Pydantic) │  │  • Tree-sitter (AST / Symbols)         │  │
│  │  • Tool Calling Loop  │  │  • ripgrep (Búsqueda textual rápida)   │  │
│  │  • Checkpoints & Diff │  │  • SQLite FTS5 (Índice y embeddings)   │  │
│  │  • Sandbox & Perms    │  │  • Language Server Protocol (LSP)      │  │
│  └───────────┬───────────┘  └────────────────────────────────────────┘  │
│              │                                                          │
│  ┌───────────┴───────────┐  ┌────────────────────────────────────────┐  │
│  │   Local LLM Runtime   │  │          Tool Execution Engine         │  │
│  │  • Ollama / llama.cpp │  │  • Filesystem Tools (Read, Edit, Diff) │  │
│  │  • Qwen2.5-Coder 3B/7B│  │  • Terminal Sandbox (Shell execution)  │  │
│  │  • Structured Outputs │  │  • Git Manager (Snapshots / Rollback)  │  │
│  └───────────────────────┘  │  • Reverse Eng (Ghidra, ILSpy, JADX)   │  │
│                             └────────────────────────────────────────┘  │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Persistencia
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          WORKSPACE & STATE                              │
│       SQLite Local DB  ·  Git Repositories  ·  Task History Logs        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Stack Tecnológico

| Capa | Tecnología | Justificación y Responsabilidad |
| :--- | :--- | :--- |
| **Desktop App** | Electron | Gestión de ventanas nativas, procesos del SO y ciclo de vida de la app. |
| **Frontend UI** | React + TypeScript | Construcción de interfaz reactiva, paneles colapsables y gestión de estado. |
| **Editor de Código** | Monaco Editor | Núcleo de edición de VS Code: resaltado de sintaxis, minimapa, diff editor. |
| **Terminal** | xterm.js + node-pty | Emulación completa de terminal interactiva (PowerShell, Bash, CMD). |
| **Backend / API** | FastAPI + Python | Endpoints asíncronos de alta velocidad, WebSockets para streaming y orquestación. |
| **Inferencia LLM** | Ollama / llama.cpp | Motor de inferencia local optimizado para GPU (CUDA) con soporte de tool calling. |
| **AST / Parsing** | Tree-sitter | Análisis sintáctico para extracción precisa de funciones, clases y firmas de código. |
| **Búsqueda** | ripgrep + SQLite FTS5 | Búsqueda léxica ultrarrápida combinada con base de datos embebida FTS5. |
| **Diagnóstico Código** | LSP (Language Server) | Navegación de símbolos (*Go to Definition*), referencias y linting/errores en vivo. |
| **Control de Versiones**| Git | Creación automática de ramas/snapshots temporales para permitir *rollback* de cambios. |
| **Ingeniería Inversa** | Ghidra, ILSpy, JADX | Descompilación headless automatizada de binarios nativos (.exe/.so), .NET y Android. |

---

## 4. El Ciclo de Vida del Agente (Agent Engine)

El agente opera en un bucle cerrado de 6 fases para garantizar precisión y evitar modificaciones destructivas:

```
  ┌───────────────┐
  │ 1. UNDERSTAND │ ──▶ Analiza la instrucción del usuario y busca archivos relevantes.
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐
  │   2. PLAN     │ ──▶ Genera una lista de pasos con objetivos y criterios de validación.
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐
  │  3. EXECUTE   │ ──▶ Aplica herramientas validadas (read, edit_diff, run_command).
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐
  │  4. OBSERVE   │ ──▶ Recibe stdout, stderr, códigos de salida y estado del diff.
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐
  │   5. VERIFY   │ ──▶ Ejecuta pruebas unitarias, linters y valida que no haya regresiones.
  └───────┬───────┘
          │
          ▼
  ┌───────────────┐
  │   6. REPORT   │ ──▶ Presenta al usuario un resumen claro con el diff y resultados.
  └───────────────┘
```

### Mecanismos de Seguridad
- **Validación con Pydantic:** Toda invocación a una herramienta es deserializada y validada estrictamente.
- **Lista Blanca de Rutas:** Prohibición de escritura fuera del directorio del proyecto actual.
- **Permisos de Ejecución:** Comandos peligrosos (e.g. `rm -rf`, `format`, borrado de ramas) requieren confirmación manual del usuario.
- **Git Checkpoints:** Creación de un commit o snapshot temporal antes de que el agente ejecute modificaciones extensas, posibilitando un botón de **Rollback Inmediato**.

---

## 5. Estructura del Repositorio

```text
aether-ide/
├── apps/
│   └── desktop/
│       ├── electron/
│       │   ├── main.ts              # Proceso principal de Electron, IPC y spawn de FastAPI
│       │   └── preload.ts           # Context isolation y puente seguro IPC
│       └── src/
│           ├── components/          # Botones, modales, paneles colapsables
│           ├── editor/              # Configuración e instancia de Monaco Editor + DiffView
│           ├── terminal/            # Wrapper de xterm.js con soporte para WebSockets
│           ├── chat/                # Interfaz de chat, renderizado Markdown y syntax highlighting
│           ├── agents/              # UI de planificación, timeline de pasos y diff previews
│           └── workspace/           # Explorador de archivos en árbol y pestañas
│
├── services/
│   └── ai-engine/
│       ├── main.py                  # Servidor FastAPI, endpoints REST y WebSocket
│       ├── agents/
│       │   ├── orchestrator.py      # Bucle principal ReAct / Tool-Calling Loop
│       │   ├── planner.py           # Generador y validador de planes estructurados
│       │   └── verifier.py          # Verificación de sintaxis, linters y ejecución de tests
│       ├── tools/
│       │   ├── filesystem.py        # Lectura, creación, diff-patching seguro de archivos
│       │   ├── terminal.py          # Ejecución controlada de comandos en subprocesos
│       │   ├── git.py               # Gestión de snapshots, diffs y rollback
│       │   └── ghidra.py            # Puente headless para descompilación con Ghidra
│       ├── context/
│       │   ├── indexer.py           # Indexador de proyectos en segundo plano
│       │   ├── retrieval.py         # Algoritmo BM25 / FTS5 + embeddings híbridos
│       │   └── symbols.py           # Extractor de símbolos y grafos con Tree-sitter
│       ├── llm/
│       │   ├── ollama.py            # Cliente de inferencia Ollama con streaming y herramientas
│       │   └── models.py            # Modelos de datos y esquemas Pydantic para I/O
│       └── security/
│           ├── permissions.py       # Control de accesos y reglas de aprobación de usuario
│           └── sandbox.py           # Aislamiento y sanitización de comandos
│
├── packages/
│   └── shared/                      # Tipos compartidos TypeScript / JSON Schemas
├── tests/                           # Pruebas automatizadas de herramientas y orquestador
├── docs/                            # Documentación técnica de arquitectura y configuración
└── README.md
```

---

## 6. Estrategia de Optimización para 6 GB de VRAM

En una GPU **RTX 4060 Laptop (6 GB VRAM)**, el consumo de memoria debe balancearse entre los pesos del modelo, el buffer de contexto KV (Key-Value Cache) y la propia VRAM utilizada por Windows/DWM y Electron.

### Perfiles de Modelos Locales Recomendados

| Modelo | Cuantización | VRAM Requerida (Pesos) | VRAM con KV Cache (4K tokens) | Rendimiento / Idoneidad |
| :--- | :--- | :--- | :--- | :--- |
| **Qwen2.5-Coder 1.5B** | Q4_K_M / Q8_0 | ~1.2 - 1.8 GB | ~2.5 GB | **Ultra ligero.** Excelente para autocompletado en línea y parsing sintáctico rápido. |
| **Qwen2.5-Coder 3B** | Q4_K_M / Q5_K_M | ~2.2 - 2.8 GB | ~3.8 - 4.2 GB | **Recomendado para el MVP.** Óptimo equilibrio de razonamiento de código y estabilidad térmica. |
| **Qwen2.5-Coder 7B** | Q4_K_M | ~4.4 - 4.8 GB | ~5.8 - 6.4 GB (Riesgo de offload a RAM) | Muy capaz en lógica, pero al límite de los 6 GB. Requiere vigilar la temperatura. |

### Configuración Óptima Inicial:
```bash
# Descarga e instalación del modelo recomendado
ollama pull qwen2.5-coder:3b
```
- **Límite de Context Window:** 4,096 tokens (ajustable hasta 8K si la VRAM libre lo permite).
- **Consideración Térmica:** Dado que las laptops MSI pueden experimentar sobrecalentamiento, se recomienda monitorizar temperaturas durante sesiones largas de inferencia continua y mantener el ventilador en perfil de rendimiento o usar base refrigeradora.

---

## 7. Roadmap de Implementación (12 Semanas)

Estimación para un desarrollador con dedicación de 15 a 20 horas semanales:

```
┌────────────────────────────────────────────────────────────────────────┐
│ SEMANAS 1–2: Fundamentos del IDE                                       │
│ • Monorepo Electron + React + TypeScript + Vite                        │
│ • Integración de Monaco Editor (abrir, editar, guardar)                │
│ • Explorador de archivos y terminal integrada (xterm.js + node-pty)    │
│ • Servidor base FastAPI conectado por WebSocket                        │
│   🏁 Entregable: Editor funcional tipo VS Code minimalista             │
├────────────────────────────────────────────────────────────────────────┤
│ SEMANAS 3–4: Integración de IA Local                                   │
│ • Conexión con Ollama API (Streaming token por token)                  │
│ • Panel de Chat lateral con renderizado de código                      │
│ • Inyección de contexto manual (@file, selección activa)               │
│   🏁 Entregable: Editor con asistente de chat interactivo local        │
├────────────────────────────────────────────────────────────────────────┤
│ SEMANAS 5–6: Motor de Contexto Inteligente                             │
│ • Indexación con ripgrep y SQLite FTS5                                 │
│ • Parsing de AST con Tree-sitter para extracción de funciones/clases   │
│ • Algoritmo de retrieval híbrido para context packing                  │
│   🏁 Entregable: Chat con comprensión automática del proyecto          │
├────────────────────────────────────────────────────────────────────────┤
│ SEMANAS 7–8: Agente Autónomo de Programación                           │
│ • Bucle de orquestación ReAct con llamadas a herramientas (Pydantic)   │
│ • Herramientas: FileSystem (read/patch), Terminal Sandbox              │
│ • Sistema de verificación de diff y ejecución de tests automáticos     │
│   🏁 Entregable: El agente crea endpoints, edita archivos y corrige    │
├────────────────────────────────────────────────────────────────────────┤
│ SEMANAS 9–10: Experiencia "Cursor-Like"                                │
│ • Editor de diffs interactivo con botones de Aceptar / Rechazar cambio │
│ • Inline edits / Prompt flotante sobre líneas de código                │
│ • Snapshots y checkpoints automáticos con Git                          │
│   🏁 Entregable: Flujo de trabajo ágil similar a Cursor                │
├────────────────────────────────────────────────────────────────────────┤
│ SEMANAS 11–12: Ingeniería Inversa & Primera Release                     │
│ • Integración headless con Ghidra / ILSpy para descompilación de DLLs  │
│ • Workspace de binarios con visualizador de desensamblado              │
│ • Empaquetado de instaladores de escritorio (Electron Builder)         │
│   🏁 Entregable: AETHER IDE v0.1.0 Alpha instalable                    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Alcance del MVP vs Versiones Posteriores

| Característica / Módulo | En el MVP (v0.1) | Versión Posterior (v0.2+) |
| :--- | :---: | :---: |
| Editor de código Monaco con pestañas | ✅ Sí | — |
| Terminal integrada multiplataforma | ✅ Sí | — |
| Chat con IA local streaming (Ollama) | ✅ Sí | — |
| Lectura y referencia contextual de archivos (`@file`) | ✅ Sí | — |
| Edición autónoma multi-archivo | ✅ Sí | — |
| Diff interactivo (Aceptar/Rechazar cambios) | ✅ Sí | — |
| Agente con ciclo de verificación y tests | ✅ Sí | — |
| Autocompletado predictivo tipo Copilot (Ghost text) | ⏳ No | ✅ Sí |
| Sistema multiagente paralelo colaborativo | ⏳ No | ✅ Sí |
| Ingeniería inversa con Ghidra / ILSpy integrada | ⏳ No | ✅ Sí |
| Depuración interactiva paso a paso guiada por IA | ⏳ No | ✅ Sí |
| Soporte para modelos remotos opcionales (OpenRouter/APIs)| ⏳ No | ✅ Sí |
| Modo voz bidireccional | ⏳ No | ✅ Sí |

---

## 9. Checklist de Inicio Inmediato (Sprint 1)

- [ ] Inicializar monorepo (`pnpm` o `npm workspaces`).
- [ ] Configurar plantilla de **Electron + Vite + React + TypeScript**.
- [ ] Integrar **Monaco Editor** con carga de archivo activo, guardado y sintaxis.
- [ ] Desarrollar componente de **Explorador de Archivos** conectado al filesystem nativo.
- [ ] Integrar terminal **xterm.js** comunicada con **node-pty** vía IPC.
- [ ] Configurar servidor backend **FastAPI** en Python y conexión WebSocket con el frontend.
- [ ] Implementar cliente de streaming con **Ollama** consumiendo `qwen2.5-coder:3b`.
- [ ] Configurar almacenamiento persistente de historial de sesiones en SQLite.

