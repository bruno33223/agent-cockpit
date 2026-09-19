# RELATÓRIO TÉCNICO — agent-cockpit × omniroute: Redundâncias, Funções Quebradas e Estado da Orquestração

**Data:** 2026-09-19
**Autor:** Orquestrador Zeus (Staff Orchestrator)
**Escopo:** `/home/bruno/Projects/agent-cockpit`, `/home/bruno/cockpit-agent`, `~/.omniroute/`
**Fontes:** Leitura de código (`server/`, `web/`, `tests/`), documentos de auditoria existentes (`AUDITORIA_PROBLEMAS.md`, `DIAGNOSTICO_COMPLETO_HARNESS.md`, `GAPS_HARNESS_CODEX_CLAUDE_ANTIGRAVITY.md`, `RELATORIO_ESTADO_ATUAL_E_PROXIMOS_PASSOS.md`), runtime (processos, portas, logs, call logs do OmniRoute, git).

---

## 0. RESUMO EXECUTIVO

| Pergunta | Resposta |
|---|---|
| **O que o agent-cockpit faz que o omniroute já faz?** | Camada paralela de **credenciais de provedores + health-check + "routing" de modelo + gestão do Ollama** (`opencode_manager.py`, `zeus_chat_engine.py`, `workers/*`, modal de settings) que duplica a função nativa do OmniRoute (gateway com contas, auto-router, streaming e limites). |
| **Há função sem funcionar?** | Sim, **várias**: split-brain de estado, fila do local worker invisível/por-processo, ciclo de vida de PTY/MCP que deixa **6 processos `mcp_server.py` órfãos no host**, Ollama sem respawn, steering global roubando mensagens de fatias, portão de plano pré-aprovado, path traversal ativos. |
| **A orquestração funciona?** | **Não de ponta a ponta.** Não há motor de dispatch automático de Builders/Critics; as tools MCP só alimentam telemetria se chamadas manualmente, e o split-brain de estado (3.1) separa a execução dos subagentes da visualização — o dashboard mostra "projetos fantasma". |
| **Total de problemas mapeados** | **69 na auditoria anterior + 7 novas evidências de runtime/estrutura = 76**, resumidos nas seções 4 e 5. |

---

## 1. CONTEXTO: O QUE O OMNIREOUTE É HOJE

Tomando por base o runtime e a integração (`opencode.json`, `~/.omniroute/`, HANDOFF `14_settings_omniroute_opencode`):

- **Gateway/roteador local de LLM** (v16.3.1), escutando em `0.0.0.0:20128` com API OpenAI-compatível (`http://localhost:20128/v1`, key `omniroute-local`).
- Modelo **`omniroute/auto`**: roteador automático que decide provedor/rota por chamada (observado nos call logs: `decisions=11`, `ProviderLimitsSync`, `[USAGE] ANTIGRAVITY | in=17804 | out=151 | account=...`, streaming SSE com fallbacks).
- **Gerencia contas/credenciais criptografadas** em `storage.sqlite` (~2,4 MB) com `STORAGE_ENCRYPTION_KEY` em `~/.omniroute/.env`.
- Conectores monitorados: **OpenAI, Anthropic, Google/Gemini, Groq, DeepSeek, Mistral, OpenRouter, Together, Ollama, General/Local**, com latência e status dinâmico.
- Mantém `call_logs/` (json por chamada), `logs/application/app.log` e limites por provedor (`ProviderLimitsSync`).
- O próprio opencode já consome o OmniRoute como provider (`model: omniroute/auto`) — ou seja, o agente ORQUESTRADOR em si já roda 100% por cima do OmniRoute.

---

## 2. REDUNDÂNCIA: O QUE O agent-cockpit FAZ QUE O omniroute JÁ FAZ

### 2.1 Mapa de sobreposição

| Função | OmniRoute (nativo) | agent-cockpit (reimplementa) | Veredito |
|---|---|---|---|
| Endereço/gateway LLM | `http://localhost:20128/v1` é o único provider | `opencode_manager.py` mantém `omniroute_config.json` + grava `opencode.json`; `zeus_chat_engine.py` conecta **diretamente** em OmniRoute **ou** Ollama **ou** fallback local | Redeundante como **mini-router paralelo** |
| Credenciais/acounts | Cofre criptografado (`storage.sqlite`) | `detect_opencode_credentials()` lê `~/.config/opencode` e expõe `api_key` **sem máscara** na API (`GET /api/opencode/credentials`, `web_server.py:969-974`); chave replicada em `<input>` no DOM | **Redundante e mais inseguro** |
| Auto-routing de modelos | `omniroute/auto` com decisões por chamada | `local_builder_tool.py` escolhe modelo local/remoto, `num_ctx`, fila; `zeus_chat_engine` decide visão/modelo | **Redundante (duas camadas de roteamento)** |
| Health/latência de provedores | Status dinâmico + limites (`ProviderLimitsSync`) | `check_omniroute_health`, polling de conectores na UI (settings) | **Redundante** |
| Gestão do Ollama | Conector Ollama nativo | `ollama_process_manager.py` (start/stop/porta 11434/`pull`) + `hf_hub_client.py` + patch URL | **Redundante (mesma instância gerenciada 2×)** |
| Streaming chat | SSE nativo (`module: sse`, `[STREAM]`) | `zeus_chat_engine.py` (1196 linhas: streaming, STT, multimodal, fallback chain) | **Redundante como chat próprio** |
| Config do opencode | — | `sync_opencode_config` reescreve `opencode.json` (trackeado no git) | Duplicação de fonte de verdade da integração |

### 2.2 Consequência prática

- **Duas fontes de verdade de credencial**: o cofre do OmniRoute e o estado do cockpit (arquivo + DOM). Corrigir em um não corrige no outro, e o vazamento da chave via git (`opencode.json` commitado — `git ls-files` confirmou) e via API/DOM amplia a superfície de exposição (auditoria 1.5, 2.5).
- **Duas camadas de roteamento**: uma chamada pode passar pelo "auto" do OmniRoute e ainda ser re-roteada pelo fallback do cockpit (OmniRoute → Ollama → local). Feedback/escala e custo ficam opacos.
- **Dois gestores do mesmo Ollama**: processo duplicado se `auto_start_ollama_task` e `POST /api/local-worker/start-server` concorrerem (auditoria 1.8).

> **Recomendação estrutural:** o cockpit deve tratar o OmniRoute como **o** gateway (um único provider), retirando toda a lógica de credencial/health/routing espelhada (`opencode_manager` reduz-se a escrever `opencode.json`), e manter no `workers/` apenas orquestração de execução (fila, patch, evidência) — não invocação de LLM concorrente.

---

## 3. FUNÇÕES DO COCKPIT QUE NÃO FUNCIONAM (com evidência)

### 3.1 Evidência de runtime observada hoje

1. **6 processos `mcp_server.py` órfãos no host** (PIDs 19525, 21266, 23161, 24240 desde 14/set; 1850158 desde 16/set; 3338719 desde 18/set), todos vivos e sem dono. **Prova viva do ciclo de vida quebrado**: cada sessão de agente (Antigravity/opencode/Zeus) que abre o MCP e morre deixa um processo para trás. Não há `atexit`/close/`SIGTERM` confiável no `mcp_server.py`.
2. **`run_cockpit.py` (web) na porta 8765 (loopback)** e **OmniRoute em `0.0.0.0:20128`** — o gateway é acessível em todas as interfaces sem autenticação (falha 1.6/3.19 se estendida ao gateway).
3. **Artifacts de governança criados fora do repositório**: `~/cockpit-agent/blueprints/` contém os HANDOFFs/locks das issues reais (02..22) e `~/cockpit-agent/vault/INDEX.md` mapeia `Android/` (SDK) e `~/Documentos` — o `project_root` aponta para `$HOME`, não para o repo. Corrobora a falha 3.4.
4. **`opencode.json` (com provider omniroute) está trackeado no git** — `git ls-files` confirma; chave real cairia no histórico (falha 1.5).
5. **State-store pululado de `.lock`** (`states/*.lock` por projeto) coexiste com escrita não-atômica (`open('w')`) — os locks existem mas, segundo a auditoria 1.3/3.6, não impedem lost-update entre os processos web e MCP (locks por-processo, não cross-processo).

### 3.2 Funções quebradas (consolidadas da auditoria vigente + runtime)

| # | Função | Problema | Onde |
|---|---|---|---|
| F1 | Vault Notes API | **Path traversal** — leitura/sobrescrita de qualquer `.md` | `code_graph.py:431-474`, `web_server.py:584-600` |
| F2 | Git Worktrees MCP | **Path traversal** — deleção recursiva arbitrária via `slice_id` | `git_worktrees.py:57,99,147,169` |
| F3 | Estado compartilhado | Split-brain: fatias viram "projetos fantasma" (`slice-N-*.json`); épico real nunca recebe progresso | `states/`, `mcp_server.py`, `web_server.py` |
| F4 | Project root | Aponta para `$HOME` (`/home/bruno`); worktrees caem em `$HOME/.worktrees/` | `states/bruno-34ae8374.json:139` |
| F5 | Fila do Local Worker | Por-processo, invisível no dashboard, stdio monothread bloqueia 300s+, starvation de tickets | `worker_queue.py`, `local_builder_tool.py:736` |
| F6 | Ciclo de vida MCP/PTY | Orfãos de sessão (ver 3.1), shells bifurcados no boot, shutdown não encerra nada, zombies | `pty_manager.py:157-169,205`, `web_server.py:373-384` |
| F7 | Ollama | Sem respawn; `start()` reporta "started" sem conferir porta; zombie em restart | `ollama_process_manager.py:128-180` |
| F8 | Steering | Consumo global rouba mensagens de outras fatias; IDs `msg-N` colidem pós-prune | `state_store.py:473-513,681-729` |
| F9 | Veredito crítico | `APPROVED` vira `REJEITADO` (normalização `"APROV"`); enums divergem | `state_store.py:414-423,450,465` |
| F10 | Gate do plano | Pré-aprovado sempre — **governança humana inexistente** | `workflow_lock.py:40-43` |
| F11 | Proof of work | `base_branch="master"` fixo penaliza repos `main` | `state_store.py:866,992` |
| F12 | Settings OmniRoute UI | **Duplo POST por clique** na mesma chave; 2 sistemas espelhados; autostart no-op | `settings.js:600-607`, `sidebar.js:509-536` |
| F13 | Ollama logs UI | Duplicação (WS + polling) e DOM sem limite (memory leak) | `local_worker.js:531,547-631` |
| F14 | Re-render | Polling 2s + WS fazem re-render duplicado; nunca limpo | `slices_chat.js:939-953` |
| F15 | Evidência/handoff | `verify_completion_evidence`/`generate_handoff` dependem do CWD do MCP — portão pode nunca achar `TEST_RAW.log` | `mcp_server.py:547-586,682-727` |
| F16 | Injeção de patch | `apply_surgical_patch` usa índice do conteúdo limpo sobre o original → corrompe arquivo com whitespace | `local_builder_tool.py:114-124` |
| F17 | Autenticação/CORS | API inteira sem auth; `CORS *` + credentials; `--host` não-loopback expõe tudo | `web_server.py:46-52` |
| F18 | XSS front | `node.id` injetado em `onclick` inline sem escape | `slices_chat.js:230` |

> Nota: 69 achados detalhados já estão formalizados em `AUDITORIA_PROBLEMAS.md` (seções 1–3) e `DIAGNOSTICO_COMPLETO_HARNESS.md`; **nada indica que tenham sido corrigidos** (as evidências de runtime desta seção confirmam os achados estruturais).

---

## 4. A ORQUESTRAÇÃO FUNCIONA? — ANÁLISE PONTA A PONTA

### 4.1 Fluxo previsto (README) vs. fluxo real

**Previsto** (README): Zeus decompoe épico → `sync_blueprint` cria `MASTER_BLUEPRINT` + `blueprint.lock.json` → despacha 3×3 pairs (Executor+Reviewer) em worktrees → subagentes rodam `run_project_tests`/`local_builder` → `log_critique_verdict` registra gauntlet → gates humanos → `generate_handoff`.

**Real (o que os artefatos mostram):**

1. **Não há motor de dispatch.** Não existe scheduler/runner que dispare Builders/Critics. O "despacho" é manual: cada agente faz chamadas MCP avulsas. As skills `dispatching-parallel-agents`, `spec-orchestrator`, `gauntlet-loop` são **prompts/instruções**, não executores.
2. **A telemetria não chega ao épico.** Como F3, `create_slice_worktree`/`prepare_task_context`/`run_project_tests` resolvem raiz por caminho/worktree (`repo_root="."`, `query_impact(".")`) enquanto o estado resolve por `project_id` (`db.get_project_root`) → o progresso gravado em `states/slice-*.json` (fantasma) **nunca** sobe ao nó do épico (`bruno-34ae8374` fica `BACKLOG/PENDING`). O dashboard não reflete o trabalho.
3. **O "paralelismo" dos 3 pares é nominal.** O stdio do MCP é single-thread síncrono (implementação do loop JSON-RPC), e `execute_local_builder` segura o servidor por até 300s+; 3 fatias "paralelas" = ~900s de bloqueio encadeado (F5). Subagentes paralelos se atropelam.
4. **Governança é simbólica.** F10 (gate de plano pré-aprovado) + F9 (veredito normalizado errado) + verificação de evidência dependente de CWD (F15) → os gates aprovam/rejeitam com base em dados que podem nem ser os da fatia executada.
5. **O steering humano é um beehive.** F8: qualquer mensagem do chat é consumida globalmente; fatia errada pode agir sobre instrução alheia.
6. **Cada sessão vaza um processo** (F6 → 6 órfãos observados). "Orquestração" acumula lixo no sistema que a hospeda.

### 4.2 Veredito

> **A orquestração NÃO funciona de ponta a ponta.** Funciona apenas a fatia de **telemetria/visualização** (dashboard, MCP tools chamadas manualmente), e mesmo essa é corrompida pelo split-brain de estado. O que falta é um **motor de orquestração real** (agendar fatias, instanciar Builders/Critics, coletar outputs, aplicar gates, escrever handoff no local certo) — hoje é convenção de papel sobre tools avulsas. Arch :: esse é o maior vendor do projeto: o cockpit se vende como "orquestrador", mas opera como **painel + SDK MCP**.

---

## 5. INVENTÁRIO COMPLETO DE PROBLEMAS (CONSOLIDADO)

> Compatibilidade de nomenclatura com `AUDITORIA_PROBLEMAS.md`. Soma-se às 69 existentes sete novas observações (N1–N7).

### 5.1 Backend

**CRÍTICO**
- 1.1 Path traversal em Vault Notes (`code_graph.py:431-474`, `web_server.py:584-600`)
- 1.2 Path traversal em Git Worktrees (`git_worktrees.py:57,99,147,169`)
- 1.3 Persistência sem lock entre processos (`state_store.py:331-347`)
- N1 **6 processos MCP órfãos** (sem cleanup de sessão)
- N2 `opencode.json` trackeado no git (chave sujeita a commit)

**ALTO**
- 1.4 `shell=True` + órfãos no test runner (`test_runner.py:58-83`)
- 1.5 API key sem máscara exposta (`opencode_manager.py:396-397`, `web_server.py:969-974`)
- 1.6 API sem autenticação + CORS `*`+credentials
- N3 state-store: `.lock` presente mas escrita não-atômica persiste

**MÉDIO**
- 1.7 `os.fork()` em servidor multithread + zombies (`pty_manager.py:67,157-169`)
- 1.8 Race do Ollama sem lock (`ollama_process_manager.py:128-211`)
- 1.9 `enqueue` não acorda waiters (`worker_queue.py:78-83`)
- 1.10 MCP stdio bloqueia ~7min (`local_builder_tool.py:736,275`)
- 1.11 Rescans O(N) por tool call (`code_graph.py:177-217`)
- 1.12 Path traversal na shell de terminal (`web_server.py:1001-1011,1078-1085`)
- 1.13 `sessions.json` multi-thread sem lock (`pty_manager.py:211-372`)
- 1.14 `handle_port_conflict` reporta "livre" por engano (`run_cockpit.py:84-86`)
- 1.15 Estado fora do lock e config não persistida (`state_store.py:959-964,1045-1065`)

**BAIXO**
- 1.16 Exceções engolidas (4 pontos)
- 1.17 `except (RuntimeError, Exception)` redundante
- 1.18 IDs `msg-N` colidem pós-prune
- 1.19 Broadcast bloqueia por cliente lento
- 1.20 Subscription leak no WS
- 1.21 Mock do pytest vazado p/ produção (`local_llm_client.py:95-107`)
- 1.22 `@app.on_event` depreciado
- 1.23 Fallback de raiz expõe o próprio cockpit
- 1.24 Autostart sem quotes (paths com espaço quebram)
- 1.25 `switch_project`/`sync` com CWD divergente
- 1.26 Monólito: `web_server.py` 1371 linhas + `state_store.py` 1221 linhas misturando responsabilidades
- 1.27 Escrita por chunk de logs de terminal

### 5.2 Frontend

**CRÍTICO** — 2.1 XSS via `node.id` em `onclick` inline (`slices_chat.js:230`)

**ALTO** — 2.2 Duplo POST no settings OmniRoute; 2.3 Logs do Ollama duplicados + leak de DOM; 2.4 Polling 2s redundante com WS; 2.5 Chave de API no DOM

**MÉDIO** — 2.6 Dois sistemas de config espelhados (1 órfão); 2.7 God-object global (`app.js`); 2.8 `getActiveProjectRoot` duplicada/divergente; 2.9 Init inconsistente entre módulos; 2.10 Política de fontes duplicada; 2.11 Pipeline CSS com 2 fontes de verdade; 2.12 `data-model` sem escape; 2.13 Reconexão WS infinita sem backoff; 2.14 Autostart Antigravity no-op garantido; 2.15 xterm CDN render-blocking sem SRI/fallback

**BAIXO** — 2.16 Colisões de z-index; 2.17 Código morto/stubs; 2.18 Landing page duplicada e frágil; 2.19 Acessibilidade; 2.20 Heurísticas frágeis de porta/storage

### 5.3 Lógica de Funcionamento

**CRÍTICO**
- 3.1 Split-brain de estado (fatias fantasma) — **núcleo da quebra de orquestração**
- 3.2 Fila por-processo + stdio monothread + starvation
- 3.3 PTY/fork: órfãos no boot, shutdown inerte, zombies
- 3.4 `project_root = $HOME` (worktrees/tests/vault fora do repo)

**ALTO**
- 3.5 Ponte legado hijacka projeto atual (default ↔ bruno mutuamente sobrescrevem)
- 3.6 Multi-writer sem locks e escrita não-atômica
- 3.7 Evidência/handoff em locais CWD-dependentes
- 3.8 Ollama sem respawn e `start()` sem confirmar porta
- 3.9 `apply_surgical_patch` corrompe arquivo com trailing whitespace
- 3.10 `reset_state` destrói `project_root`
- 3.11 Steering global + IDs colidindo

**MÉDIO**
- 3.12 Veredito em inglês vira REJEITADO
- 3.13 Gate do plano pré-aprovado (sem governança real)
- 3.14 Proof of work com `master` fixo
- 3.15 `num_ctx=2048` + prompts gigantes (truncamento) e regex `//.*` que quebra URLs/strings
- 3.16 `manage_local_model(pull)` bloqueia 600s
- 3.17 Troca de projeto global em qualquer tab
- 3.18 `file_watch_loop` trata todo `*.json` como estado
- 3.19 CORS inválido

**BAIXO**
- 3.20 `handle_port_conflict` enganoso; 3.21 `_tickets` nunca podado; 3.22 `estimated_tokens_saved` fabricado
- N4 **Duplicidade de `cockpit-agent/`**: `~/cockpit-agent` (blueprints 02..22 + vault que mapeia `$HOME`) e `~/Projects/agent-cockpit/cockpit-agent` (vault do código) coexistem e divergem
- N5 **Dois mundos de invocação de LLM em paralelo**: envoy via OmniRoute (auto) vs. Local Worker direto ao Ollama — invisível ao gateway, metricas/uso divergentes
- N6 **Governança órfã do `$HOME`**: `blueprint.lock.json`/HANDOFFs de issues reais moram fora do repo → qualquer clone/CI não os enxerga
- N7 **Porta 20128 do OmniRoute em `0.0.0.0`** sem restrição de origem (combinada com 1.6, expõe o gateway em LAN)

---

## 6. COBERTURA DE TESTES (LACUNAS QUE PERMITEM AS QUEBRAS)

- Testado: `worker_queue` só no mesmo processo; `local_worker_api` valida dispatch via **mock**; `ollama_server_lifecycle` só WS do Ollama; `issue_6_terminal_pty` **consagra fork-no-boot**; suítes `test_issue_*` são asserções de markup.
- **Não testado:** `file_watch_loop`/`sync_from_legacy_if_modified`; `handle_port_conflict`; consumo de steering/prune; `verify_completion_evidence`/`generate_handoff` (CWD); `apply_surgical_patch` com whitespace; ciclo de vida PTY (órfãos/zombies/shutdown); respawn do Ollama; e **nenhum teste de integração real MCP+web+WS cross-processo** nem de "morte de cliente no meio da fila".
- Os `tests/test_omniroute_*` (direct_accounts, account_modal_e2e, native_config, gemini_38) confirmam que o cockpit **até testa a UI/credenciais do OmniRoute** — esforço que pertence ao próprio OmniRoute, reforçando a seção 2.

---

## 7. PRIORIZAÇÃO RECOMENDADA (PRÓXIMA ONDA)

1. **Segurança primeiro (bloqueante):** travas de path traversal (1.1, 1.2, 1.12), vazamento de key (1.5, 2.2, 2.5), XSS `node.id` (2.1), auth/CORS (1.6, 3.19) e restrição da porta 20128 (N7).
2. **Curar o split-brain (custo máximo de orquestração):** alinhar `project_root` aos repos reais, unificar resolução de raiz entre MCP/web (acabar com `repo_root="."` vs `db.get_project_root`), corrigir `sync_from_legacy_if_modified` e podar os `states/slice-*.json` fantasmas (3.1, 3.4, 3.5, N4, N6).
3. **Persistência:** escrita atômica (tempfile+rename) + lock cross-processo (1.3, 3.6, N3).
4. **Ciclo de vida:** cleanup do MCP no `atexit`/session close (N1 — matar os 6 órfãos), parar PTY no shutdown, reaping, respawn do Ollama com confirmação de porta (3.3, 3.8).
5. **Fila/concorrência:** fila compartilhada/observável, `notify_all` no enqueue, lock no Ollama, `run_project_tests` sem `shell=True` (3.2, 1.8, 1.9, 1.4).
6. **Redundância com OmniRoute:** remover credencial/health/routing espelhado; o cockpit passa a enxergar **um único provider** e foca em orquestração (seção 2).
7. **Decidir o motor de orquestração:** se o cockpit deve ser orquestrador de verdade, construir o runner (dispatch automático, coleta de outputs, gates, handoff) — caso contrário, reposicionar o README/docs como **painel de telemetria + SDK MCP**, e parar de prometer a frota 3×3.

---

*Documento gerado por Orquestrador Zeus em 2026-09-19. Base: inspeção de código, auditorias existentes e estado de runtime do host.*