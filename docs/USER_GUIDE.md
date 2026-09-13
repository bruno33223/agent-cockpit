# 🚀 User Guide: Installing and Using Agent Cockpit

Welcome to **Agent Cockpit**! This suite transforms how AI models write and govern code on your workstation by establishing an offline ecosystem featuring **real-time visual telemetry**, a **zero-token AST dependency graph**, and **multi-agent orchestration with automated test distillation**.

---

## ⚡ 1-Minute Setup (Single-Click Mode)

### Prerequisites:
- **Python 3.9+** installed ([Download Python](https://www.python.org/downloads/)).  
  *(When installing, ensure **"Add python.exe to PATH"** is checked)*.

### Step-by-Step:
1. **Extract or clone the repository** to any folder (e.g., `C:gent-cockpit` or `~/Projects/agent-cockpit`).
2. Run the automated installer:
   - On Linux/macOS:
     ```bash
     ./install.sh
     ```
   - On Windows:
     Double-click **`install.bat`**
3. The installer automatically:
   - Installs required dependencies (`FastAPI`, `Uvicorn`, `WebSockets`, `Pydantic`).
   - Configures the MCP server in your AI harness (Google Antigravity and Claude Desktop).
   - Installs essential skills (`cockpit`, `spec-orchestrator`, `gauntlet-loop`).

---

## 🖥️ Launching the Visual Dashboard

Whenever you program with AI and want real-time telemetry on screen:

1. **On Linux / macOS:**
   - Agent Cockpit can start automatically upon system boot (via the installer or the **Autostart** toggle button on the top bar).
   - Or start manually via terminal:
     ```bash
     ./start_cockpit.sh
     # or
     python3 run_cockpit.py
     ```
2. **On Windows:**
   - Double-click **`start_cockpit.bat`**
3. The dashboard opens automatically in your browser:
   🌐 **http://localhost:8765**

---

### ⚙️ Operating System Autostart (Linux)
Manage autostart at any time:
- **Via Web Interface:** Click the `Autostart` toggle in the top actions bar.
- **Via CLI:**
  - Status: `python3 run_cockpit.py --autostart-status`
  - Enable: `python3 run_cockpit.py --autostart-enable`
  - Disable: `python3 run_cockpit.py --autostart-disable`

---

## 🤖 Using with AI Orchestrators (Antigravity or Claude)

With the server installed and dashboard running, open your project and message your AI harness:

```text
Activate the /cockpit skill and orchestrate this epic using /spec-orchestrator.
```

### Real-Time Telemetry Flow:
1. **Blueprint Synchronization:** The orchestrator outlines vertical slices, rendering interactive nodes on the canvas.
2. **3x3 Fleet Telemetry:** Watch 3 paired agents execute in parallel:
   - `Executor 1 ⟷ Reviewer 1` (Infrastructure & Contracts)
   - `Executor 2 ⟷ Reviewer 2` (Core Logic & Domain)
   - `Executor 3 ⟷ Reviewer 3` (User Interface & Integration)
3. **Micro-Kanban Nodes:** Cards automatically transition from `Backlog` ➔ `Builder` ➔ `Critic` ➔ `Approved`.
4. **Distilled Test Runner:** Cockpit runs test suites and extracts only relevant failure traces, saving thousands of LLM context tokens.
5. **Code Graph Tab:** Explore file relationships and symbol dependencies mapped with zero LLM overhead.
6. **Human Steering Chat:** Send steering directions directly from the web dashboard; the AI consumes instructions on the next execution loop.

---

## 🛠️ Troubleshooting

- **"Python command not found":** Reinstall Python ensuring *"Add python.exe to PATH"* is checked.
- **"Port 8765 already in use":** The launcher automatically identifies and recycles stale Cockpit instances. If occupied by an unrelated service (e.g., Docker or PostgreSQL), run on an alternate port: `python run_cockpit.py --port 8766`.
- **Manual MCP Configuration (for Cursor, Cline, or custom clients):**
  Add to your `mcp_config.json`:
  ```json
  {
    "mcpServers": {
      "agent-cockpit": {
        "command": "python",
        "args": [
          "/FULL/PATH/TO/agent-cockpit/server/mcp_server.py"
        ]
      }
    }
  }
  ```
