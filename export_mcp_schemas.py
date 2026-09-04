import os
import sys
import json

base_dir = os.path.dirname(os.path.abspath(__file__))
server_dir = os.path.join(base_dir, "server")
sys.path.insert(0, server_dir)

from mcp_server import TOOLS_DEFINITIONS

target_dir = os.path.expanduser("~/.gemini/antigravity/mcp/agent-cockpit")
os.makedirs(target_dir, exist_ok=True)

for tool in TOOLS_DEFINITIONS:
    name = tool["name"]
    file_path = os.path.join(target_dir, f"{name}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(tool, f, indent=2, ensure_ascii=False)
    print(f"Exported tool: {name}")

print(f"Total tools exported: {len(TOOLS_DEFINITIONS)}")
