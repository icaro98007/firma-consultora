@echo off
title Consola RAG Revisoría Fiscal & KPO - Servidor Local
echo ======================================================================
echo   Iniciando Consola RAG Privada - Revisoría Fiscal & KPO
echo   URL de Acceso: http://localhost:8000
echo ======================================================================
echo.
echo Abriendo en el navegador...
timeout /t 1 >nul
start "" "http://localhost:8000"
python -m http.server 8000
pause
