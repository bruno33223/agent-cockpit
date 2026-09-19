# Agent Cockpit — Diagnóstico Completo: Problemas, GAPs, Melhorias & Caminho para um Harness Completo

> **Data:** 16 de Setembro de 2026
> **Base verificada:** branch `feature/orca-redesign` + WIP não commitado (Integração Zeus Chat / Issue #24)
> **Escopo:** Todos os problemas do sistema atual, GAPs em relação aos principais agent harnesses do mercado (OpenAI Codex, Anthropic Claude Code, Google Antigravity), melhorias necessárias e os requisitos de "Definition of Done" para o Cockpit ser considerado um harness completo.
> **Fontes consolidadas:** `AUDITORIA_PROBLEMAS.md`, `GAPS_HARNESS_CODEX_CLAUDE_ANTIGRAVITY.md`, `RELATORIO_ESTADO_ATUAL_E_PROXIMOS_PASSOS.md`, inspeção direta do código e do estado em disco.

---

## 1. O que o sistema é hoje

O **Agent Cockpit** é, hoje, um **painel de telemetria, governança e orquestração visual para frotas de agentes de IA**, não um agente harness por si só. Ele é o "controlador de voo": acompanha, isola e audita agentes que rodam em clientes externos (OpenCode, Claude Desktop, Antigravity) via protocolo **MCP (stdio)** e um painel web em tempo real.

```
┌────────────────────────────────────────────────────────────────────┐
│              CLIENTES DE IA (externos)                             │
│      OpenCode CLI · Claude Desktop · Google Antigravity            │
│                 │                          │                      │
└─────────────────│──────────────────────────│──────────────────────┘
                  │ MCP stdio (JSON-RPC 2.0) │ WS/REST (127.0.0.1:8765)
                  ▼                          ▼
┌────────────────────────────────────────────────────────────────────┐
│                       AGENT COCKPIT SERVER                         │
│  ┌─────────────┐  ┌──────────────────────┐  ┌───────────────────┐  │
│  │ MCP Server  │  │  FastAPI + WebSockets │  │  Zeus Chat Engine │  │
│  │ (19 tools)  │  │  REST /api + /ws      │  │  (OpenCode hd)    │  │
│  └──────┬──────┘  └─────────┬────────────┘  │  + STT/áudio RAM   │  │
│         │                   │                                     │  │
│  ┌──────▼──────┐  ┌─────────▼────────────┐  ┌───────────────────┐  │
│  │ State Store │  │ Code Graph + Vault   │  │ Local Worker      │  │
│  │ (JSON atom) │  │ (AST/Obsidian)       │  │ Ollama + HF + Fila│  │
│  └─────────────┘  └──────────────────────┘  └───────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ PTY Manager · Git Worktrees · Gauntlet 3x3 · Test Runner     │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────┘
```

**Componentes-chave verificados (set/2026):**

| Componente | Arquivo | Status |
| --- | --- | --- |
| Web server FastAPI | `server/web_server.py` (~2595 linhas) | Funcional, crescendo acima do saudável |
| MCP stdio server | `server/mcp_server.py` | Funcional, loop single-thread |
| State Store atômico + lock | `server/state_store.py` (fcntl.flock + os.replace) | Corrigido, mas com acúmulo de lixo de testes |
| Code Graph + Vault Obsidian | `server/code_graph.py` | Funcional; scan é O(N) por chamada |
| Git Worktrees | `server/git_worktrees.py` | Funciona, mas com resolução de raiz incorreta |
| Local Worker (Ollama/HF/GPU) | `server/workers/*` | Funcional; fila FIFO agora com flock |
| Zeus Chat Engine | `server/zeus_chat_engine.py` | **WIP não commitado** (Issue #24) |
| OpenCode Headless | `server/opencode_manager.py` | Funcional; credencial com máscara pendente |
| Painel web (Vanilla JS) | `web/` | Funcional; muitos módulos globais |

**O que já foi resolvido nas rodadas recentes (#14–#24):**

- ✅ Path traversal do Vault corrigido (`code_graph.py:431-442` — `_validate_vault_file_path` com `realpath`+`commonpath`).
- ✅ CORS restrito a localhost com regex e lista fixa (`web_server.py:58-72`).
- ✅ Persistência atômica (`.tmp` + `os.replace`) e `fcntl.flock` cross-processo (`state_store.py:197-241`).
- ✅ PTY shutdown encerra todas as sessões com `stop_all()` (`web_server.py:397-403`, `pty_manager.py:456`).
- ✅ Kill de árvore de processos nos test runners (`test_runner.py:68,80,102`).
- ✅ Worktrees, chat visual integrado com subagentes, STT em RAM, multimodal, detecção de credenciais OpenCode, MCP manager, configurações por projeto.

A auditoria de 15/09 resolveu os problemas **críticos classificáveis como "segurança de superfície"**. Os problemas que restam são, em grande parte, **arquiteturais, de estado e de escopo de produto** — e é aí que mora a distância para os harnesses líderes.

---

## 2. Estado atual verificado — problemas ativos em disco (16/09/2026)

### 2.1 Projeto "default" sem raiz → "Projeto Sem Nome"
Verificado em `states/projects_index.json`: `current_project_id = "default"` com `project_root = null`, `name = "Projeto Sem Nome"`. Sem raiz, o explorer varre a HOME inteira, worktrees são criados em `/home/bruno/.worktrees` e o Épico não se liga a repositório algum. É o sintoma do split-brain de raiz que a auditoria apontou e que **persiste**:

- **Evidência no disco:** `/home/bruno/.worktrees/slice-{1,2,3}` existem; `/home/bruno/Projects/agent-cockpit/.worktrees/` está **vazio**. O trabalho dos builders foi gravado em `$HOME`, fora do repositório.

### 2.2 `projects_index.json` poluído por execução de testes
Verificado: **~200 entradas** como `canonical_bp_project-*`, `sample_repo-*`, `proj-builder-*`, `proj-settings-*`, todas apontando para `/tmp/cockpit_issue20_test_*/...`. Os testes da Issue #20 (persistência) **não limpam o índice** após a execução. Consequências: estado do dashboard poluído, `list_projects` inchado, e qualquer busca de projeto "principal" fica enterrada.

### 2.3 WIP não commitado e sem issue rastreada
`git status` mostra modificações em `zeus_chat_engine.py`, `opencode_manager.py`, `local_builder_tool.py`, `web_server.py`, `web/js/zeus_chat_*.js` e testes relacionados. A Issue #24 (Zeus Chat) está parcialmente integrada e **no working tree**, ainda sem commit — o histórico de `CHANGELOG.md` não reflete o estado real do código.

### 2.4 Conversa do chat visual não persiste
O chat visual do Zeus mantém mensagens em memória: **F5 perde a conversa**; a sessão do subagente continua viva no backend mas a UI hidrata do zero. Relatado no `RELATORIO` como melhoria da Fase 2, ainda pendente.

### 2.5 MCP ainda é o único "motor de execução" real
Ainda não existe um motor de agente nativo que: edite arquivos, rode comandos com permissões, faça checkpoints e rollback, e gere diffs dentro do próprio Cockpit de forma autônoma (sem depender de um cliente MCP externo). Todo o trabalho "real" continua dependente de OpenCode/Claude/Antigravity conectados via MCP.

---

## 3. Problemas detalhados por domínio

### 3.1 Segurança (situação: melhorou; ainda há furos)

| # | Severidade | Problema | Evidência | Recomendação |
|---|:---:|---|---|---|
| P1 | **Alta** | **API completa sem autenticação.** Qualquer processo local (ou remoto se `--host` for exposto) pode deletar projetos, resetar estado, ler arquivos arbitrários via `read_fs_file` e abrir shells via WS. CORS restrito ajuda, mas não é auth. | `web_server.py` endpoints REST/WS sem middleware de auth | Token de sessão + verificação de origem + proibição de `--host` não-loopsback |
| P2 | **Alta** | **Exposição de API key.** `detect_opencode_credentials` retorna a chave completa via `/api/opencode/credentials` e `/api/omniroute/config`; `sync_opencode_config` grava `apiKey` real em `opencode.json` (trackeado no git). | `server/opencode_manager.py:396-397`; `web_server.py:969-974` | Mascarar na API (padrão do `check_omniroute_health`) e gravar `apiKey` só em arquivo fora do repo com perms 0600 |
| P3 | **Alta** | **Path traversal residual em `slice_id`/terminal.** `slice_id` sem sanitização via query/body entra em `os.path.join(root_path, ".worktrees", target_slice)` → `chdir` fora do projeto. | `web_server.py:1001-1011,1078-1085`; `pty_manager.py:78` | Aplicar `_validate` tipo `realpath/commonpath` também nos worktrees/terminais |
| P4 | **Média** | **Shell=True + `test_command` arbitrário** no test runner (injeção de comando a partir do contexto do agente). | `server/test_runner.py:58-67` | Whitelist de runners; `shlex`; nunca `shell=True` com input do agente direto |
| P5 | **Média** | **XSS por atributo `data-model` e `node.id` em onclick inline** no frontend. | `web/js/local_worker.js:~342`; `web/js/slices_chat.js:230` | Sempre `escapeHtml`/`createElement`; nunca interpolar em atributo |
| P6 | **Média** | **Chave de API no DOM** (`<input type=password>` populado com a chave real). | `web/js/settings.js:334` | Nunca injetar segredo no DOM; só exibir mascarado e re-requisar no save |

### 3.2 Estado & persistência

| # | Severidade | Problema | Evidência | Recomendação |
|---|:---:|---|---|---|
| P7 | **Crítica** | **Split-brain de raiz:** MCP resolve raiz por CWD/`repo_root="."` enquanto o web resolve por `db.get_project_root`. Worktrees fantasmas em `$HOME/.worktrees`. | `mcp_server.py:418-426,625-680`; `web_server.py:1004-1011`; disco `/home/bruno/.worktrees` | Resolver raiz **sempre** via `project_id` no State Store; jamais por CWD do processo |
| P8 | **Alta** | **Testes que sujam o estado real:** issue #20 deixa ~200 projetos temporários no `projects_index.json`. | `states/projects_index.json` | Testes devem usar diretórios próprios e limpar; adicionar GC de projetos órfãos |
| P9 | **Alta** | **Ponte legado `sync_from_legacy_if_modified` continua ativa** e pode "hijackar" o projeto atual (default e real compartilham raiz). | `state_store.py:947`; `web_server.py:379` | Remover a ponte legado e o `file_watch_loop`; migrar definitivamente para o índice canônico |
| P10 | **Alta** | **Escrita não-atômica remanescente em `sessions.json`** (PTY) fora do lock multi-thread. | `pty_manager.py:211-233,283` | Mesmo padrão `.tmp`+`os.replace`+lock usado no state |
| P11 | **Média** | **Consumo global de steering** consome mensagens de todas as fatias; IDs `msg-{len+1}` colidem após prune. | `state_store.py:473-513` | Steering por `slice_id` + IDs únicos monotônicos |
| P12 | **Média** | **Fallback de raiz expõe o próprio cockpit** quando projeto não tem root. | `web_server.py:1337` (`_resolve_project_fs_root` → `base_cockpit_dir`) | Bloquear nulo em vez de cair no diretório do cockpit |

### 3.3 Concorrência & ciclo de vida de processos

| # | Severidade | Problema | Evidência | Recomendação |
|---|:---:|---|---|---|
| P13 | **Alta** | **MCP stdio monothread e síncrono:** `execute_local_builder` bloqueia até ~300s (acquire de worker + inferência); todas as demais tools/ping da sessão travam. | `server/tools/local_builder_tool.py:736,275`; `mcp_server.py:782-873` | Worker threads/async no loop stdio; resposta imediata de "job enfileirado" + progresso por notificação |
| P14 | **Média** | **Ollama sem respawn/watchdog** e `start()` reporta "started" sem confirmar porta. | `server/workers/ollama_process_manager.py:128-211` | Respawn com backoff + healthcheck de porta antes de `running=True` |
| P15 | **Média** | **`os.fork()` servidor multithread + reaping incompleto de zombies** no PTY (mitigado no shutdown, mas fechamento individual de sessão ainda arriscado). | `pty_manager.py:67,157-169` | Substituir fork por `pty.fork` com sessão própria e reap seguro |
| P16 | **Média** | **`enqueue` sem `notify_all`** na fila (thread B espera até timeout de 300s). | `server/workers/worker_queue.py:78-83` | `notify_all()` no enqueue |
| P17 | **Média** | **Broadcast sem backpressure** por cliente WS lento atrasa file-watch e streaming. | `web_server.py:114-111` (loop de `send_text`) | Timeout/sendqueue por cliente |
| P18 | **Baixa** | **Leak de subscription WS** em falhas não-`WebSocketDisconnect`. | `web_server.py:449-450` | `try/finally` no handler do WS |

### 3.4 Frontend & UX

| # | Severidade | Problema | Evidência | Recomendação |
|---|:---:|---|---|---|
| P19 | **Alta** | **32+ segundos de polling redundante + re-render total** convivendo com WebSocket (flicker/perda de input). | `web/js/slices_chat.js:939-953` | Remover polling; depender só do WS |
| P20 | **Alta** | **Logs de Ollama duplicados e DOM sem limite** (polling 3s + WS + append duplo + contagem `querySelectorAll` O(n)) | `web/js/local_worker.js:531-631` | Dedupe por UUID, buffer circular, single container |
| P21 | **Alta** | **Duplo POST no save do OmniRoute** (dois handlers no mesmo botão gravando `opencode.json`). | `web/js/settings.js:605-607` + `web/js/sidebar.js:509-536` | Um único handler; debounce; `apiFetch` |
| P22 | **Média** | **God-object global `window`** em `app.js` → contratos frágeis e inits fora de ordem. | `web/app.js:111-241` | Módulos ES com import/export direto |
| P23 | **Média** | **`getActiveProjectRoot()` duplicada** (grafo vs terminal), risco de raízes divergentes. | `codebase_graph.js:32` vs `terminal_workspace.js:601` | Single source (State Store) |
| P24 | **Média** | **Reconexão WS infinita sem backoff/jitter.** | `web/js/websocket_client.js:55,225` | Backoff exponencial com teto |
| P25 | **Média** | **Dois sistemas de config espelhados (legado × modal)** e botões de autostart que não existem no HTML (no-op garantido). | `web/index.html:982`; `sidebar.js:618-626` | Remover view legada; deletar listeners mortos |
| P26 | **Média** | **xterm.js via CDN síncrono no `<head>`** (render-blocking, sem SRI, sem fallback local). | `web/index.html:13-16` | Vendora local + `defer` + SRI |
| P27 | **Baixa** | Motivação: **persistência da conversa do chat (F5 perde tudo)**; acessibilidade (tabs/aria, focus trap); overflow de abas de frota 3x3; z-index inconsistente; código morto (`initTabsBarControls` stub, `debounce` duplicado). | `RELATORIO` seção 3; `terminal_workspace.js:1489-1492` | Fase de polimento UX |

### 3.5 Arquitetura & dívida técnica

| # | Severidade | Problema | Evidência | Recomendação |
|---|:---:|---|---|---|
| P28 | **Alta** | **Monólito superlotado:** `web_server.py` 2595 linhas (REST+WS+Ollama fallback+LLM fallback+broadcast+file-watch+PTY+explorer+vault); `state_store.py` 1221 linhas (persistência+negócio Gauntlet+prova-de-trabalho+breaker); singletons globais por import direto. | `web_server.py`; `state_store.py` | Quebrar em serviços (auth, projects, governance, executor, telemetry) com injeção |
| P29 | **Média** | **Scan de codebase O(N) por chamada** (`query_impact(".")` re-varre tudo a cada tool call; até 5 por contexto). | `code_graph.py:177-217`; `mcp_server.py:649-663` | Índice incremental persistente (JSON/SQLite + hashes mtime) |
| P30 | **Média** | **`base_branch="master"` fixo** na prova-de-trabalho → `main` gera falso `ZERO_COMMIT_DROPPED`. | `state_store.py:866,992` | Detectar branch default (git symbolic-ref) |
| P31 | **Média** | **`num_ctx=2048` + prompt com arquivos inteiros** → truncamento silencioso; e remoção de `//.*` quebra URLs/strings em JS. | `local_builder_tool.py:241-246,300-304` | Context window configurável + parser de comentário por linguagem |
| P32 | **Média** | **Exceções engolidas** em `file_watch_loop`, `_sync_legacy_file`, loop de leitura PTY, `prepare_task_context`. | `web_server.py:363-364`; `state_store.py:343-348`; `pty_manager.py:144-145` | Logging estruturado mínimo |
| P33 | **Baixa** | Deprecações (`@app.on_event` → lifespan), dispositivos de teste em prod (`hasattr(resp,"mock_calls")`), métrica `estimated_tokens_saved` fabricada, `_tickets` nunca podado. | `web_server.py:391-403`; `local_llm_client.py:95-107`; `state_store.py:557` | Limpeza técnica + honestidade de métricas |

### 3.6 Testes

- ✅ 348 testes verdes (`RELATORIO`), cobrindo fila FIFO, atomicidade do state, lifecycle do Ollama, endpoints REST/WS, markup de UI.
- ❌ **Não há teste de integração real MCP + Web com WebSocket completo** (cross-processo).
- ❌ Split-brain de raiz, `sync_from_legacy`, steering entre fatias/prune, evidência/handoff, apply_surgical_patch com whitespace, ciclo de vida PTY (órfãos/zombies), respawn do Ollama — **sem testes**.
- ❌ Testes da issue #20 **poluem o índice real** (P8) — falta isolamento/limpeza.

---

## 4. GAPs vs. OpenAI Codex, Claude Code e Google Antigravity

Matriz comparativa (o que um harness de mercado tem e o Cockpit ainda não, ou tem parcial):

| Pilar | Codex CLI | Claude Code | Antigravity | Cockpit (hoje) | Nota Cockpit |
| --- | :---: | :---: | :---: | :---: | --- |
| **Motor de agente nativo** (editar/testar no próprio harness) | Sim | Sim | Sim | **Não** — depende de cliente externo via MCP | O maior GAP estrutural |
| **Context Engine** (compactação, pruning, cache) | Alto | Excelente (prompt caching, read com offset/limit) | Estado da arte (AST graph + pruner) | **Básico** (histórico linear; AST só via scan O(N)) | `context_pruner` MCP existe mas é manual |
| **Isolamento de execução** (sandbox/permissão por comando) | Sandbox cloud | Permissão por comando | Worktrees + MCP | **Parcial** — worktree manual, PTY sem permission prompt | Sem sistema de aprovação de comandos |
| **Subagentes em paralelo reais** | Limitado | Background tasks | Frotas 3x3 reais | **Telemetria 3x3 sim; execução paralela não** | UI mostra, mas quem executa é o cliente externo |
| **Feedback loop automático** (testes+linter antes de "done") | Sim | Sim | Sim | **Gate existe** (evidência <180s) mas execução depende de tool do agente externo | Hellen: falta TDD loop autônomo |
| **Undo/checkpoint/rollback de mudanças** | Sim | Sim | Sim | **Não** — só worktree descartável manual | Recomendar por slice |
| **Sessões/checkpointing** (retomar sessão zerando drift) | Sim | Sim (resume) | Sim | **Parcial** — `HANDOFF.md` é manual | Chat visual nem persiste (P27) |
| **Leitura seletiva de arquivos** (offset/limit, símbolos) | Sim | Sim | Sim | **Parcial** — `read_fs_file` não tem token-budget | Dock: range/truncação por tool |
| **MCP nativo** | Parcial | Nativo | Nativo lazy-load | **É o protocolo base do projeto** | Frente forte |
| **Autenticação/isolamento multi-tenant** | Sim | Sim | Sim | **Não** | P1 |
| **UX: TUI/IDE integrada** | CLI | CLI | IDE fork | **Web rico (PTY+chat+grafo)** — vantagem | É a vantagem competitiva |
| **Custo/privacidade (offline, zero-token AST, STT RAM)** | Cloud | API | API | **Local-first total** — vantagem | É a vantagem competitiva |

### Diagnóstico de pilar (o detalhe)

1. **Context Engine (GAP 1):** o Cockpit produz AST e vault "zero-token" localmente — mas entrega o gráfico **por scan O(N)** a cada chamada e não gerencia o **orçamento de tokens** da conversa: não trunca outputs de tools >2000 tokens (salvando em scratch e dando ponteiro), não condensa histórico automaticamente ao atingir ~60% da janela e não detecta degeneração (loop de repetição) no streaming. Codex/Claude/Antigravity fazem isso nativamente.

2. **Execução isolada (GAP 2):** o `create_slice_worktree` existe, mas: (a) a raiz usada é CWD-dependente (gera os fantasmas de `$HOME/.worktrees`), (b) não há **prompt de aprovação por comando** (o humor do sandbox do Codex/Claude), e (c) não há política de merge automático pós-aprovação da banca.

3. **Multi-agente real (GAP 3):** o painel mostra a frota 3x3 e o Gauntlet, mas não há **orquestrador residente** que dispare builders/critics em paralelo dentro do próprio processo — a execução continua delegada ao cliente MCP externo, e a ordem "builder termina → critic valida" (critic foi invocada junto com builder antes) só funciona por convenção, não por barreira temporal real.

4. **Verificação/feedback (GAP 4):** o portão `verify_completion_evidence` (<180s, exit 0) é bom, porém: localiza `TEST_RAW.log` por CWD (divergente do `run_project_tests`), não roda linter/fmt automaticamente como parte do loop e não faz **rollback automático** quando a banca rejeita.

5. **Observabilidade/UX (GAP 5):** já é forte (PTY real, grafo, abas de subagentes, kill switches). Faltam métricas de GPU/tokens-seg, export do log do Gauntlet, pers-asistência do chat e acesso por teclado/a11y para nível ferramenta profissional.

6. **Governança de contexto cross-session:** Claude Code e Codex mantêm **checkpointing de sessão**; o Cockpit tem HANDOFF mas é manual e não é automático.

---

## 5. Melhorias recomendadas — fila de execução (priorizada)

### Onda 0 — Higiene imediata (1-2 dias)
1. **Nova issue + commit** do WIP do Zeus Chat (#24). `git status` está sujo.
2. **Resetar estado real:** definir `current_project_id` correto para `agent-cockpit-316ac845` (root `/home/bruno/Projects/agent-cockpit`) ou recriar o workspace; apagar `/home/bruno/.worktrees` fantasmas e os `states/*` de teste de `/tmp/...`.
3. **GC de projetos órfãos** no State Store (remover `project_root` inexistente ou `/tmp/cockpit_issue20_test_*`).

### Onda 1 — Segurança e correção de estado (P0/P1)
4. **Auth mínima + proibição de bind não-loopback** (`--host 127.0.0.1` obrigatório por default). **(P1)**
5. **Mascarar API keys** em todas as rotas; mover `apiKey` para fora do `opencode.json` trackeado. **(P2)**
6. **`_validate` de `slice_id`** em todos os endpoints de worktree/terminal. **(P3)**
7. **Unificar resolução de raiz por `project_id`** no MCP; eliminar `repo_root="."`/CWD. **(P7)**
8. **Remover ponte legado** (`sync_from_legacy_if_modified` + `file_watch_loop`) após migrar índice canônico. **(P9)**

### Onda 2 — Arrastão arquitetural (harness mínimo)
9. **Token-budget nos outputs de tools** (truncar >2000 tokens, salvar em scratch, devolver ponteiro) **(GAP 1)**
10. **Compactação automática de histórico** quando >60% da janela; detector de repetição n-gram no streaming. **(GAP 1 / P29)**
11. **Índice AST incremental** (mtime hashing) para tornar `query_impact` barato. **(P29)**
12. **Fila de worker observável cross-processo + MCP async** para não travar o stdio 300s. **(P13)**
13. **Aprovação de comandos** (allowlist por projeto: `pytest|dotnet test|npm test|git ...`) no test runner. **(P4)**

### Onda 3 — Funções de harness competitivas
14. **Motor de sessão/checkpoint:** snapshot do diff + estado por turno; retomar sessão do chat visual. **(P27 / GAP 5)**
15. **Autopause crítica: barreira real Builder→Critic** no orquestrador com disparo automático do critic após `BUILDER_FINISHED`. **(GAP 3)**
16. **Merge/rollback automático por slice** após veredito da banca. **(GAP 2/4)**
17. **Métricas GPU + tokens/s + export do Gauntlet** em PDF/MD. **(GAP 5)**

### Onda 4 — Polimento UX
18. Fallback de nome por basename da raiz; finder do HF Hub visível; a11y (tabs/aria/focus trap); overflow-x das abas da frota; dedupe/limite de logs; remover polling redundante; xterm local+SRI.

---

## 6. Definition of Done — o que significa "ser um harness completo"

### 🥉 Nível 1 — Harness funcional e confiável (meta imediata)
Requisitos de "eu usaria isso todos os dias":

- [x] Executa edições e testes a partir de um agente confiável (MCP) com **raiz correta** e evidência de testes fresca.
- [x] Estado não corrompe nem perde em crash (atomic + flock) — **concluído**.
- [ ] **Auth e isolamento de superfície** (nível de confiança para API local seguro).
- [ ] **Token-budget por tool** e truncamento de outputs grandes.
- [ ] **Histórico persistente de chat/sessão** (sem perder em F5) + checkpoint de conversa.
- [ ] **Loop de feedback automático**: testes → lint → veredito → **rollback ou merge** sem intervenção manual.

### 🥈 Nível 2 — Concorrência com Codex / Claude Code / Antigravity (meta 1-2 meses)
- [ ] **Context Engine próprio**: prune automático + resumo semântico + índice AST incremental (um "roca para Antigravity").
- [ ] **Isolamento real por slice**: worktree por task **com raiz correta**, monitorado, com diff view e merge aprovado.
- [ ] **Multi-agente com barreira temporal**: haras críticos só disparam após o builder terminar; painel mostra os 3 pares ao vivo.
- [ ] **Permissão por comando** (allow/deny/semelhante ao Claude Code) com veredito registrável.
- [ ] **Sessões retomáveis** (resume) com zero drift de contexto.
- [ ] **Testes de integração cross-processo** MCP+Web em CI.

### 🥇 Nível 3 — Diferenciação (onde o Cockpit já é/será único)
- [ ] **Orquestrador residente**: o próprio cockpit despacha builders/critics (sem depender de cliente externo), mantendo a telemetria como hoje.
- [ ] **STT em RAM + multimodal + local-first** (já tem) integrado ao fluxo de execução (falar → instrução → slice).
- [ ] **Vault/AST zero-token** como fonte de contexto oficial do agente (economizando tokens em qualquer modelo).
- [ ] **IDE web com PTY, chat e grafo** integrados (já tem visão) + a11y e métricas de GPU.

---

## 7. Roadmap resumido

| Fase | Período | Entrega | Critérios de saída |
|---|---|---|---|
| **0 — Higiene** | 1-2 dias | commit Zeus, reset de estado, GC | `git status` limpo; dashboard com 1 projeto real |
| **1 — Segurança/Estado** | 1 semana | P1-P9 resolvidos | sem chave no DOM/API; sem path traversal; raiz única |
| **2 — Harness mínimo** | 2-3 semanas | GAP1/2/4 + MCP async + fila observável | tools não travam >5s; outputs truncados; portões reais |
| **3 — Competitivo** | 1 mês | barreira builder→critic real, checkpoint/rollback, resume | frota 3x3 executa de ponta a ponta no próprio cockpit |
| **4 — Polimento** | contínuo | UX/a11y/metrics | auditoria de a11y passa; métricas de GPU no painel |

---

## 8. Referências

- `AUDITORIA_PROBLEMAS.md` — inventário técnico original (backend/frontend/lógica), 15/09.
- `GAPS_HARNESS_CODEX_CLAUDE_ANTIGRAVITY.md` — matriz de GAPs vs. market leaders.
- `RELATORIO_ESTADO_ATUAL_E_PROXIMOS_PASSOS.md` — validação em navegador e UX audit, 16/09.
- `CHANGELOG.md`, `README.md` (docs do produto), `opencode.json` (config corrente).
- Verificação direta: `states/projects_index.json`, `/home/bruno/.worktrees`, `git log/status`, `server/*`, `web/js/*`.