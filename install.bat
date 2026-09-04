@echo off
title Instalador Agent Cockpit
cd /d "%~dp0"

echo =======================================================
echo          AGENT COCKPIT - INSTALADOR 1-CLIQUE
echo =======================================================
echo.

where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERRO] O Python nao foi encontrado no seu computador!
    echo Por favor, instale o Python 3.9+ em https://www.python.org/downloads/
    echo IMPORTANTE: Marque a opcao "Add python.exe to PATH" durante a instalacao.
    echo.
    pause
    exit /b 1
)

python setup_installer.py

echo.
pause
