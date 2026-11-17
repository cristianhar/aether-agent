@echo off
title AETHER IDE - Launcher Completo
cd /d "%~dp0"

echo ======================================================================
echo    AETHER IDE - EJECUTANDO TODO EL SISTEMA (100%% LOCAL)
echo    Hardware: NVIDIA RTX 4060 + Ollama (Qwen2.5-Coder 7B)
echo    Desktop:  Tauri v2 + Monaco Editor + Python Bridge API
echo ======================================================================
echo.

REM 1. Verificar entorno virtual Python
if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creando entorno virtual .venv...
    python -m venv .venv
    echo [1/4] Instalando dependencias de Python...
    call .venv\Scripts\pip.exe install -r requirements.txt
) else (
    echo [1/4] [OK] Entorno virtual Python listo.
)

REM 2. Verificar dependencias de Node en desktop/
if not exist "desktop\node_modules" (
    echo [2/4] Instalando dependencias de Node en desktop/...
    pushd desktop
    call npm install
    popd
) else (
    echo [2/4] [OK] Dependencias de Node listas.
)

REM 3. Verificar servicio Ollama
echo [3/4] Verificando motor Ollama...
curl.exe --connect-timeout 2 -s http://127.0.0.1:11434/api/tags >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo       Ollama no detectado. Iniciando 'ollama serve' en segundo plano...
    start "AETHER_OLLAMA" /B ollama serve
    ping 127.0.0.1 -n 4 >nul
)
echo       [OK] Ollama activo y listo.

REM 4. Iniciar Servidor Puente (Bridge API) en segundo plano
echo [4/4] Iniciando Servidor Puente (Bridge API en http://127.0.0.1:8765)...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8765" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)

start "AETHER_BRIDGE_SERVER" /min cmd /c ""%~dp0.venv\Scripts\python.exe" "%~dp0bridge\server.py""

REM Esperar respuesta del puente
echo       Esperando conexion con el puente...
for /L %%i in (1,1,10) do (
    curl.exe --connect-timeout 1 -s http://127.0.0.1:8765/api/status >nul 2>&1
    if not errorlevel 1 goto BRIDGE_READY
    ping 127.0.0.1 -n 2 >nul
)

:BRIDGE_READY
echo       [OK] Servidor Puente conectado y respondiendo.

echo.
echo ======================================================================
echo    AETHER IDE DESKTOP INICIANDO (Tauri v2 + Monaco Editor)
echo    Cierra la ventana de AETHER IDE para terminar la sesion.
echo ======================================================================
echo.

pushd desktop
call npm run tauri dev
set TAURI_EXIT=%ERRORLEVEL%
popd

REM Limpieza al salir
echo.
echo [AETHER] Cerrando procesos en segundo plano...
taskkill /fi "WINDOWTITLE eq AETHER_BRIDGE_SERVER*" /t /f >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8765" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
echo [AETHER] Todo cerrado correctamente.
if %TAURI_EXIT% NEQ 0 (
    echo [AETHER] La aplicacion finalizo con codigo de salida: %TAURI_EXIT%
    pause
)
