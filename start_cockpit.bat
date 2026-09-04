@echo off
title Agent Cockpit Dashboard
cd /d "%~dp0"

echo =======================================================
echo          INICIANDO AGENT COCKPIT DASHBOARD
echo =======================================================
echo.
:: Liberar porta 8765 se já estiver ocupada por instância anterior
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8765 ^| findstr LISTENING 2^>nul') do (
    echo Liberando porta 8765 em uso pelo processo PID %%a...
    taskkill /F /PID %%a >nul 2>&1
)

echo Abrindo em http://localhost:8765 ...
echo Para encerrar, feche esta janela do terminal.
echo.

start "" http://localhost:8765
python run_cockpit.py

pause
