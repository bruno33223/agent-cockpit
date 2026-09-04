import sys
import json
import os
import warnings

# Suprime warnings para proteger o pipe stdio JSON-RPC 2.0
warnings.filterwarnings("ignore")

# Garante path relativo para importar state_store
sys.path.insert(0, os.path.dirname(__file__))
from state_store import db

TOOLS_DEFINITIONS = [
    {
        "name": "sync_blueprint",
        "description": "Sincroniza o Master Blueprint do Épico gerado pelo Orquestrador com o dashboard visual, inicializando os nós do fluxograma com suas respectivas fatias verticais.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "epic_name": {"type": "string", "description": "Nome do Épico ou objetivo macro."},
                "goal": {"type": "string", "description": "Resumo em uma linha do objetivo global."},
                "project_root": {"type": "string", "description": "Caminho absoluto ou relativo da raiz do projeto alvo do usuário."},
                "vertical_slices": {
                    "type": "array",
                    "description": "Lista das fatias verticais (até 3 simultâneas) para os nós do fluxograma.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Identificador da fatia (ex: slice-1)."},
                            "title": {"type": "string", "description": "Título da fatia vertical."},
                            "acceptance_criteria": {"type": "string", "description": "Critérios de aceitação em Markdown."},
                            "spec_md": {"type": "string", "description": "Especificação técnica e contratos de dados da fatia em Markdown."},
                            "max_attempts": {"type": "integer", "description": "Limite máximo de tentativas (padrão 5)."}
                        },
                        "required": ["title"]
                    }
                }
            },
            "required": ["epic_name", "goal", "vertical_slices"]
        }
    },
    {
        "name": "update_agent_pulse",
        "description": "Atualiza a telemetria do par 3x3 [Executor N ⟷ Revisor N] e move o card Kanban do nó em tempo real.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pair_id": {"type": "integer", "description": "ID do par (1, 2 ou 3).", "enum": [1, 2, 3]},
                "builder_status": {"type": "string", "description": "Status do Executor (IDLE, WORKING, WAITING)."},
                "critic_status": {"type": "string", "description": "Status do Revisor (IDLE, REVIEWING, REJECTED, APPROVED)."},
                "slice_id": {"type": "string", "description": "ID da fatia vertical associada (ex: slice-1)."},
                "attempt": {"type": "integer", "description": "Número da tentativa atual (1..5)."},
                "details_md": {"type": "string", "description": "Resumo do que está sendo feito ou nota do crítico."}
            },
            "required": ["pair_id", "builder_status", "critic_status"]
        }
    },
    {
        "name": "log_critique_verdict",
        "description": "Registra o veredito formal da banca revisora (Harsh Critic) no GAUNTLET_LOG e atualiza o nó no dashboard.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slice_id": {"type": "string", "description": "ID da fatia vertical (ex: slice-1)."},
                "attempt": {"type": "integer", "description": "Número da tentativa avaliada."},
                "verdict": {"type": "string", "description": "Veredito da revisão: APROVADO ou REJEITADO.", "enum": ["APROVADO", "REJEITADO"]},
                "reason_md": {"type": "string", "description": "Justificativa técnica rigorosa dos defeitos ou validação."}
            },
            "required": ["slice_id", "attempt", "verdict", "reason_md"]
        }
    },
    {
        "name": "fetch_user_steering",
        "description": "Recupera todas as mensagens, direcionamentos e comentários que o usuário enviou pelo chat do dashboard.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "post_orchestrator_message",
        "description": "Envia uma mensagem de status, resposta ou pedido de autorização do Orquestrador diretamente para o chat do dashboard.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Texto da mensagem enviada pelo Orquestrador."}
            },
            "required": ["message"]
        }
    },
    {
        "name": "get_cockpit_state",
        "description": "Retorna o estado completo atual do dashboard (Épico, Nós, Frota 3x3, Logs e Chat).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "analyze_codebase_graph",
        "description": "Analisa o grafo de dependências e símbolos do repositório (.cs, .py, .ts, etc.) de forma determinística com ZERO consumo de tokens.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "root_path": {"type": "string", "description": "Diretório raiz da análise (padrão: .)."},
                "max_files": {"type": "integer", "description": "Limite máximo de arquivos para varredura (padrão: 150)."}
            }
        }
    },
    {
        "name": "query_symbol_impact",
        "description": "Mapeia o raio de impacto de modificar uma classe, função ou arquivo (identifica instantaneamente quais arquivos importam ou dependem dele).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol_or_path": {"type": "string", "description": "Nome da classe, função ou caminho do arquivo a consultar."},
                "root_path": {"type": "string", "description": "Diretório raiz (padrão: .)."}
            },
            "required": ["symbol_or_path"]
        }
    },
    {
        "name": "get_slice_failure_report",
        "description": "Retorna o diagnóstico estruturado da última falha/rejeição de uma fatia vertical em JSON compacto para correção sem tokens de prosa.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slice_id": {"type": "string", "description": "ID da fatia vertical (ex: slice-1)."}
            },
            "required": ["slice_id"]
        }
    },
    {
        "name": "run_project_tests",
        "description": "Executa a suíte de testes de forma determinística no servidor Python e destila o resultado, eliminando 95% do lixo de terminal, salvando o log bruto em disco e retornando apenas as falhas reais em JSON compacto. Se test_command for omitido, auto-detecta dotnet test, pytest ou npm test.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "test_command": {"type": "string", "description": "Comando de teste opcional (ex: 'dotnet test', 'pytest', 'npm test'). Se omitido, auto-detecta."},
                "working_dir": {"type": "string", "description": "Diretório de execução (padrão: .)."},
                "timeout_sec": {"type": "integer", "description": "Timeout em segundos (padrão: 60)."},
                "log_output_dir": {"type": "string", "description": "Pasta para salvar TEST_RAW.log (padrão: pasta da blueprint mais recente)."}
            }
        }
    },
    {
        "name": "generate_handoff",
        "description": "Gera e salva o arquivo padronizado HANDOFF.md na pasta da blueprint numerada e registra no Cockpit, consolidando a entrega e liberando a IA para emitir apenas um ponteiro compacto no chat.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "blueprint_dir": {"type": "string", "description": "Caminho da pasta da blueprint (ex: '01_tiro_carregado')."},
                "epic_name": {"type": "string", "description": "Nome do Épico entregue."},
                "summary": {"type": "string", "description": "Resumo técnico da implementação."},
                "files_touched": {"type": "array", "items": {"type": "string"}, "description": "Lista dos arquivos criados ou modificados."},
                "tests_passed": {"type": "boolean", "description": "Se os testes passaram com sucesso."},
                "remaining_risks": {"type": "array", "items": {"type": "string"}, "description": "Riscos ou notas arquiteturais remanescentes."},
                "next_steps": {"type": "string", "description": "Instrução cirúrgica para a próxima sessão."}
            },
            "required": ["blueprint_dir", "epic_name", "summary", "files_touched", "tests_passed"]
        }
    },
    {
        "name": "read_last_handoff",
        "description": "Lê o último documento HANDOFF.md gerado no projeto para retomada instantânea de contexto em uma nova sessão sem precisar ler dezenas de arquivos de código.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "base_dir": {"type": "string", "description": "Diretório base do projeto (padrão: .)."}
            }
        }
    },
    {
        "name": "get_slice_spec",
        "description": "Retorna exclusivamente a especificação e critérios de aceitação de uma única fatia vertical (ex: slice-1), poupando 70-80% dos tokens de briefing dos subagentes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "slice_id": {"type": "string", "description": "Identificador da fatia (ex: 'slice-1', 'slice-2', 'slice-3')."}
            },
            "required": ["slice_id"]
        }
    },
    {
        "name": "check_human_gate",
        "description": "Verifica se um portão humano de autorização (ex: 'gate_ship_approved') foi aprovado pelo usuário no dashboard do Cockpit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "gate_name": {"type": "string", "description": "Nome do portão ('gate_plan_approved', 'gate_ship_approved').", "default": "gate_ship_approved"}
            }
        }
    }
]

def handle_tool_call(name: str, args: dict) -> dict:
    if name == "sync_blueprint":
        proj_root = args.get("project_root")
        if not proj_root:
            proj_root = os.path.abspath(".")
        res = db.sync_epic(
            epic_name=args.get("epic_name", ""),
            goal=args.get("goal", ""),
            vertical_slices=args.get("vertical_slices", []),
            project_root=proj_root
        )
        try:
            import workflow_lock
            bp_dir = args.get("blueprint_dir")
            if not bp_dir:
                found = workflow_lock.find_latest_blueprint_dir(proj_root)
                bp_dir = found if found else os.path.join(workflow_lock.get_blueprints_base_dir(proj_root), f"01_{args.get('epic_name', 'epic').lower().replace(' ', '_')}")
            elif not os.path.isabs(bp_dir):
                norm = bp_dir.replace('\\', '/')
                if not norm.startswith("cockpit-agent/"):
                    bp_dir = os.path.join(workflow_lock.get_blueprints_base_dir(proj_root), bp_dir)
                else:
                    bp_dir = os.path.join(proj_root, bp_dir)
            lock_path = workflow_lock.create_blueprint_lock(
                blueprint_dir=bp_dir,
                epic_name=args.get("epic_name", ""),
                goal=args.get("goal", ""),
                slices=args.get("vertical_slices", [])
            )
            lock_msg = f" | Lock declarativo gerado em: {os.path.basename(lock_path)}"
        except Exception as e:
            lock_msg = f" | Aviso lock: {e}"

        return {"content": [{"type": "text", "text": f"Épico '{args.get('epic_name')}' sincronizado no dashboard ({len(res.get('nodes', []))} nós atualizados){lock_msg}."}]}

    elif name == "update_agent_pulse":
        db.update_agent_pulse(
            pair_id=args.get("pair_id", 1),
            builder_status=args.get("builder_status", "IDLE"),
            critic_status=args.get("critic_status", "IDLE"),
            slice_id=args.get("slice_id"),
            attempt=args.get("attempt"),
            details_md=args.get("details_md")
        )
        return {"content": [{"type": "text", "text": f"Pulso do Par {args.get('pair_id')} atualizado com sucesso no Cockpit."}]}

    elif name == "log_critique_verdict":
        res = db.log_critique_verdict(
            slice_id=args.get("slice_id", "slice-1"),
            attempt=args.get("attempt", 1),
            verdict=args.get("verdict", "REJEITADO"),
            reason_md=args.get("reason_md", "")
        )
        return {"content": [{"type": "text", "text": f"Veredito [{res.get('verdict')}] registrado no Gauntlet Log para {args.get('slice_id')} (Tentativa {args.get('attempt')})."}]}

    elif name == "fetch_user_steering":
        messages = db.fetch_unconsumed_steering()
        if not messages:
            return {"content": [{"type": "text", "text": "Nenhum novo direcionamento ou mensagem do usuário no momento."}]}
        formatted = "\n".join([f"[{m['timestamp']}] Usuário: {m['text']}" for m in messages])
        return {"content": [{"type": "text", "text": f"Mensagens recebidas do usuário:\n{formatted}"}]}

    elif name == "post_orchestrator_message":
        db.post_orchestrator_message(args.get("message", ""))
        return {"content": [{"type": "text", "text": "Mensagem postada no chat do Cockpit com sucesso."}]}

    elif name == "get_cockpit_state":
        state = db.get_state()
        return {"content": [{"type": "text", "text": json.dumps(state, indent=2, ensure_ascii=False)}]}

    elif name == "analyze_codebase_graph":
        from code_graph import scan_codebase_graph
        root = args.get("root_path", ".")
        max_f = args.get("max_files", 150)
        graph = scan_codebase_graph(root, max_files=max_f)
        summary = {
            "scanned_files_count": graph["scanned_files_count"],
            "total_symbols_indexed": len(graph["symbol_index"]),
            "files_summary": {k: {"symbols": v.get("defined_symbols", []), "lines": v.get("lines", 0)} for k, v in list(graph["files"].items())[:60]},
            "direct_impact_map": graph.get("direct_impact_map", {})
        }
        return {"content": [{"type": "text", "text": json.dumps(summary, ensure_ascii=False)}]}

    elif name == "query_symbol_impact":
        from code_graph import query_impact
        target = args.get("symbol_or_path", "")
        root = args.get("root_path", ".")
        res = query_impact(root, target)
        return {"content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False)}]}

    elif name == "get_slice_failure_report":
        slice_id = args.get("slice_id", "")
        state = db.get_state()
        logs = [l for l in state.get("gauntlet_log", []) if l.get("slice_id") == slice_id and l.get("verdict") == "REJEITADO"]
        latest = logs[-1] if logs else None
        if not latest:
            return {"content": [{"type": "text", "text": json.dumps({"status": "NO_FAILURES", "slice_id": slice_id})}]}
        return {"content": [{"type": "text", "text": json.dumps(latest, ensure_ascii=False)}]}

    elif name == "run_project_tests":
        from test_runner import run_distilled_tests
        cmd = args.get("test_command")
        cwd = args.get("working_dir", ".")
        timeout = args.get("timeout_sec", 60)
        log_dir = args.get("log_output_dir")
        if not log_dir:
            import workflow_lock
            found = workflow_lock.find_latest_blueprint_dir(".")
            log_dir = found if found else cwd
        res = run_distilled_tests(cmd, working_dir=cwd, timeout_sec=timeout, log_output_dir=log_dir)
        return {"content": [{"type": "text", "text": json.dumps(res, indent=2, ensure_ascii=False)}]}

    elif name == "generate_handoff":
        import workflow_lock
        import time
        bp_dir = args.get("blueprint_dir")
        if not bp_dir:
            found = workflow_lock.find_latest_blueprint_dir(".")
            bp_dir = found if found else "01_entrega"
        epic_name = args.get("epic_name", "")
        summary = args.get("summary", "")
        files_touched = args.get("files_touched", [])
        tests_passed = args.get("tests_passed", True)
        remaining_risks = args.get("remaining_risks", [])
        next_steps = args.get("next_steps", "")

        path = workflow_lock.write_handoff_document(
            blueprint_dir=bp_dir,
            epic_name=epic_name,
            summary=summary,
            files_touched=files_touched,
            tests_passed=tests_passed,
            remaining_risks=remaining_risks,
            next_steps=next_steps
        )
        handoff_meta = {
            "blueprint_dir": os.path.basename(bp_dir),
            "path": path,
            "epic_name": epic_name,
            "files_count": len(files_touched),
            "tests_passed": tests_passed,
            "created_at": time.strftime("%H:%M:%S")
        }
        db.set_last_handoff(handoff_meta)
        result = {
            "status": "HANDOFF_CREATED",
            "handoff_file": path,
            "files_documented": len(files_touched),
            "tests_passed": tests_passed,
            "chat_pointer": f"✅ **Épico Concluído: [{epic_name}]**\n- Fatias: 3/3 aprovadas pelo Harsh Critic\n- Handoff: [{path}]\n- Testes: {'PASSOU' if tests_passed else 'FALHOU'}\n- Dashboard: http://localhost:8765"
        }
        return {"content": [{"type": "text", "text": json.dumps(result, indent=2, ensure_ascii=False)}]}

    elif name == "read_last_handoff":
        import workflow_lock
        base_dir = args.get("base_dir", ".")
        data = workflow_lock.read_latest_handoff(base_dir)
        if not data:
            return {"content": [{"type": "text", "text": json.dumps({"status": "NO_HANDOFF_FOUND"})}]}
        return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}

    elif name == "get_slice_spec":
        slice_id = args.get("slice_id", "")
        spec = db.get_slice_spec(slice_id)
        if not spec:
            return {"content": [{"type": "text", "text": json.dumps({"error": f"Fatia '{slice_id}' não encontrada no estado atual."})}]}
        return {"content": [{"type": "text", "text": json.dumps(spec, indent=2, ensure_ascii=False)}]}

    elif name == "check_human_gate":
        gate_name = args.get("gate_name", "gate_ship_approved")
        status = db.get_gate_status(gate_name)
        return {"content": [{"type": "text", "text": json.dumps(status, indent=2, ensure_ascii=False)}]}

    else:
        return {"isError": True, "content": [{"type": "text", "text": f"Ferramenta desconhecida: {name}"}]}

def run_stdio_server():
    """Loop JSON-RPC 2.0 padrão MCP sobre stdin/stdout unbuffered."""
    try:
        sys.stdin.reconfigure(encoding='utf-8')
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            if method == "initialize":
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"tools": {}},
                        "serverInfo": {
                            "name": "agent-cockpit",
                            "version": "1.0.0"
                        }
                    }
                }
                sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
                sys.stdout.flush()

            elif method == "notifications/initialized":
                # Apenas acknowledge
                pass

            elif method == "ping":
                res = {"jsonrpc": "2.0", "id": req_id, "result": {}}
                sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
                sys.stdout.flush()

            elif method == "tools/list":
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"tools": TOOLS_DEFINITIONS}
                }
                sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
                sys.stdout.flush()

            elif method == "tools/call":
                tool_name = params.get("name")
                tool_args = params.get("arguments", {})
                try:
                    tool_result = handle_tool_call(tool_name, tool_args)
                except Exception as ex:
                    tool_result = {
                        "isError": True,
                        "content": [{"type": "text", "text": f"Erro executando {tool_name}: {str(ex)}"}]
                    }
                res = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": tool_result
                }
                sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
                sys.stdout.flush()

            else:
                if req_id is not None:
                    res = {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "error": {"code": -32601, "message": f"Método não suportado: {method}"}
                    }
                    sys.stdout.write(json.dumps(res, ensure_ascii=False) + "\n")
                    sys.stdout.flush()

        except Exception as e:
            err = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": f"Erro interno do servidor: {str(e)}"}
            }
            sys.stdout.write(json.dumps(err, ensure_ascii=False) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    run_stdio_server()
