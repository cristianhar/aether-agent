@echo off
echo ========================================================
echo    AETHER - APAGADO AUTOMATICO PROGRAMADO DEL SISTEMA
echo ========================================================
echo Todas las tareas, verificaciones y pruebas han concluido.
echo Tu equipo se apagara en 60 segundos.
echo Para CANCELAR el apagado de inmediato, presiona cualquier tecla.
echo ========================================================
shutdown /s /t 60 /c "AETHER ha finalizado todas las tareas con exito. Apagando equipo..."
pause
shutdown /a
echo.
echo [OK] El apagado automatico fue CANCELADO exitosamente.
echo ========================================================
