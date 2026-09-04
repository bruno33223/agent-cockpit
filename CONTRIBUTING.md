# Contributing to Agent Cockpit

Thank you for your interest in contributing! Agent Cockpit is an open ecosystem — PRs for new MCP tools, dashboard features, AI client integrations, and language support for the code graph analyzer are all welcome.

---

## Development Setup

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/agent-cockpit.git
cd agent-cockpit

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Start the dashboard in development mode
python run_cockpit.py
```

The dashboard will be live at `http://localhost:8765`.

---

## Areas to Contribute

| Area | Description |
| :--- | :--- |
| **New MCP Tools** | Add tools to `server/mcp_server.py` following the JSON-RPC 2.0 schema already in place. |
| **Code Graph Languages** | Extend `server/code_graph.py` to support new file extensions (e.g. `.go`, `.rs`, `.java`). |
| **Test Runner Backends** | Add new test framework parsers to `server/test_runner.py` (e.g. `cargo test`, `go test`, `jest --json`). |
| **Dashboard UI** | Improve `web/index.html`, `web/styles.css`, or `web/app.js`. No build step required — pure HTML5/CSS/JS. |
| **AI Client Integrations** | Update `setup_installer.py` to auto-detect new AI tools (e.g. Cursor, Windsurf, Copilot Workspace). |

---

## Pull Request Guidelines

1. **Fork** the repository and create your branch from `main`:
   ```bash
   git checkout -b feat/my-awesome-tool
   ```
2. **Keep changes focused**: one feature or fix per PR.
3. **Test your changes**: run `python test_cockpit.py` to validate the MCP server and web server.
4. **Update documentation**: if you add a new MCP tool, add it to the README tools table.
5. **Open a PR** against `main` with a clear title and description.

---

## Code Style

- Python: follow [PEP 8](https://peps.python.org/pep-0008/). No third-party linters required — just keep it readable.
- JavaScript: vanilla ES6+, no framework, no bundler. Keep `app.js` self-contained.
- No external CSS frameworks — the design system is handcrafted in `styles.css`.

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
