#!/usr/bin/env bash
cd "$(dirname "$0")"

# Liberar porta 8765 se ja estiver ocupada
if command -v fuser >/dev/null 2>&1; then
    fuser -k 8765/tcp >/dev/null 2>&1 || true
elif command -v lsof >/dev/null 2>&1; then
    PID=$(lsof -ti :8765)
    if [ -n "$PID" ]; then
        kill -9 $PID 2>/dev/null || true
    fi
fi

echo "Abrindo Agent Cockpit..."
if which xdg-open > /dev/null; then
    xdg-open http://localhost:8765 &
elif which open > /dev/null; then
    open http://localhost:8765 &
fi
python3 run_cockpit.py || python run_cockpit.py
