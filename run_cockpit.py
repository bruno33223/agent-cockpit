import os
import sys
import uvicorn

def main():
    port = 8765
    host = "127.0.0.1"

    print("=" * 68)
    print("           AGENT COCKPIT - PAINEL OFFLINE EM TEMPO REAL           ")
    print("=" * 68)
    print(f"[*] Dashboard Web:   http://localhost:{port}")
    print(f"[*] WebSocket Feed:  ws://localhost:{port}/ws")
    print(f"[*] Servidor MCP:    agent-cockpit/server/mcp_server.py (stdio)")
    print("=" * 68)
    print("\n[Instruções de Conexão no Antigravity MCP]:")
    print("Adicione o servidor ao seu mcp_config.json:")
    print('''
{
  "mcpServers": {
    "agent-cockpit": {
      "command": "python",
      "args": ["''' + os.path.abspath(os.path.join(os.path.dirname(__file__), "server", "mcp_server.py")).replace("\\", "\\\\") + '''"]
    }
  }
}
''')
    print("=" * 68)
    print("Iniciando servidor local do Cockpit... Pressione Ctrl+C para encerrar.\n")

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server"))
    uvicorn.run("web_server:app", host=host, port=port, log_level="info")

if __name__ == "__main__":
    main()
