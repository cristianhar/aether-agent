@echo off
chcp 65001 >nul
title AETHER IDE - Local Agentic CLI
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [AETHER] Creando entorno virtual...
    python -m venv .venv
    echo [AETHER] Instalando dependencias...
    .venv\Scripts\pip install -r requirements.txt
)

echo [AETHER] Iniciando entorno agéntico...
.venv\Scripts\python main.py
if errorlevel 1 pause
