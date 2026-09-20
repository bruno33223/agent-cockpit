#!/usr/bin/env bash
# Inicia o Agent Cockpit Desktop (Tauri)
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$DIR/agent-cockpit-desktop"

if [ ! -f "$BIN" ]; then
    BIN="/media/bruno/SteamGames/cargo-target/release/agent-cockpit"
fi

if [ ! -f "$BIN" ]; then
    echo "Compilando binário desktop..."
    cd "$DIR" && tauri build --no-bundle
fi

# Verifica se o backend do Cockpit está respondendo na porta 8765
if ! curl -s --connect-timeout 1 http://127.0.0.1:8765/api/cockpit/state > /dev/null 2>&1; then
    echo "Iniciando backend do Cockpit em segundo plano..."
    cd "$DIR" && python3 run_cockpit.py &
    sleep 2
fi

echo "Iniciando Agent Cockpit Desktop..."
exec "$BIN" "$@"
