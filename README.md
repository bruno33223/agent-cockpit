<div align="center">

# Agent Cockpit

**Visual multi-agent telemetry, dependency graph, and test distiller for AI coding workflows.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![MCP](https://img.shields.io/badge/Protocol-MCP%20%28JSON--RPC%202.0%29-8A2BE2)]()
[![Antigravity](https://img.shields.io/badge/Works%20with-Google%20Antigravity-4285F4?logo=google&logoColor=white)]()
[![Claude](https://img.shields.io/badge/Works%20with-Claude%20Desktop-D97757?logo=anthropic&logoColor=white)]()

</div>

---

Agent Cockpit is a **local, offline control station** that gives you real-time visibility into AI-driven software development. It bridges any MCP-compatible AI client (Google Antigravity, Claude Desktop) with a live dashboard showing exactly what each agent is doing, what it built, what the critic rejected, and which files it touched — all without sending a single token of codebase context to an LLM.

```
AI Agent Fleet (3x3 pairs)         Agent Cockpit (local)
  ┌─────────────┐                  ┌────────────────────────────────┐
  │ Executor 1  │ ◀── MCP stdio ── │  MCP Server  │  State Store   │
  │ Reviewer 1  │                  │  (JSON-RPC)  │  (atomic JSON) │
  │ Executor 2  │                  │──────────────┤────────────────│
  │ Reviewer 2  │                  │  FastAPI + WebSocket           │
  │ Executor 3  │                  │──────────────┬────────────────│
  │ Reviewer 3  │                  │  Dashboard   │  http://       │
  └─────────────┘                  │  localhost   │  :8765         │
                                   └──────────────┴────────────────┘
```

---

## Features

### Visual Multi-Agent Dashboard
4-tab navigation updated in real time via WebSocket — no page reload ever needed.

| Tab | Description |
| :--- | :--- |
| **Overview** | KPI grid: slices approved, first-pass rate, estimated tokens saved, verdict count. |
| **Flow & Kanban** | Sequential node pipeline. Each node contains a 4-column micro-kanban (`Backlog → Builder → Critic → Approved`) where cards transition as agents work. |
| **Code Graph** | Interactive 2D canvas with zero-LLM-cost AST analysis. Click any node to see its symbols and compute its full dependency impact zone. |
| **Gauntlet Log** | Full history of adversarial Builder vs. Harsh Critic verdicts with timestamps and rationale. |

### MCP Server (JSON-RPC 2.0 over stdio)

10 tools available to any MCP-compatible AI client:

| Tool | Description |
| :--- | :--- |
| `sync_blueprint` | Initialize flow nodes with the Master Blueprint and vertical slice acceptance criteria, generating `blueprint.lock.json`. |
| `update_agent_pulse` | Update 3x3 pair telemetry and move a Kanban card in real time. |
| `log_critique_verdict` | Record an approval or rejection in the Gauntlet Log. |
| `fetch_user_steering` | Read queued human instructions from the dashboard chat. |
| `post_orchestrator_message` | Send orchestrator replies back to the dashboard chat. |
| `get_cockpit_state` | Return a full JSON snapshot of the current system state. |
| `run_project_tests` | Run the project test suite (auto-detects `dotnet test`, `pytest`, `npm test`) and return only failing assertions and stack traces — stripping all terminal noise. |
| `get_slice_failure_report` | Retrieve the distilled failure history for a specific vertical slice. |
| `analyze_codebase_graph` | Scan the codebase with static AST analysis and return the full dependency graph. |
| `query_symbol_impact` | Given a file or symbol, return every file that imports it (impact zone). |
| `generate_handoff` | Generate a standardized `HANDOFF.md` in disk for seamless session continuity. |
| `read_last_handoff` | Read the most recent `HANDOFF.md` to resume work in a new session with zero context drift. |
| `get_slice_spec` | Retrieve only the isolated specification of a single vertical slice (saving 70-80% tokens). |
| `check_human_gate` | Verify human authorization status for release/ship gates from the dashboard. |

### Zero-Token Codebase Map
The **Code Graph** tab renders a force-directed interactive graph of your entire repository without calling any LLM. Uses regex-based AST parsing of C#, Python, JS, and TS files — runs in under 500ms on most projects.

### Test & Error Distiller
Instead of feeding thousands of lines of `dotnet build` output to an agent, `run_project_tests` returns a compact JSON like:
```json
{
  "status": "FAILURES",
  "total_tests": 42,
  "failed": 2,
  "failures": [
    {
      "test": "WeaponPipeline.Tests.TestSingularityVortex",
      "file": "tests/WeaponPipelineTests.cs",
      "line": 87,
      "message": "Expected: 0.95  Actual: 0.73"
    }
  ]
}
```
The builder agent gets exactly what it needs and nothing else. ~95% token reduction on test feedback loops.

---

## Quick Start

### Prerequisites
- **Python 3.9+** — [Download](https://python.org/downloads/) *(Windows: check "Add python.exe to PATH")*
- A MCP-compatible AI client: [Google Antigravity](https://deepmind.google/antigravity) or [Claude Desktop](https://claude.ai/download)

### 1-Click Install (Windows)
```
1. Download or clone this repository
2. Double-click  install.bat
```
The installer will:
- Verify your Python version
- Install `fastapi`, `uvicorn`, `websockets`, `pydantic` via pip
- Auto-configure the MCP server in Antigravity and Claude Desktop config files
- Copy the bundled skills (`cockpit`, `spec-orchestrator`, `gauntlet-loop`) to your user skill directory

### macOS / Linux
```bash
chmod +x install.sh
./install.sh
```

### Manual Install
```bash
pip install -r requirements.txt
```

Then add to your AI client MCP config (`~/.gemini/config/mcp_config.json` or Claude Desktop):
```json
{
  "mcpServers": {
    "agent-cockpit": {
      "command": "python",
      "args": ["/absolute/path/to/agent-cockpit/server/mcp_server.py"]
    }
  }
}
```

---

## Running the Dashboard

**Windows (double-click):**
```
start_cockpit.bat
```

**Terminal (all platforms):**
```bash
python run_cockpit.py
```

Open your browser at **`http://localhost:8765`**.

---

## Connecting Your AI Agent

With the dashboard running, start a session in your AI client and use the bundled skills:

```
Activate the /cockpit skill and orchestrate this project using /spec-orchestrator
```

The orchestrator will:
1. Call `sync_blueprint` — nodes appear in the Flow & Kanban tab
2. Spawn 3 executor/reviewer pairs — telemetry updates in real time
3. Call `run_project_tests` after each implementation — only failures are processed
4. Call `log_critique_verdict` — verdicts accumulate in the Gauntlet Log
5. Steer the whole process through `fetch_user_steering` — you can type instructions directly in the dashboard chat

---

## Architecture

```
agent-cockpit/
│
├── server/                         # Backend
│   ├── mcp_server.py               # JSON-RPC 2.0 stdio MCP server (10 tools)
│   ├── state_store.py              # Thread-safe atomic state machine + metrics
│   ├── web_server.py               # FastAPI: REST API + WebSocket live push
│   ├── code_graph.py               # AST dependency graph analyzer (no LLM)
│   └── test_runner.py              # Test distiller: dotnet/pytest/npm
│
├── web/                            # Frontend (no build step)
│   ├── index.html                  # 4-tab SPA shell
│   ├── styles.css                  # Dark-tech design system + custom scrollbars
│   └── app.js                      # Tab switcher, WebSocket handler, Canvas graph
│
├── skills/                         # Bundled AI skills (auto-installed)
│   ├── cockpit/                    # Cockpit activation skill
│   ├── spec-orchestrator/          # Spec-driven 3x3 orchestrator skill
│   └── gauntlet-loop/              # Adversarial Builder vs Critic loop skill
│
├── docs/                           # Documentation assets
│   └── screenshots/
│
├── run_cockpit.py                  # Entry point: starts Uvicorn on port 8765
├── setup_installer.py              # Cross-platform installer and MCP configurator
├── test_cockpit.py                 # Integration tests for MCP and web server
│
├── install.bat                     # Windows 1-click installer
├── install.sh                      # macOS/Linux installer
├── start_cockpit.bat               # Windows 1-click launcher
├── start_cockpit.sh                # macOS/Linux launcher
├── requirements.txt                # Python dependencies
├── CHANGELOG.md
├── CONTRIBUTING.md
└── LICENSE
```

**Data flow:**
```
AI Agent  ──stdio──▶  mcp_server.py
                          │
                    state_store.py  ──▶  workflow_state.json
                          │
                    web_server.py  ──▶  WebSocket /ws  ──▶  Browser Dashboard
                                   ──▶  REST /api/*    ──▶  Browser Dashboard
```

---

## REST API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/state` | Full current state snapshot |
| `GET` | `/api/metrics` | Productivity KPIs (tokens saved, approval rate) |
| `GET` | `/api/graph` | Codebase dependency graph (nodes + edges) |
| `GET` | `/api/health` | Health check `{"status": "healthy"}` |
| `POST` | `/api/steering` | Queue a human instruction for the orchestrator |
| `POST` | `/api/reset` | Reset the state machine to its initial state |
| `WS` | `/ws` | Live push: receives full state on every change |

---

## Running Tests

```bash
python test_cockpit.py
```

The test suite starts the server in-process, validates the MCP JSON-RPC handshake, state store atomicity, WebSocket delivery, and all REST endpoints.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Areas most in need of contributions:
- Code graph support for Go, Rust, Java
- New test runner backends (`cargo test`, `go test`, `jest --json`)
- Claude Desktop and Cursor Desktop deep integration

---

## License

[MIT](LICENSE) © 2026 lekdohacking contributors
