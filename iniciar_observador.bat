@echo off
title Observador de Extractos - Activo
cd /d "%~dp0"
echo ========================================
echo  OBSERVADOR DE EXTRACTOS BANCARIOS
echo ========================================
echo.
echo Monitoreando: data\inbox\
echo Para detener: cierra esta ventana o presiona Ctrl+C
echo.
python pipeline\observar_inbox.py --silent
pause
