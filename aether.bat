@echo off
title AETHER IDE - Master Control Launcher
cd /d "%~dp0"

REM Manejo de argumentos directos
if "%1"=="--desktop" goto RUN_DESKTOP
if "%1"=="--all" goto RUN_DESKTOP
if "%1"=="-d" goto RUN_DESKTOP
if "%1"=="1" goto RUN_DESKTOP
if "%1"=="--cli" goto RUN_CLI
if "%1"=="-c" goto RUN_CLI
if "%1"=="2" goto RUN_CLI
if "%1"=="--web" goto RUN_WEB
if "%1"=="-w" goto RUN_WEB
if "%1"=="3" goto RUN_WEB
if "%1"=="--test" goto RUN_TESTS
if "%1"=="-t" goto RUN_TESTS
if "%1"=="4" goto RUN_TESTS
if "%1"=="--bridge" goto RUN_BRIDGE
if "%1"=="-b" goto RUN_BRIDGE
if "%1"=="5" goto RUN_BRIDGE

:MENU
cls
echo ======================================================================
echo    AETHER IDE - CENTRO DE CONTROL MAESTRO (100%% LOCAL)
echo    Hardware: NVIDIA GeForce RTX 4060 + Ollama (Qwen2.5-Coder 7B)
echo ======================================================================
echo.
echo   [1] Ejecutar Todo (Tauri Desktop + Monaco Editor + Bridge API)
echo   [2] Consola Autonoma CLI (Terminal interactiva ReAct)
echo   [3] Modo Web en Navegador (Vite Dev Server + Bridge API)
echo   [4] Ejecutar Suite de Tests Automatizados (pytest 63/63)
echo   [5] Iniciar unicamente Servidor Puente (puerto 8765)
echo   [6] Salir
echo.
echo ======================================================================
CHOICE /C 123456 /T 8 /D 1 /M "Selecciona una opcion [1-6] (Por defecto 1 en 8s): "

if errorlevel 6 goto EXIT
if errorlevel 5 goto RUN_BRIDGE
if errorlevel 4 goto RUN_TESTS
if errorlevel 3 goto RUN_WEB
if errorlevel 2 goto RUN_CLI
if errorlevel 1 goto RUN_DESKTOP

:RUN_DESKTOP
echo.
call "%~dp0run.bat"
goto END

:RUN_CLI
echo.
echo [AETHER] Verificando entorno virtual y Ollama...
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    call .venv\Scripts\pip.exe install -r requirements.txt
)
curl.exe --connect-timeout 2 -s http://127.0.0.1:11434/api/tags >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [AETHER] Iniciando Ollama...
    start "" /B ollama serve
    ping 127.0.0.1 -n 4 >nul
)
echo [AETHER] Iniciando consola autonoma interactiva...
.venv\Scripts\python.exe main.py
pause
goto END

:RUN_WEB
echo.
echo [AETHER] Iniciando servidor puente y servidor web Vite...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8765" ^| findstr "LISTENING"') do (
    taskkill /f /pid %%a >nul 2>&1
)
start "AETHER_BRIDGE_SERVER" /min cmd /c ""%~dp0.venv\Scripts\python.exe" "%~dp0bridge\server.py""
ping 127.0.0.1 -n 3 >nul
echo [AETHER] Abriendo interfaz en el navegador...
start http://localhost:1420
pushd desktop
call npm run dev
popd
taskkill /fi "WINDOWTITLE eq AETHER_BRIDGE_SERVER*" /t /f >nul 2>&1
pause
goto END

:RUN_TESTS
echo.
echo [AETHER] Ejecutando suite completa de 63 pruebas unitarias...
.venv\Scripts\pytest -v
pause
goto END

:RUN_BRIDGE
echo.
echo [AETHER] Iniciando Servidor Puente en primer plano en http://127.0.0.1:8765...
.venv\Scripts\python.exe bridge/server.py
pause
goto END

:EXIT
echo Saliendo de AETHER IDE.
exit /b 0

:END
exit /b 0
