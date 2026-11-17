<div align="center">

<img src="./assets/logo.svg" alt="AETHER IDE Logo" width="100%" />

# AETHER IDE

**Agente Autónomo de Ingeniería de Software Local y CLI Interactiva**

[![Tests](https://img.shields.io/badge/pruebas-61%20pasadas-brightgreen.svg)]()
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)]()
[![Repositorio](https://img.shields.io/badge/github-cristianhar%2Faether--agent-181717?logo=github)](https://github.com/cristianhar/aether-agent)
[![Licencia](https://img.shields.io/badge/licencia-MIT-purple.svg)]()
[![Hardware](https://img.shields.io/badge/hardware-Optimizado%20RTX%204060-76b900.svg)]()
[![Desktop](https://img.shields.io/badge/desktop-Tauri%20v2%20%2B%20Monaco-blueviolet.svg)]()
[![Costo API](https://img.shields.io/badge/costo-$0%20Offline-success.svg)]()

[English](./README.md) • [Guía de Arquitectura](./docs/architecture.md) • [Plan Maestro](./docs/plan_maestro.md) • [Arquitectura Tauri Desktop](./docs/desktop_tauri_architecture.md) • [Repositorio GitHub](https://github.com/cristianhar/aether-agent)

</div>

---

## ⚡ Descripción General

**AETHER IDE** es un agente autónomo de programación que opera **100% de forma local y offline** sobre tu tarjeta gráfica utilizando Ollama (`qwen2.5-coder:7b`). Reúne la autonomía en terminal de Claude Code, la edición quirúrgica y mapeo sintáctico de Cursor/Aider, y la privacidad y velocidad de un entorno local sin costo de suscripción.

A diferencia de los chats pasivos, AETHER opera como un ingeniero de software activo: inspecciona la estructura del repositorio, crea archivos reales en disco, ejecuta pruebas en sub-terminales, captura errores de ejecución y auto-repara el código de forma iterativa en un bucle cerrado.

---

## 🌟 Superpoderes y Capacidades Clave

| Capacidad | Implementación Técnica | Beneficio Práctico |
| :--- | :--- | :--- |
| **Bucle ReAct Autónomo** | Esquemas JSON Schema con streaming en `/api/chat` de Ollama | El agente selecciona herramientas, las ejecuta, observa la salida en consola y toma decisiones continuas. |
| **Motor Transaccional de Parches** | Escritura atómica (`.tmp` + `os.replace`), SHA-256 pre-check y reversión | Cero riesgo de corrupción de archivos, ediciones truncadas o colisiones de concurrencia. |
| **Motor de Permisos y Jaula** | Aislamiento en límites de workspace, patrones destructivos y confirmación | Impide destrucción accidental o modificaciones fuera del proyecto. |
| **Checkpoints Seguros por Archivo** | Snapshots de pre-imagen en `.aether/checkpoints/<id>/` | Restaura quirúrgicamente solo los archivos del agente sin `git reset --hard`. |
| **Persistencia SQLite de Sesiones** | Base de datos `.aether/sessions.db` con `/sessions` y `/resume` | Reanuda tareas y audita ejecuciones entre reinicios sin perder contexto. |
| **Gestor Asíncrono de Procesos** | Ejecución desacoplada con IDs de proceso y cancelación de árbol en Windows | Corre servidores o watchers sin bloquear el agente y deténlos con `/cancel`. |
| **Telemetría y Rendimiento** | Registro JSONL de latencias y reporte resumido (`/telemetry`) | Visibilidad en tiempo real de tiempos de inferencia y tasa de éxito de herramientas. |
| **Repo-Map Compacto** | Extracción sintáctica AST de clases, firmas y métodos | Mapea proyectos enteros en ~300 tokens sin saturar la memoria de contexto. |
| **Diagnósticos Estáticos AST** | Validación de sintaxis para Python y JSON (`get_diagnostics`) | Comprueba la validez sintáctica del código antes y después de aplicar cambios. |
| **Modos de Trabajo** | Sistema de hooks con soporte para `/mode ask`, `/mode agent`, `/mode plan` | Modo de solo lectura en `ask`; creación y ejecución con plenos poderes en `agent`. |
| **Subagentes Lógicos** | Contextos de conversación aislados compartiendo el modelo local | Delega investigaciones pesadas o auditorías a subagentes auxiliares sin ensuciar la memoria principal. |

---

## 🏗️ Diagrama de Arquitectura

```mermaid
flowchart TD
    User["Entrada del Desarrollador"] --> Orch["Orquestador ReAct"]
    Orch --> Hooks["Gestor de Hooks (PreToolUse)"]
    Hooks --> LLM["Ollama Local (Qwen 2.5 Coder 7B)"]
    LLM --> Decision{"¿Solicita Herramienta?"}
    Decision -- Sí --> ToolExec["Despachador Atómico de Herramientas"]
    ToolExec --> SysOps["I/O Disco / Subprocesos PowerShell / Git CLI"]
    SysOps --> Feedback["Salida STDOUT/STDERR"]
    Feedback --> HooksPost["Gestor de Hooks (PostToolUse)"]
    HooksPost --> Orch
    Decision -- No --> FinalResp["Terminal Interactiva (Rich / Markdown)"]
```

---

## 🚀 Inicio Rápido

### 1. Requisitos Previos
- **Python:** 3.10, 3.11 o 3.12 instalado.
- **Ollama:** Instalado y corriendo (`ollama serve`).
- **Modelo recomendado:**
  ```bash
  ollama pull qwen2.5-coder:7b
  ```

### 2. Instalación
Clona el repositorio y configura el entorno:
```bash
git clone https://github.com/cristianhar/aether-ide.git
cd aether-ide
python -m venv .venv

# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Ejecución
- **Windows (Lanzador con un clic):**
  ```cmd
  aether.bat
  ```
- **Lanzamiento directo por consola:**
  ```bash
  python main.py
  ```

---

## 🛠️ Comandos Slash (`/`)

| Comando | Descripción |
| :--- | :--- |
| `/cd <ruta>` | Cambia el directorio de trabajo activo y genera el nuevo Repo-Map. |
| `/mode [agent\|ask\|plan]` | Cambia entre modo autónomo, modo de solo lectura (preguntas) o planificación. |
| `/map` | Muestra la arquitectura completa del repositorio (clases, métodos, firmas). |
| `/test [ruta]` | Ejecuta pruebas con `pytest` y ofrece auto-sanación instantánea si algo falla. |
| `/diff` | Muestra los cambios actuales pendientes con resaltado de sintaxis. |
| `/commit [mensaje]` | Prepara todos los cambios (`git add -A`) y realiza un commit limpio. |
| `/export [archivo.md]` | Exporta la transcripción de la sesión y el código a un informe Markdown. |
| `/undo` | Revierte al último checkpoint seguro en 1 segundo. |
| `/model <nombre>` | Cambia el modelo de Ollama en caliente (ej: `/model qwen2.5-coder:7b`). |
| `/status` | Muestra el modelo activo, telemetría de tokens en VRAM y estado de Git. |
| `/clear` | Limpia la memoria de contexto para liberar VRAM. |
| `/exit` | Cierra la sesión de AETHER de forma segura. |

---

## 🧪 Pruebas Automatizadas

El proyecto incluye 24 pruebas automatizadas que validan la edición quirúrgica, linter, hooks, bucle ReAct y subagentes:

```bash
pytest -v
```

---

## 👤 Autor

Desarrollado por **Cristian Arboleda** ([@cristianhar](https://github.com/cristianhar))

Distribuido bajo la **Licencia MIT**.
