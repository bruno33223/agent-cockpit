@echo off
title Agent Cockpit Dashboard
cd /d "%~dp0"

echo =======================================================
echo          INICIANDO AGENT COCKPIT DASHBOARD
echo =======================================================
echo.
echo Abrindo em http://localhost:8765 ...
echo Para encerrar, feche esta janela do terminal.
echo.

start "" http://localhost:8765
python run_cockpit.py %*

pause
