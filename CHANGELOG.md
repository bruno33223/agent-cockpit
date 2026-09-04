# Changelog

All notable changes to Agent Cockpit will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0] - 2026-09-04

### Added
- **Test & Error Distiller** (`server/test_runner.py`): New MCP tools `run_project_tests` and `get_slice_failure_report` that auto-detect `dotnet test`, `pytest`, and `npm test`, run silently, and return only failing asserts, file, line number, and clean stack trace — eliminating terminal noise and reducing token consumption by ~95%.
- **Dependency Graph Visualizer** (Code Graph tab): Interactive 2D Canvas workspace in the dashboard. New `server/code_graph.py` performs zero-LLM-cost static AST analysis of C#, Python, JS, and TS files. Clicking any node shows its symbols, line count, and computes the full impact zone.
- **New MCP tools**: `analyze_codebase_graph` and `query_symbol_impact`.
- **New REST endpoints**: `GET /api/graph` and `GET /api/metrics`.
- **Productivity Telemetry**: `state_store.get_metrics()` computes estimated tokens saved, first-pass approval rate, total attempts, and gauntlet verdict count in real time.
- **Professional Frontend Redesign (Anti-Slop)**: Full UI overhaul from generic AI look to a dark-tech engineering theme. Introduced 4-tab navigation: Visão Geral, Fluxo & Kanban, Code Graph, Gauntlet Log.
- **Custom Scrollbars**: Minimal 6px scrollbars with rounded corners via `::-webkit-scrollbar`.
- **1-Click Installer** (`install.bat`, `install.sh`, `setup_installer.py`): Auto-detects and configures MCP in Antigravity and Claude Desktop, installs dependencies, and copies skills.
- **`start_cockpit.bat` / `start_cockpit.sh`**: One-double-click launch scripts that open the dashboard in the browser automatically.
- **Bundled Skills**: `skills/cockpit`, `skills/spec-orchestrator`, `skills/gauntlet-loop` included in the package.

### Changed
- `state_store.py`: Replaced `threading.Lock` with `threading.RLock` to eliminate deadlock in nested state access.
- `web_server.py`: Added `/api/graph` and `/api/metrics` endpoints and imported `code_graph` module.
- `web/app.js`: Full rewrite to support tab switching, KPI grid, Canvas graph renderer, and impact analysis sidebar.
- `web/styles.css`: Complete dark-tech design system — custom palette, typography stack, and scrollbars.

---

## [1.0.0] - 2026-09-03

### Added
- Initial release of Agent Cockpit.
- `server/mcp_server.py`: Full JSON-RPC 2.0 stdio MCP server exposing 6 tools: `sync_blueprint`, `update_agent_pulse`, `log_critique_verdict`, `fetch_user_steering`, `post_orchestrator_message`, `get_cockpit_state`.
- `server/state_store.py`: Thread-safe atomic state machine backed by `workflow_state.json`.
- `server/web_server.py`: FastAPI server with WebSocket live push (`/ws`) and REST endpoints.
- `web/`: Initial dashboard with Kanban flow, Fleet Monitor, Human Steering chat, and Inspector Drawer.
- `run_cockpit.py`: Single-command launcher that starts Uvicorn on port 8765.
- `skills/spec-orchestrator`: Versioned blueprint workflow with Gauntlet Loop adversarial validation.
