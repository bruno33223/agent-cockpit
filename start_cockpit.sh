#!/usr/bin/env bash
cd "$(dirname "$0")"
echo "Abrindo Agent Cockpit..."
if which xdg-open > /dev/null; then
    xdg-open http://localhost:8765 &
elif which open > /dev/null; then
    open http://localhost:8765 &
fi
python3 run_cockpit.py || python run_cockpit.py
