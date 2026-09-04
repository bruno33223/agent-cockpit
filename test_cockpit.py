import sys
import os
import json
import time
import subprocess
import urllib.request

def run_tests():
    print("=" * 60)
    print("INICIANDO TESTES DO AGENT COCKPIT (CORE & MCP)")
    print("=" * 60)

    # 1. Test StateStore
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "server"))
    from state_store import db

    print("[TEST 1] StateStore Inicial...")
    db.reset_state()
    s = db.get_state()
    assert len(s["nodes"]) == 3, "Deveria ter 3 nós iniciais"
    assert len(s["pairs_3x3"]) == 3, "Deveria ter 3 pares 3x3"
    print(" [OK] StateStore inicializado com sucesso.")

    # 2. Test MCP Server over stdio
    print("\n[TEST 2] MCP Server JSON-RPC stdio...")
    mcp_script = os.path.join(os.path.dirname(__file__), "server", "mcp_server.py")
    proc = subprocess.Popen(
        [sys.executable, mcp_script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    def send_rpc(req):
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        return json.loads(line)

    # Handshake
    init_res = send_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init_res["result"]["serverInfo"]["name"] == "agent-cockpit", "Nome inválido"
    print(" [OK] Handshake initialize OK")

    # List tools
    tools_res = send_rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tool_names = [t["name"] for t in tools_res["result"]["tools"]]
    assert "sync_blueprint" in tool_names, "sync_blueprint ausente"
    assert "update_agent_pulse" in tool_names, "update_agent_pulse ausente"
    assert "log_critique_verdict" in tool_names, "log_critique_verdict ausente"
    print(f" [OK] tools/list OK ({len(tool_names)} ferramentas registradas)")

    # Call sync_blueprint
    sync_res = send_rpc({
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "sync_blueprint",
            "arguments": {
                "epic_name": "Sistema de Teste de Cockpit",
                "goal": "Validar integração entre IA e UI offline.",
                "vertical_slices": [
                    {
                        "id": "slice-1",
                        "title": "Fatia 1: Banco e Modelos",
                        "acceptance_criteria": "- Schema validado\n- Migrations OK",
                        "spec_md": "### Spec Fatia 1\nCriar tabelas e contratos.",
                        "max_attempts": 5
                    },
                    {
                        "id": "slice-2",
                        "title": "Fatia 2: Lógica de Negócio",
                        "acceptance_criteria": "- Regras de validação",
                        "spec_md": "### Spec Fatia 2\nImplementar services.",
                        "max_attempts": 5
                    },
                    {
                        "id": "slice-3",
                        "title": "Fatia 3: Frontend e UI",
                        "acceptance_criteria": "- Telas responsivas",
                        "spec_md": "### Spec Fatia 3\nRenderizar dashboard.",
                        "max_attempts": 5
                    }
                ]
            }
        }
    })
    assert "sincronizado" in sync_res["result"]["content"][0]["text"], "Falha no sync_blueprint"
    print(" [OK] Tool call sync_blueprint OK")

    # Call update_agent_pulse
    pulse_res = send_rpc({
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "update_agent_pulse",
            "arguments": {
                "pair_id": 1,
                "builder_status": "WORKING",
                "critic_status": "IDLE",
                "slice_id": "slice-1",
                "attempt": 1,
                "details_md": "Builder 1 codificando modelos de dados..."
            }
        }
    })
    print(" [OK] Tool call update_agent_pulse OK")

    # Call log_critique_verdict
    critique_res = send_rpc({
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "log_critique_verdict",
            "arguments": {
                "slice_id": "slice-1",
                "attempt": 1,
                "verdict": "REJEITADO",
                "reason_md": "Faltou índice no campo user_id na migration."
            }
        }
    })
    assert "REJEITADO" in critique_res["result"]["content"][0]["text"]
    print(" [OK] Tool call log_critique_verdict (REJEITADO) OK")

    # Call post_orchestrator_message
    post_res = send_rpc({
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "post_orchestrator_message",
            "arguments": {
                "message": "Orquestrador ciente da rejeição da Fatia 1. Despachando Builder para refatoração."
            }
        }
    })
    print(" [OK] Tool call post_orchestrator_message OK")

    # Add user steering via StateStore directly (simulating UI click)
    db.add_user_steering("Orquestrador, dê atenção extra à performance dos índices.")

    # Fetch user steering via MCP
    fetch_res = send_rpc({
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "fetch_user_steering",
            "arguments": {}
        }
    })
    assert "performance" in fetch_res["result"]["content"][0]["text"]
    print(" [OK] Tool call fetch_user_steering (Human Steering) OK")

    # Call get_slice_spec
    slice_res = send_rpc({
        "jsonrpc": "2.0",
        "id": 8,
        "method": "tools/call",
        "params": {
            "name": "get_slice_spec",
            "arguments": {"slice_id": "slice-1"}
        }
    })
    slice_data = json.loads(slice_res["result"]["content"][0]["text"])
    assert slice_data["id"] == "slice-1"
    assert "Fatia 1: Banco e Modelos" in slice_data["title"]
    print(" [OK] Tool call get_slice_spec (Zero-Token Slicing) OK")

    # Call check_human_gate
    gate_res = send_rpc({
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/call",
        "params": {
            "name": "check_human_gate",
            "arguments": {"gate_name": "gate_ship_approved"}
        }
    })
    gate_data = json.loads(gate_res["result"]["content"][0]["text"])
    assert gate_data["gate"] == "gate_ship_approved"
    assert gate_data["approved"] is False
    print(" [OK] Tool call check_human_gate (Gate pendente) OK")

    # Call generate_handoff
    handoff_res = send_rpc({
        "jsonrpc": "2.0",
        "id": 10,
        "method": "tools/call",
        "params": {
            "name": "generate_handoff",
            "arguments": {
                "blueprint_dir": "test_handoff_dir",
                "epic_name": "Sistema de Teste de Cockpit",
                "summary": "Implementação e testes executados com sucesso.",
                "files_touched": ["Models.cs", "StateStore.py"],
                "tests_passed": True,
                "remaining_risks": ["Nenhum"],
                "next_steps": "Iniciar próximo épico."
            }
        }
    })
    handoff_data = json.loads(handoff_res["result"]["content"][0]["text"])
    assert handoff_data["status"] == "HANDOFF_CREATED"
    print(" [OK] Tool call generate_handoff (Handoff em disco) OK")

    # Call read_last_handoff
    read_handoff_res = send_rpc({
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {
            "name": "read_last_handoff",
            "arguments": {"base_dir": "."}
        }
    })
    read_data = json.loads(read_handoff_res["result"]["content"][0]["text"])
    assert "content" in read_data or "status" in read_data
    print(" [OK] Tool call read_last_handoff OK")

    # Clean up test handoff dir
    import shutil
    if os.path.exists("test_handoff_dir"):
        shutil.rmtree("test_handoff_dir")

    proc.terminate()

    # 3. Test HTTP Server
    print("\n[TEST 3] Servidor Web FastAPI...")
    import uvicorn
    import threading

    from web_server import app
    config = uvicorn.Config(app, host="127.0.0.1", port=8766, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(1.5)

    try:
        # Health check
        with urllib.request.urlopen("http://127.0.0.1:8766/api/health") as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "healthy", "Servidor não está healthy"
            print(" [OK] Endpoint /api/health OK")

        # State check
        with urllib.request.urlopen("http://127.0.0.1:8766/api/state") as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["epic"]["name"] == "Sistema de Teste de Cockpit"
            print(" [OK] Endpoint /api/state OK")

        # Gate approval check
        req = urllib.request.Request(
            "http://127.0.0.1:8766/api/gates/approve",
            data=json.dumps({"gate": "gate_ship_approved", "approved_by": "test_suite"}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "APPROVED"
            assert data["gate"] == "gate_ship_approved"
            print(" [OK] Endpoint POST /api/gates/approve OK")

        # Handoff endpoint check
        with urllib.request.urlopen("http://127.0.0.1:8766/api/handoff") as resp:
            data = json.loads(resp.read().decode("utf-8"))
            assert "content" in data or "status" in data
            print(" [OK] Endpoint GET /api/handoff OK")

        # Static index.html check
        with urllib.request.urlopen("http://127.0.0.1:8766/") as resp:
            html = resp.read().decode("utf-8")
            assert "AGENT COCKPIT" in html, "HTML não servido corretamente"
            print(" [OK] Static Web Dashboard (index.html) OK")

    finally:
        server.should_exit = True

    print("\n" + "=" * 60)
    print("TODOS OS TESTES FORAM CONCLUÍDOS COM SUCESSO! 100% OPERACIONAL.")
    print("=" * 60)

if __name__ == "__main__":
    run_tests()
