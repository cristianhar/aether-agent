@echo off
chcp 65001 >nul
title AETHER IDE - Local Agentic CLI
cd /d "%~dp0"

echo ======================================================================
echo    AETHER IDE - AGENTE PROGRAMADOR AUTONOMO 100%% LOCAL
echo    Hardware: NVIDIA RTX 4060 + Ollama (Qwen2.5-Coder 7B)
echo ======================================================================

REM Verificar si Ollama esta corriendo
curl -s http://127.0.0.1:11434/api/tags >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [AETHER] Iniciando servicio Ollama en segundo plano...
    start "" /B ollama serve
    timeout /t 3 >nul
)

if not exist ".venv\Scripts\python.exe" (
    echo [AETHER] Creando entorno virtual .venv...
    python -m venv .venv
    echo [AETHER] Instalando dependencias...
    .venv\Scripts\pip install -r requirements.txt
)

echo [AETHER] Iniciando consola agentica...
.venv\Scripts\python.exe main.py
if errorlevel 1 (
    echo.
    echo [AETHER] El programa termino con un error.
    pause
)
pause
