<div align="center">

# Agent Cockpit 🎛️

**Visual Multi-Agent Telemetry, AST Dependency Graph & Governance Hub for AI Coding Fleets**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![MCP](https://img.shields.io/badge/Protocol-MCP%20%28JSON--RPC%202.0%29-8A2BE2)]()
[![Obsidian](https://img.shields.io/badge/Vault-Obsidian%20Compatible-7C3AED?logo=obsidian&logoColor=white)](https://obsidian.md)
[![Zero-Token](https://img.shields.io/badge/Architecture-Zero--Token%20AST-00C853)]()
[![Antigravity](https://img.shields.io/badge/Works%20with-Google%20Antigravity-4285F4?logo=google&logoColor=white)]()
[![Claude](https://img.shields.io/badge/Works%20with-Claude%20Desktop-D97757?logo=anthropic&logoColor=white)]()

</div>

---

**Agent Cockpit** is a local, offline command center and telemetry server built for spec-driven multi-agent AI development. It bridges MCP-compatible AI orchestrators ([Google Antigravity](https://deepmind.google/antigravity), Claude Desktop) with a real-time reactive dashboard showing agent fleet status, vertical slice kanbans, adversarial review logs, session handoffs, and an interactive AST dependency graph integrated with Obsidian.

All structural codebase intelligence, graph mapping, and test distillation happen **100% locally with zero LLM token consumption**.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        AI FLEET & ORCHESTRATOR                         │
│   Pair 1: Infra & Contracts │ Pair 2: Domain & Logic │  Pair 3: UI     │
│   (Executor + Reviewer)     │ (Executor + Reviewer)  │  (Exec+Review)  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ stdio (JSON-RPC 2.0)
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                         AGENT COCKPIT SERVER                           │
│  ┌─────────────────────────┐  ┌─────────────────────────────────────┐  │
│  │   MCP Server (stdio)    │  │        FastAPI & WebSockets         │  │
│  │  14 Specialized Tools   │  │   REST API + Real-time Push (/ws)   │  │
│  └───────────┬─────────────┘  └──────────────────┬──────────────────┘  │
│              │                                   │                     │
│  ┌───────────▼─────────────┐  ┌──────────────────▼──────────────────┐  │
│  │ State Machine & Metrics │  │ Code Graph & Obsidian Vault Sync    │  │
│  │   (Atomic JSON Store)   │  │ AST Parser • Wikilinks • Notes DB   │  │
│  └─────────────────────────┘  └─────────────────────────────────────┘  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                  LOCAL DIRECTORY: ./cockpit-agent/                     │
│   ├── blueprints/           # Master Blueprints, Locks & Handoffs      │
│   └── vault/                # Obsidian-compatible Markdown Knowledge   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 📸 Interface Showcase

### 1. Overview Dashboard & Live Steering
A central control room displaying real-time productivity KPIs, fleet execution states, active epic banners, and a bidirectional human-in-the-loop steering chat.

![Overview Dashboard](docs/screenshots/screenshot_2.png)

- **KPI Grid**: Track tokens saved via AST indexing, first-pass review approval rate, vertical slices completed, and MCP/WebSocket heartbeat.
- **Fleet 3x3 (Live)**: Real-time telemetry for all 3 executor/reviewer pairs (Infra, Domain, UI).
- **Steering Chat**: Chat directly with the AI orchestrator to inject human instructions or course corrections mid-flight without context loss.

---

### 2. Vertical Slices Flowchart (Flow & Kanban)
Pipeline visualizer where vertical slices operate as autonomous micro-kanbans (`Backlog → Builder → Critic → Approved`) ending in a unified release integration gate.

![Flow & Kanban](docs/screenshots/screenshot_3.png)

- **Per-Slice Micro-Kanban**: Immediate visual feedback as cards shift dynamically when agents commit code or submit work for review.
- **Final Integration Gate**: Automatic global cohesion verification and regression test validation before final release sign-off.

---

### 3. Slice Inspection Drawer (Slice Detail & Acceptance Criteria)
Click any slice in the pipeline to open the lateral inspection drawer containing the full vertical specification, checklist, and audit history.

![Inspection Drawer](docs/screenshots/screenshot_4.png)

- **Acceptance Criteria**: Markdown checklists extracted directly from `MASTER_BLUEPRINT.md`.
- **Master Blueprint Viewer**: Full slice context isolated from the rest of the project.
- **Integrated Gauntlet Log**: View historical passes, rejections, and test assertions specific to that slice.

---

### 4. AST Dependency Graph & Obsidian Constellation (Code Graph)
Interactive 2D constellation canvas powered by AST regex parsing. Zero tokens, zero external API calls.

![Code Graph](docs/screenshots/screenshot_1.png)

- **Constellation View**: Nodes sized proportionally to connectivity (degree) and color-coded by directory clusters (`Entities`, `Core`, `Systems`, `UI`, `Tests`, etc.).
- **Cluster Filter Bar**: Instant filter pills at the top to isolate specific subsystems with a single click.
- **Smart Navigation**: Click any node to focus and open its drawer; click the canvas background or a cluster filter to deselect; double-click a node to toggle focus off.
- **Obsidian Note Editor**: Lateral drawer displaying symbols (classes, methods, interfaces) and allowing instant markdown note editing saved straight to the Obsidian Vault.

---

### 5. Gauntlet Audit Log (Adversarial Review History)
Immutable historical record of every adversarial review round between Builders and Harsh Critics.

![Gauntlet Log](docs/screenshots/screenshot_5.png)

- **Blind Code Audit**: Critics evaluate implementations against acceptance criteria without knowing internal builder shortcuts.
- **Detailed Audit Trail**: Captures passed unit tests, coverage requirements, and actionable feedback across failure loops.

---

### 6. Session Handoff & Worklog (Zero-Token Context Drift)
Persistent on-disk session memory located at `./cockpit-agent/blueprints/{epic}/HANDOFF.md` enabling instant session resumption with zero token drift.

![Session Handoff](docs/screenshots/screenshot_6.png)

- **Epic Summary**: High-level overview of delivered capabilities.
- **Touched Files Inventory**: Complete manifest of created and modified source files and tests.
- **Test Status & Next Steps**: Ready-to-use briefing for the next developer or agent session.

---

## 🏛️ Architectural Practices & Governance (KISS, Clean, SOLID)

The orchestrator operates with a **Staff Software Engineer & Senior Architecture Advisor** mindset, enforcing **radical pragmatism**: mastering Clean Architecture, SOLID principles, and proven design patterns, but knowing precisely when to use them and—critically—when to avoid over-engineering in favor of simplicity (**KISS**) and continuous value delivery.

### 1. KISS & Radical Pragmatism (No Over-Engineering)
- **Anti-Overengineering Rule**: Never introduce speculative abstractions, factories-of-factories, or premature generalized frameworks for hypothetical future requirements.
- **Direct & Legible Solutions**: Favor transparent, straightforward implementations over complex layers of indirection. Code must be immediately obvious and easily maintainable.
- **Continuous Value Delivery**: Each iteration must deliver concrete, working features rather than sprawling architectural scaffolding.

### 2. Clean Architecture & Domain Isolation
- **Boundary Separation**: Decouples core business logic and domain entities from external frameworks, rendering engines, databases, and UI components.
- **Dependency Rule**: Dependencies always point inward toward high-level domain policies, never outward toward volatile implementation details.
- **Testability First**: Isolated domain structures ensure business rules are validated with fast, deterministic unit tests without spinning up heavy external dependencies.

### 3. SOLID Principles in Practice
- **Single Responsibility (SRP)**: Every class and subsystem has a single, well-defined reason to change. The 3x3 fleet divides vertical concerns cleanly (contracts, core domain, UI wiring).
- **Open/Closed (OCP) & Extension Points**: Existing code is protected. New behaviors are plugged in via designated hooks, events, or modular extension points rather than mutating core established structures.
- **Liskov Substitution (LSP)**: Polymorphic components and specialized implementations honor base contracts without surprise side-effects or broken invariants.
- **Interface Segregation (ISP)**: Lean, purposeful interfaces tailored specifically to what client consumers actually require, preventing bloated fat contracts.
- **Dependency Inversion (DIP)**: High-level systems interact through clear abstractions and contracts rather than depending directly on volatile low-level mechanics.

### 4. Vertical Slice Architecture
Instead of traditional, horizontal siloed layers (where database schemas, domain models, and UI screens are built weeks apart across disconnected branches), features are split into **self-contained vertical slices**:
- **Slice 1 (Contracts & Infra)**: Data structures, interfaces, and core persistence schemas.
- **Slice 2 (Domain & Business Logic)**: Rules, physics, state machines, and calculations.
- **Slice 3 (UI, Integration & Polish)**: User interaction, audio/visual wiring, and integration.

Each slice is an end-to-end, testable deliverable that adds verified functionality to the system.

### 5. Pre-flight Collision Check & Declarative File Locks
When multiple subagents operate concurrently in parallel:
- **Exclusive File Ownership**: Each domain file or entity is strictly assigned to exactly one builder agent. Modifying files outside the agent's assigned lock is forbidden.
- **Shared Append-Only Points**: Central aggregation hubs (e.g., `app.ts`, `container.py`, `Program.cs`) are designated as *Shared Append-Only*. Agents only register or wire their subsystems in earmarked sections, preventing destructive merge conflicts and race conditions.

---

## 📂 Standardized `./cockpit-agent/` Directory Architecture

To keep your project's root clean and ensure native compatibility with tools like [Obsidian](https://obsidian.md), Agent Cockpit standardizes all governance artifacts inside a unified `./cockpit-agent/` directory:

```
<your-project-root>/
└── cockpit-agent/
    ├── blueprints/
    │   └── {NN_epic_name}/
    │       ├── MASTER_BLUEPRINT.md    # Pragmatic vertical specification
    │       ├── blueprint.lock.json    # Immutable validation contract
    │       └── HANDOFF.md             # Persistent memory & session worklog
    │
    └── vault/                         # Zero-token AST-generated Obsidian Vault
        ├── .obsidian/
        │   └── app.json               # Obsidian vault config (Wikilinks enabled)
        ├── INDEX.md                   # Master index categorized by clusters
        └── {file_path}.md             # Code note per file with bidirectional wikilinks
```

### Obsidian Notes with Custom Note Preservation
Each code file generates a corresponding note in the Vault containing:
- **YAML Frontmatter**: `type: code_node`, `cluster`, `file_path`, `degree`, `dependencies`, `symbols`.
- **Bidirectional Wikilinks**: Links like `[[Entities/Player.cs]]` navigable both in Cockpit and Obsidian.
- **Protected Notes Block**:
  ```markdown
  <!-- COCKPIT_NOTES_START -->
  ### Architecture Notes
  - Passive capacitor was added here to prime the devastating first shot.
  <!-- COCKPIT_NOTES_END -->
  ```
  Any manual developer annotations or agent notes written inside this block are **strictly preserved** across repeated AST graph synchronizations!

---

## 🛠️ MCP Server Tools (JSON-RPC 2.0)

The stdio MCP server exposes 14 specialized tools for AI orchestrators:

| Tool | Description |
| :--- | :--- |
| `sync_blueprint` | Initializes the active epic and vertical slices, creating `blueprint.lock.json` in `./cockpit-agent/blueprints/`. |
| `update_agent_pulse` | Sends real-time telemetry for 3x3 pairs and moves cards across the visual Kanban pipeline. |
| `log_critique_verdict` | Records approvals or detailed rejections into the Gauntlet Audit Log. |
| `fetch_user_steering` | Reads queued human instructions sent via the dashboard live chat. |
| `post_orchestrator_message` | Sends orchestrator status updates and replies back to the dashboard chat. |
| `get_cockpit_state` | Returns the full JSON snapshot of the current governance state. |
| `run_project_tests` | Executes the project test suite (`dotnet test`, `pytest`, `npm test`) and distills only failing assertions and stack traces (~95% token reduction). |
| `get_slice_failure_report` | Retrieves the distilled failure history for a specific vertical slice. |
| `analyze_codebase_graph` | Performs a static AST scan and returns the dependency graph with zero token expenditure. |
| `query_symbol_impact` | Computes the impact zone (blast radius) of any modified file or symbol. |
| `generate_handoff` | Writes the standardized `HANDOFF.md` to disk for session wrap-up or continuation. |
| `read_last_handoff` | Reads the most recent handoff to resume work in a new session with zero context drift. |
| `get_slice_spec` | Returns only the isolated specification of a single vertical slice (saving 80% tokens for subagents). |
| `check_human_gate` | Verifies whether the human operator has approved release or integration gates. |

---

## 🌐 REST API Endpoints & WebSockets

The FastAPI backend runs on port `8765` by default:

| Method | Endpoint | Parameters | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/state` | — | Full current state snapshot from the atomic store. |
| `GET` | `/api/metrics` | — | Productivity KPIs (tokens saved, approval rate, slice progress). |
| `GET` | `/api/graph` | `root` (optional) | Codebase dependency graph (nodes, edges, clusters, symbols). |
| `GET` | `/api/vault/note` | `file`, `root` | Fetches the Markdown note content for a file in the Vault. |
| `POST` | `/api/vault/note` | JSON: `{file, content, root}` | Saves updates to a Vault note while preserving user notes. |
| `POST` | `/api/vault/sync` | JSON: `{root}` | Triggers a fresh Vault resynchronization from the AST graph. |
| `GET` | `/api/handoff` | `root` (optional) | Reads the most recent `HANDOFF.md` from disk. |
| `POST` | `/api/project_root` | JSON: `{project_root}` | Updates the active project root directory dynamically at runtime. |
| `POST` | `/api/steering` | JSON: `{message}` | Queues a human steering instruction for the orchestrator. |
| `POST` | `/api/gates/approve` | JSON: `{gate_id}` | Manually approves a quality or integration gate. |
| `POST` | `/api/reset` | — | Resets the state machine back to initial idle status. |
| `GET` | `/api/health` | — | Health check returning `{"status": "healthy"}`. |
| `WS` | `/ws` | — | Bidirectional WebSocket feed delivering real-time state updates. |

---

## 🚀 Installation & Quick Start

### Prerequisites
- **Python 3.9+** installed ([python.org](https://python.org))
- A MCP-compatible AI client: **Google Antigravity** or **Claude Desktop**

### 1. One-Click Installation

**On Windows:**
```cmd
install.bat
```

**On macOS / Linux:**
```bash
chmod +x install.sh
./install.sh
```

The automated installer will:
1. Validate your Python environment and install dependencies (`fastapi`, `uvicorn`, `websockets`, `pydantic`).
2. Auto-configure the MCP server in your AI client's configuration file.
3. Install the bundled skills (`cockpit`, `spec-orchestrator`, `gauntlet-loop`).

### 2. Launching the Cockpit

**On Windows:**
```cmd
start_cockpit.bat
```

**Via Terminal (All Platforms):**
```bash
python run_cockpit.py
```

Open your browser at: **`http://localhost:8765`**.

---

## ⚙️ Manual MCP Configuration

If you prefer to configure MCP manually in your client's config file (`~/.gemini/config/mcp_config.json` or Claude Desktop's `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "agent-cockpit": {
      "command": "python",
      "args": [
        "C:/absolute/path/to/agent-cockpit/server/mcp_server.py"
      ]
    }
  }
}
```

---

## 💡 How to Use with Your AI Agent

With the dashboard running, start a prompt in your AI assistant:

```text
Activate the /cockpit skill and orchestrate this project using /spec-orchestrator
```

The orchestrator will run the complete development flight cycle:
1. Scans codebase AST via `analyze_codebase_graph` and creates `./cockpit-agent/vault/`.
2. Generates `MASTER_BLUEPRINT.md` and syncs it with `sync_blueprint`.
3. Dispatches the 3 concurrent pairs of the 3x3 Fleet, transmitting live telemetry via `update_agent_pulse`.
4. Runs automated tests via `run_project_tests` and registers adversarial review rounds via `log_critique_verdict`.
5. Emits the final `HANDOFF.md` via `generate_handoff` to guarantee flawless session resumption.

---

## 🧪 Automated Testing

To run the automated integration test suite:

```bash
python test_cockpit.py
```

Validates MCP JSON-RPC handshakes, state store atomicity, REST endpoints, and WebSocket channels.

---

## 📄 License

Distributed under the MIT License. See [LICENSE](LICENSE) for details.
