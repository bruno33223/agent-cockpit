#!/usr/bin/env bash
cd "$(dirname "$0")"
echo "======================================================="
echo "       AGENT COCKPIT - INSTALADOR 1-CLIQUE"
echo "======================================================="
python3 setup_installer.py || python setup_installer.py
