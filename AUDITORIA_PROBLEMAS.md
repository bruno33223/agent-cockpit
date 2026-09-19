# Auditoria de Problemas Técnicos e de Arquitetura — agent-cockpit

**Data:** 2026-09-15
**Escopo:** Backend, Frontend e Lógica de Funcionamento
**Branch auditada:** `feature/orca-redesign`
**Diretório:** `/home/bruno/Projects/agent-cockpit`

---

# 1. PROBLEMAS IDENTIFICADOS (BACKEND)

## CRÍTICO

### 1.1 Path Traversal — leitura/escrita arbitrária de arquivos via Vault Notes
`server/code_graph.py:431-474` e `server/web_server.py:584-600`

Os endpoints `GET/POST /api/vault/note` aceitam `file` e `root` vindos da rede sem nenhuma validação (`normpath`/`commonpath`). `os.path.join(root_dir, "cockpit-agent", "vault", f"{file_path}.md")` com `file=../../../../home/user/documento.md` (ou absoluto) lê qualquer `.md` do sistema em `get_file_vault_note` e **sobrescreve qualquer arquivo `.md` arbitrário** com conteúdo controlado em `save_file_vault_note` (`code_graph.py:472-473`). Diferente de `read_fs_file`/`get_fs_tree`, estes endpoints não têm guarda alguma.

### 1.2 Path Traversal — deleção arbitrária de diretórios via Git Worktrees
`server/git_worktrees.py:57, 99, 147, 169` (chamado por `server/mcp_server.py:625-639`)

`slice_id` chega direto dos args MCP. `os.path.join(repo_root, ".worktrees", slice_id)` com `slice_id` absoluto (`/home/...`) ou `..` escapa da raiz; na criação `shutil.rmtree(worktree_dir)` (linha 99) e na limpeza `git worktree remove --force` + `shutil.rmtree` (linhas 154/169) podem **deletar recursivamente diretórios arbitrários** do disco. Nenhum `resolve`/`commonpath` é aplicado a `slice_id`.

### 1.3 Persistência sem lock entre processos — perda de estado/corrupção
`server/state_store.py:331-347, 220-222, 343-348` e `server/mcp_server.py:16`

`db = StateStore()` é instanciado **separadamente** no processo `web_server` (uvicorn) e no processo `mcp_server` (stdio). Ambos gravam os mesmos arquivos `states/*.json`/`projects_index.json`/`workflow_state.json` sem locking entre processos. As escritas não são atômicas (`open('w')` trunca + escreve), então updates concorrentes (ex.: `update_agent_pulse` via MCP + `add_user_steering` via WebSocket) geram *lost updates*; uma falha no meio do dump corrompe o JSON e `get_state` (`state_store.py:317-321`) devolve estado default, mascarando dados. O próprio `file_watch_loop` (`web_server.py:321-365`) existe como workaround reativo do problema.

## ALTO

### 1.4 Execução de comando arbitrário + processo órfão no test runner
`server/test_runner.py:58-67, 70-83`

`test_command` e `working_dir` vêm de args MCP (`run_project_tests`) e são executados com `shell=True` — injeção de comando possível a partir do contexto do agente. No timeout (Linux), chama-se apenas `proc.kill()` (partindo a shell raiz) sem matar a árvore de processos (`start_new_session` ausente) — testes filhos continuam rodando como órfãos após o retorno do tool.

### 1.5 Segredo de API key vazado por várias vias
- `server/opencode_manager.py:396-397`: `sync_opencode_config` grava `apiKey` real (detectada de `~/.config/opencode`) no arquivo `opencode.json` **trackeado pelo git**. Uma chave real detectada seria commitada no repositório.
- `server/web_server.py:969-974` → `opencode_manager.detect_opencode_credentials()` retorna `api_key` **completa, sem máscara** — ao contrário de `check_omniroute_health` (`opencode_manager.py:261-268`) que mascara. `GET /api/omniroute/config` e `GET /api/opencode/credentials` expõem a chave a qualquer caller local.

### 1.6 Zero autenticação em toda a API + CORS "*" com credentials
`server/web_server.py:46-52`

CORS `allow_origins=["*"]` + `allow_credentials=True` (combinação inválida/arcaica) e nenhum endpoint se autentica. Com o `--host` não-loopback, qualquer origem/processo pode: deletar projetos (`DELETE /api/projects/{id}`, `web_server.py:479-482`), resetar estado (`POST /api/reset`), gravar configurações, ler arquivos absolutos via `read_fs_file` (`web_server.py:1272-1289` permite raízes de **qualquer** projeto cadastrado + a raiz do próprio cockpit, o que inclui `states/*.json`), e abrir shells via WS de terminal.

## MÉDIO

### 1.7 `os.fork()` em servidor multithreaded + reaping incompleto de zombies
`server/pty_manager.py:67, 157-169`

`fork()` dentro do processo uvicorn (que já tem threadpool/threads de logging) é arriscado (locks/mutexes herdados); e `close()` faz `os.kill(SIGTERM)` + `waitpid(WNOHANG)` único — se o filho ainda rodar, `waitpid` retorna `(0,0)` e a sessão fica **não reaped**: ao sair depois, vira zombie até o servidor encerrar. Acúmulo sob uso prolongado.

### 1.8 Race no ciclo de vida do Ollama sem lock
`server/workers/ollama_process_manager.py:128-180, 182-211`

`start()`/`stop()` não usam `self._lock`; `self.process = Popen` (linha 162) pode ser disparado duas vezes se `auto_start_ollama_task` (`web_server.py:313-314` via executor) concorrer com `POST /api/local-worker/start-server` (`web_server.py:780-793`) → subprocessos duplicados do Ollama.

### 1.9 `enqueue` não acorda waiters da fila
`server/workers/worker_queue.py:78-83`

`enqueue` faz `append` sem `notify_all()` na `Condition`. Se uma thread B aguarda em `acquire_worker` por um ticket ainda não enfileirado, só acorda por um `notify` alheio (`release_worker`); com uma única tarefa concorrente pendente, B só sai no timeout (300s), marcando "timeout" indevidamente.

### 1.10 MCP stdio bloqueante: `execute_local_builder` congela o servidor
`server/tools/local_builder_tool.py:736, 275` + `server/mcp_server.py:782-873`

O loop stdio é single-thread e síncrono. `acquire_worker(timeout=300)` + inferência síncrona `urlopen(timeout=120)` (`local_builder_tool.py:275`) podem manter o servidor MCP travado por até ~7min, impossibilitando responder a qualquer outra tool/ping/notification do agente no período.

### 1.11 Rescans do codebase por chamada (custo O(N) repetido)
`server/code_graph.py:177-217` + `server/mcp_server.py:649-663`

`prepare_task_context` chama `query_impact(".")` para até 5 símbolos; cada chamada re-varre todo o repositório (`scan_codebase_graph` + leitura integral de cada arquivo). Multiplicado por tentativas/fatias, torna tool calls pesadas e lentas. `analyze_codebase_graph` (`mcp_server.py:495-506`) permite `root_path` arbitrário do agente (varredura de disco).

### 1.12 Diretório da shell de terminal controlável por path traversal
`server/web_server.py:1001-1011, 1078-1085`

`slice_id` (query/body, sem sanitização) entra em `os.path.join(root_path, ".worktrees", target_slice)`; um `slice_id` tipo `../outra/maquina` seleciona `cwd` fora do projeto e o `PTYSession` faz `chdir` nele (`pty_manager.py:78`). Combinado com 1.6, dá shell em diretório arbitrário.

### 1.13 `sessions.json` escrito de múltiplas threads sem lock
`server/pty_manager.py:211-233, 287-325, 345-372`

`_save_index()` é chamado de `get_or_create`, `close_session`, `list_sessions` — executados no event loop (ws) e na threadpool HTTP (endpoints sync) concorrentemente, sem lock → risco de corrupção/perda no `states/terminals/sessions.json`.

### 1.14 `handle_port_conflict` retorna "livre" quando não consegue listar PIDs
`run_cockpit.py:84-86`

Se a porta está aberta mas o `lsof`/`netstat` não retorna PIDs (permissões), a função retorna `True` ("porta livre") e o `uvicorn.run` seguinte falha com bind error. Além disso, `--force` mata **qualquer** processo na porta, não só do Cockpit (`run_cockpit.py:93-98`).

### 1.15 Estado lido/escrito fora do lock e config mutada sem persistir
`server/state_store.py:959-964` (`check_fleet_liveness` lê `get_state` sem `self.lock`), e `get_local_worker_config` (`state_store.py:1045-1065`) usa `setdefault` mutando o estado em memória **sem chamar `_save_state`** — defaults corrigidos não persistem.

## BAIXO

### 1.16 Exceções engolidas em pontos críticos
- `server/web_server.py:363-364` (`file_watch_loop` `except Exception: pass` — silencia erros de sync legado)
- `server/state_store.py:343-348` (`_sync_legacy_file` engole falha)
- `server/pty_manager.py:144-145` (loop de leitura engole erros inesperados sem close)
- `server/code_graph.py:661-663` (`except Exception: pass` em `prepare_task_context`)

### 1.17 Redundância/erro de tipo
`except (RuntimeError, Exception)` em `server/web_server.py:790, 805` (o segundo torna o primeiro inútil).

### 1.18 IDs de mensagens duplicados pós-prune
`server/state_store.py:479, 521, 691` — `msg-{len+1}` e `msg-pruned-summary` fixo podem colidir após `prune_session_context`.

### 1.19 Bloqueio de broadcast por cliente lento
`_broadcast` (`web_server.py:94-111`) faz `await send_text` sem timeout/backpressure — um WS lento atrasa `file_watch_loop` e todo o streaming.

### 1.20 Leak de subscription em `websocket_endpoint`
`server/web_server.py:449-450` — apenas `WebSocketDisconnect` chama `manager.disconnect`; outras exceções de conexão deixam a entrada em `manager.subscriptions`.

### 1.21 Dispositivos de teste em código de produção
`server/workers/local_llm_client.py:95-107` (`hasattr(resp, "mock_calls")`) — lógica de mock do pytest vazada para o `pull_model` real.

### 1.22 Deprecações
`@app.on_event("startup"/"shutdown")` (`web_server.py:367-384`) — substituído por lifespan em FastAPI moderno.

### 1.23 Fallback de raiz expõe o próprio cockpit
`_resolve_project_fs_root` (`web_server.py:1137-1138`) cai para `base_cockpit_dir`; explorer/terminals/graph do projeto "default" expõem o código fonte do cockpit e `states/*` ao cliente local.

### 1.24 Autostart gera systemd/desktop sem quotes
`server/autostart.py:42-52, 63-78` — `Exec={python_exec} {run_script}` e `ExecStart` sem aspas quebram se o path contiver espaços.

### 1.25 `switch_project`/`sync` com divergência de CWD
`server/mcp_server.py:418-426` — `proj_root` usa `os.path.abspath(".")` do processo MCP enquanto `target_pid` vem de `resolve_context_project`; pode sincronizar blueprint em diretório incorreto.

### 1.26 Arquitetura: monólito com responsabilidades misturadas
`web_server.py` (1371 linhas) acumula: API REST, WebSocket, gerenciador Ollama (fallback de ~140 linhas inline), cliente LLM (fallback inline), broadcast, file-watch, terminal PTY, file explorer e vault. `state_store.py` (1221 linhas) mistura persistência, lógica de negócio do Gauntlet, proof-of-work git e circuit breaker. Singleton global `db` (e `local_worker_queue`, `pty_session_manager`) acoplado por import direto em camadas distintas (tools → workers → state_store).

### 1.27 Escrita de logs de terminal p/ disco por sessão
`pty_manager.py:125-130` abre o arquivo a cada chunk (append em micro-lotes de 15ms), sem `flush`/`open` reutilizado — overhead I/O desnecessário sob múltiplas sessões.

---

# 2. PROBLEMAS IDENTIFICADOS (FRONTEND)

## CRÍTICO

### 2.1 Injeção de HTML/atributo via `node.id` sem escape em `onclick` inline
`web/js/slices_chat.js:230`

Gera `onclick="openDrawer('${node.id}')"` com `node.id` vindo da API sem `escapeHtml`. Se o servidor retornar um `id` contendo `'`/`"`/`>` (ex.: `x'); alert(1);//`), o atributo é quebrado e há injeção de markup/exfiltração. O handler global depende ainda de `window.openDrawer`, criado só em `initSlicesChatEvents` (`slices_chat.js:928`), o que torna a ordem de inicialização um requisito silencioso.

*Correção sugerida:* construir via `document.createElement` + `addEventListener`, ou aplicar `escapeHtml` (escapa `'` e `"` → seguro para atributo) — o `escapeHtml` já é usado em outros pontos.

## ALTO

### 2.2 Dois handlers no mesmo botão → 2 POSTs por clique + corrida na escrita de `opencode.json`
- `web/js/settings.js:605-607` liga `btn-ag-save-omniroute → saveHandler('ag-modal')` (POST `/api/omniroute/config`).
- `web/js/sidebar.js:509-536` liga o MESMO botão: copia inputs do modal para os inputs legados e dispara `origSave.click()` (`btn-save-omniroute-config`) → `settings.js:600-602` `saveHandler('tab-view')` → segundo POST.

Um clique = 2 requisições simultâneas gravando `opencode.json` (resultado imprevisível). Além disso, `saveHandler` usa `fetch` cru (`settings.js:565`) enquanto o resto usa `apiFetch` — inconsistência de tratamento de erro.

### 2.3 Logs do Ollama duplicados e DOM sem limite (memory leak)
- `web/js/local_worker.js:531` faz `setInterval(fetchOllamaLogs, 3000)`, e `fetchOllamaLogs` (`:547-560`) busca `limit=80` do início do buffer e re-apenda **todas** as linhas **sem dedupe** — a cada poll, 80 linhas novas vão ao DOM.
- `renderOllamaLogLine` (`:562-631`) apende em **dois** contêineres por linha: `#ollama-terminal-logs` (`:614`) e `#inpage-ollama-logs` (`:626`).
- O contador recalcula via `querySelectorAll('.ollama-log-line').length` por linha (`:617`) — O(n·80) por ciclo.
- A mesma função também é chamada pelos eventos WebSocket (imports em `web/js/websocket_client.js:23-30`) → linhas chegam pelo WS *e* pelo polling, duplicando ainda mais.

O `clearInterval` só existe na troca de contexto (`:541-544`); sem limite de linhas, sem UUID/dedupe, sem `innerHTML` rodízio.

### 2.4 Polling de 2s redundante com WebSocket + re-render total
`web/js/slices_chat.js:939-953`

`setInterval` (2s) busca `/api/state`, compara via `JSON.stringify(remoteState) !== JSON.stringify(state)` e chama `renderAll()` em qualquer diferença — re-renderiza a visão inteira (cards de pairs, worktree, gauntlet). O WS já atualiza tudo (`websocket_client.js:86,210`), então há dupla re-renderização, risco de flicker e de perder input do usuário. O intervalo nunca é limpo.

### 2.5 Chave de API do OmniRoute fica em `<input>` no DOM
`web/js/settings.js:334` (`autofillOpenCodeCredentials`) injeta a `api_key` num `<input type="password">` (`omniroute-key-input`). Qualquer injeção (2.1) ou XSS secundário a exfiltraria com um `document.getElementById(...).value`. Combinado com a duplicação de recipientes (2.2 legado × modal), a chave existe em dois lugares.

## MÉDIO

### 2.6 Dois sistemas de configuração espelhados (legado × Antigravity)
A view antiga de configs (`#view-settings`, `web/index.html:982`) espelha o modal Antigravity com mapeamento manual de inputs (`sidebar.js:520-522`). O botão de navegação dessa view está `display:none; aria-hidden="true"` (`index.html:176`) e a abertura via quick-search vai direto ao modal (`sidebar.js:663+`) — a seção legada é **órfã**: bindada (`initTerminalAndOmniEvents`, `initGovernanceEvents`) mas nunca exibida, mantendo dois caminhos de persistência do mesmo dado.

### 2.7 God-object global (app.js)
`web/app.js:111-136` (`Object.defineProperty`) e `:138-241` (`Object.assign`) expõem praticamente todas as funções dos módulos em `window`. Chamadas indiretas como `window.renderAll()` (`state.js:281`, `sidebar.js:673`) e `window.openDrawer()` criam contratos frágeis a renomeações de import e APIs globais sondáveis. Favorecer exports/imports diretos e um dispatcher explícito.

### 2.8 `getActiveProjectRoot()` duplicada e divergente
`web/js/codebase_graph.js:32` e `web/js/terminal_workspace.js:601` implementam a mesma lógica (fallback `localStorage 'cockpit_target_project'`) separadamente; divergências futuras produzirão raiz de projeto inconsistente entre o grafo, o terminal e os worktrees.

### 2.9 Inicialização inconsistente entre módulos
- `web/js/settings.js:803-814`: `initThemeAndFontSettings`, `initGovernanceEvents`, `loadGovernanceSettings` rodam na **avaliação do módulo**; outras inits só sob bootstrap.
- `web/js/file_explorer.js:462`: singleton instanciado na avaliação do módulo com DOM cacheado no constructor (`:22-39`) — quebra se carregado antes do DOM.

Risco de ordem dupla e de state não inicializado.

### 2.10 Política de fontes duplicada/incoerente
- `web/index.html:11` carrega **Inter + JetBrains Mono** via `<link>` do Google Fonts.
- `web/styles.css:14` (proveniente de `web/css/tokens.css:6`) faz `@import` de **Geist + JetBrains Mono**.

Resultado: JetBrains Mono baixado 2×; Inter baixado e quase sem uso (única referência: `web/css/terminal.css:141`); fontes do app (Geist) bloqueiam o render via `@import`. Unificar em um único fonte.

### 2.11 Pipeline CSS com múltiplas fontes de verdade
`build_css.py:16-27` concatena os 10 módulos em `web/styles.css` (e, quando não é symlink, também em `web/css/styles.css`); `scripts/split_css.py` faz o caminho inverso por intervalos fixos de linhas (antigos), injetando `@import` — re-gerar os módulos reutilizando o split script corromperia o CSS. A página carrega só o bundle (`index.html:8`); os módulos são apenas artefatos de build, mas ficam sujeitos a drift manual.

### 2.12 Atributo `data-model` sem escape em nomes de modelo
`web/js/local_worker.js:~342` injeta o nome do modelo (vindo da API/Ollama) em `data-model="..."` sem `escapeHtml` — possível quebra de atributo se o nome contiver aspas.

### 2.13 Reconexão WS infinita, sem backoff
`web/js/websocket_client.js:55` agenda o retry em 3s já no erro de instanciação; `:225` reconecta a cada 2s no `onclose` — loop infinito sem jitter/backoff máximo, martelando o servidor se ele estiver fora.

### 2.14 Autostart do modal Antigravity é no-op garantido + listeners duplicados
`#btn-autostart-toggle` e `#btn-autostart-toggle-overview` NÃO existem no `index.html` (só referenciados em JS) → `sidebar.js:618,626` sempre retorna `origBtn = null` (apenas alterna classes). Ao mesmo tempo, `settings.js:731-745` também liga listeners nos mesmos botões `ag-toggle-autostart-on/off` (persistindo governança). Dois listeners no mesmo elemento; um deles morto.

### 2.15 CDN xterm.js render-blocking, sem SRI/fallback
`web/index.html:13-16` — xterm + addons carregados como scripts síncronos no `<head>` (bloqueiam render; sem `defer`), sem integridade SRI e sem fallback local — terminal quebra se o CDN falhar.

## BAIXO

### 2.16 Colisões de `z-index`
Sistema de camadas inconsistente: dropdown de terminal `terminal.css:303` (1000) == backdrop do modal de configurações `modals.css:705` (1000); palette `sidebar.css:855` (10000); vários overlay 999-1000 (`worker.css:199`, `right-sidebar.css:641`, `modals.css:705`). Um dropdown aberto pode ficar sob o backdrop.

### 2.17 Código morto / imports shadowed
- `web/js/terminal_workspace.js:1489-1492` `initTabsBarControls` é um stub vazio.
- `ui_utils.js:22` `formatBytes` e `:31` `debounce` exportados e **nunca usados** (debounce reimplementado inline em `file_explorer.js:54`).
- `terminal_workspace.js:6` importa `formatRelativeCwd` da ui_utils, mas o método da classe (`:391`) o sombreia — import morto.
- Seção legada `#view-settings` (`index.html:982`) alimentada e bindada, porém inacessível (ver 2.6).

### 2.18 Landing page duplicada e frágil
- `landing-page/app.js:24-52`: 6 `setTimeout` encadeados (até 3600ms) sem cleanup em navegação; `isRunning` só volta a `false` no último timer; `appendLogEntry` (`:10-22`) cresce o DOM sem limite.
- `landing-page/index.html:25`: link "GitHub" aponta para `https://github.com` (placeholder).
- `landing-page/styles.css` define sistema de tokens próprio paralelo ao do `web/` (drift de identidade visual).
- `landing-page/app.js:1` usa `DOMContentLoaded` enquanto `web/` chegou via módulo — paradigmas distintos.

### 2.19 Acessibilidade
Navegação por abas sem `role="tablist"`/`aria-selected`, palette/quick-search sem `aria-modal`/focus trap; `#nav-tab-settings` `sr-only`+`display:none` esconde navegação de leitores de tela.

### 2.20 Heurísticas frágeis
`web/js/state.js:7-11` detecta backend por `location.port === '8765'`; `state.js:40` lê `localStorage` na avaliação do módulo (quebra em ambientes sem storage).

---

# 3. PROBLEMAS IDENTIFICADOS (LÓGICA DE FUNCIONAMENTO)

## 3.0 RESUMO DO FUNCIONAMENTO

1. O Painel Web (frontend Vanilla JS em `web/`) roda na porta 8765 via FastAPI/uvicorn, iniciado por `run_cockpit.py` — que sobe **apenas** o `web_server.py`; o servidor MCP (`mcp_server.py`, protocolo stdio) é um processo separado, iniciado por cada cliente de IA (`run_cockpit.py:163–185`).
2. Web e MCP compartilham o mesmo estado persistido em JSON em `states/`: índice de projetos (`projects_index.json`), um arquivo por projeto (`states/<id>.json`), terminais (`states/terminals/sessions.json`) e a ponte legado (`workflow_state.json`).
3. `state_store.py` é o singleton de Estado com listeners de broadcast; `web_server.py` registra um listener que emite eventos via WebSocket (`web_server.py:86,116`) — `STATE_FULL`/`STATE_CHANGED`, `PROJECTS_UPDATED`, `GOVERNANCE_*`, `ollama_*`, `worker_queue_updated` (`web_server.py:129,289,317,668,788–807`).
4. O MCP sincroniza o Blueprint do Épico e opera as tools de execução: cria worktrees de fatias (`create_slice_worktree`), prepara contexto (`prepare_task_context`), roda testes (`run_project_tests`/`test_runner.py`), valida conclusão (`verify_completion_evidence`) e gera `HANDOFF.md` (`generate_handoff`) (`mcp_server.py:168,265`).
5. O Local Worker serializa o acesso à GPU por uma fila FIFO de worker único (`LocalWorkerQueue` em `worker_queue.py:85`, `acquire_worker(ticket_id, timeout=300.0)`), usada por `execute_local_builder` (`local_builder_tool.py:736`), que por sua vez invoca modelo local via `local_llm_client` (Ollama gerenciado por `ollama_process_manager`) ou remoto.
6. O patch é gerado em `local_builder_tool` (`apply_surgical_patch`, fallback de scaffold) e aplicado via `patch_engine.py` (SEARCH/REPLACE).
7. O Ollama é subprocesso com pipe de logs, descoberta de porta 11434 e broadcast de `ollama_log`/`ollama_status` por WebSocket.
8. O web_server mantém seções PTY via `PTYSessionManager`, restaurando as sessões persistidas no boot.
9. O portão de conclusão exige `TEST_RAW.log` fresco (<180s) com exit 0 antes de liberar a entrega e gerar o handoff.
10. O frontend re-renderiza dashboard, terminal, slices/chats, sidebar e settings conforme os eventos WebSocket chegam.
11. Esse fluxo previsto depende integralmente do casamento entre o processo MCP (execução) e o processo Web (estado/UI) — e é exatamente nessa fronteira que se concentram as quebras: split-brain de estado, fila por-processo e CWD divergente.

## CRÍTICO

### 3.1 Split-brain de estado: fatias viram "projetos fantasma" e o Épico real nunca recebe o progresso
- `projects_index.json:2–7` define o projeto atual como `bruno-34ae8374` com root `/home/bruno`, mas existem `states/slice-1-974e8592.json`, `slice-2-b41117f1.json`, `slice-3-ad16326e.json` — IDs cujo prefixo 8-hex é `sha256(".../agent-cockpit/.worktrees/slice-N")[:8]` (verificado por hashing) — contendo Épico "Projeto Padrão"/`PLANNING` e `tdd_stage: GREEN_CONFIRMED` em slice-1 (`states/slice-1-974e8592.json`).
- Ou seja, `set_slice_tdd_stage`/`run_project_tests` gravaram o progresso no estado **fantasma**, não no nó do Épico (`bruno-34ae8374` permanece `BACKLOG/PENDING` no `states/bruno-34ae8374.json:139`).
- Causa raiz: ferramentas MCP resolvem raiz por caminho/worktree enquanto o estado resolve por `project_id`/`db.get_project_root`. Ex.: `create_slice_worktree` usa `repo_root="."` (`mcp_server.py:625–631`; `git_worktrees.py:48`), `prepare_task_context` usa `query_impact(".")` (`mcp_server.py:641–680`), já o terminal web resolve worktrees por `db.get_project_root` (`web_server.py:1004–1011`).
- Efeito ponta-a-ponta: dashboard e agentes divergem; handoffs/Gauntlet não refletem o trabalho dos subagentes.

### 3.2 Fila do Local Worker é por-processo e invisível para o dashboard; o stdio do MCP é monothread e bloqueia o cliente inteiro
- `local_worker_queue` é singleton **por processo** (`worker_queue.py:270`); o listener de broadcast é registrado apenas no processo web (`web_server.py:127–130`). Jobs enfileirados no processo MCP em `execute_local_builder` (`local_builder_tool.py:731–736`) nunca disparam `worker_queue_updated` no processo web → o painel de fila fica sempre vazio (o frontend só lê a fila uma vez em `web/js/local_worker.js`).
- O loop stdio do MCP é sequencial (`mcp_server.py:790–853`): `execute_local_builder` fica até **300s** bloqueado em `acquire_worker` (`local_builder_tool.py:736`, `worker_queue.py:85`) travando todas as demais tools/ping da sessão; com 3 fatias "paralelas" a fila chega a ~900s de bloqueio.
- Se o cliente enfileira e morre antes do acquire, o ticket fica no topo e jamais é adquirido → **starvation** de todos os tickets seguintes (timeout 300s cada), contradizendo a promessa de "Worker Queue (FIFO Single-Worker)" (`docs/LOCAL_WORKER_SPEC.md:25`).

### 3.3 PTY/fork: boot bifurca shells órfãos, shutdown não encerra nada e fechamento nunca reaproveita processos
- `pty_manager.py:205,235–273` — `_load_persisted_sessions()` roda no construtor (instanciado no import de `web_server.py:35–42`) e faz `os.fork()` de 1 shell **por sessão persistida** mesmo sem clientes conectados.
- `web_server.py:373–384` — o `shutdown_event` só para o Ollama; **não chama `pty_session_manager.stop_all()`** → a cada restart os shells anteriores ficam órfãos.
- `pty_manager.py:157–169` — `close()` usa `SIGTERM` + `waitpid(WNOHANG)` — shell que não morre vira zombie; morte do servidor com SIGKILL deixa filhos vivos permanentemente.
- `pty_manager.py:64–88` — `os.fork()` dentro de handlers (threadpool do FastAPI) e os `slave_fd` abertos de outras sessões são herdados pelo novo shell → a sessão pode nunca ver EOF (fica "presa").

### 3.4 `project_root` do projeto atual é a HOME (`/home/bruno`), não o repositório
- `states/bruno-34ae8374.json:139`, `states/default.json` e `projects_index.json:7` apontam `project_root: /home/bruno`.
- Consequência verificada em disco: worktrees criadas em `/home/bruno/.worktrees/slice-{1,2,3}` (enquanto `agent-cockpit/.worktrees/` está vazio), ou seja, o Local Builder grava em `$HOME/.worktrees/...`, o file explorer varre `$HOME` recursivo (`web_server.py:1119–1145`) e `run_project_tests` executaria em `$HOME`.

## ALTO

### 3.5 Ponte legado `sync_from_legacy_if_modified` "hijacka" o projeto atual e sobrescreve o vizinho
`state_store.py:760–787`

Resolve o pid pelo `project_root` do legado, copia o conteúdo para o pfile e altera `current_project_id`. Como `default` e `bruno-34ae8374` têm o mesmo root `/home/bruno`, trocar para "default" no WebSocket (`web_server.py:398–407`) é revertido pelo watcher e os dois `*.json` se sobrescrevem mutuamente.

### 3.6 Multi-writer sem locks entre processos e escrita não-atômica
`state_store.py:220–222` (`_save_index`) e `331–334` (`_save_state`) usam `open('w')` direto, sem tempfile+rename e sem lock entre os processos web/MCP. Um crash no meio de `json.dump` corrompe o arquivo; `get_state` cai então em `default_initial_state` silenciosamente (`state_store.py:310–321`) e o próximo save apaga o progresso.

### 3.7 Evidência/handoff em locais divergentes (dependentes do CWD do processo MCP)
`verify_completion_evidence` procura `TEST_RAW.log` em `"."`/`find_latest_blueprint_dir(".")` (`mcp_server.py:682–727`), enquanto `run_project_tests` grava o log em `db.get_project_root`/blueprint (`mcp_server.py:524–545`, `test_runner.py:102–113`). `generate_handoff` também defaulta para `"."` (`mcp_server.py:547–586`). O portão pode nunca encontrar a evidência ou gerar o handoff no repositório errado.

### 3.8 Ollama sem respawn/watchdog e `start()` reporta "started" sem confirmar a porta
`ollama_process_manager.py:128–180`

Não há respawn automático se o processo morrer; `start()` retorna `running=True` imediatamente sem aguardar a porta abrir (divergência com o fallback que tem `auto_wait`, `web_server.py:217–221`); um Popen morto é recriado sem `wait()` (zombie). Primeira inferência pode pegar connection refused → circuit breaker escala.

### 3.9 `apply_surgical_patch`: índice do conteúdo "limpo" aplicado sobre o conteúdo original
`local_builder_tool.py:114–124`

`idx` é calculado em `clean_content` (linhas com `rstrip`) mas usado para fatiar `norm_content` original → em arquivos com trailing whitespace antes do alvo, a substituição ocorre na posição errada, corrompendo o arquivo.

### 3.10 `reset_state` destrói o `project_root`
`state_store.py:731–738`

Usa `default_initial_state(None, None)` → zera `project_root`; pós-reset o projeto perde raiz e a relação com o Épico/arquivos some até nova definição manual.

### 3.11 Steering: consumo global rouba mensagens de outras fatias; IDs colidem; sem lock entre processos
`state_store.py:492–513`

`fetch_unconsumed_steering` não filtra e consome **todas** as mensagens (inclusive as de `slice_id` específico). IDs `msg-{len+1}` (`473–490`) podem se repetir após `prune_session_context` (`681–729`). Cada processo MCP tem seu próprio `db`, então dois builders podem consumir a mesma mensagem concorrentemente.

## MÉDIO

- **3.12 Veredito em inglês vira REJEITADO**: `log_critique_verdict` normaliza por `"APROV" in verdict.upper()` (`state_store.py:450`); `APPROVED` não contém "APROV" → vira `REJEITADO`; enums divergem entre pulse (`REJECTED`) e verdict (`REJEITADO`) (`state_store.py:414–423,465`), enquanto o gate auto aceita ambos (`mcp_server.py:612–616`).
- **3.13 Gate do plano é pré-aprovado**: `create_blueprint_lock` grava `gate_plan_approved: true` sempre (`workflow_lock.py:40–43`) e o estado inicial idem (`state_store.py:119–124`) — a "Governança Real" do plano não tem portão humano real.
- **3.14 Proof of Work com `base_branch="master"` fixo** (`state_store.py:866,992`): repositórios com `main` geram falso `ZERO_COMMIT_DROPPED`/congelamento indevido.
- **3.15 `num_ctx=2048` + prompt com arquivos inteiros** (`local_builder_tool.py:241–246`): truncamento silencioso do contexto; e `is_file_empty_or_blank` remove `//.*` quebrando URLs/strings em JS (`local_builder_tool.py:300–304`).
- **3.16 `manage_local_model(pull)` bloqueia até 600s** (`local_builder_tool.py:930–947`) dentro do stdio monothread.
- **3.17 Troca de projeto global**: qualquer segundo tab muda o `current_project_id` de todos os clientes (`web_server.py:398–407`); e `list_projects` mostra o projeto atual por último (`state_store.py:295`).
- **3.18 `file_watch_loop` trata todo `*.json` de `states/` como estado de projeto** (`web_server.py:343–348`) — inclui os "fantasmas" `slice-*.json` e potenciais `.checkpoint.json` (via `freeze_checkpoint`), que não têm a estrutura completa (`steering_messages`/`gauntlet_log`) → frontend recebe `STATE_FULL` incompleto.
- **3.19 CORS `allow_origins=["*"]` + `allow_credentials=True`** (`web_server.py:46–52`): combinação inválida em browsers (cabeçalho nunca é emitido), mesmo que clientes nativos ignorem.

## BAIXO

- **3.20 `handle_port_conflict` retorna "porta livre" quando `lsof` falha** (`run_cockpit.py:84–86`): porta ocupada por processo alheio sem permissão de listagem → uvicorn morre com "address already in use" em vez do aviso de segurança.
- **3.21 `_tickets` da fila nunca é podado** (`worker_queue.py:28,81–83`): crescimento de memória em sessão longa.
- **3.22 `get_metrics.estimated_tokens_saved` é um cálculo fabricado** (`state_store.py:557`), apresentado como métrica — pode enganar decisões.

## 3.23 COBERTURA DE TESTES

**Testado (e como):**
- `tests/test_worker_queue.py:60–152` — ciclo FIFO, timeout e fila em memória (processo único).
- `tests/test_local_worker_api.py:175–190` — broadcast de `worker_queue_updated`, mas via **mock** (`patch web_server.manager.broadcast_sync`): valida apenas o dispatch no mesmo processo, não o real cross-processo.
- `tests/test_ollama_server_lifecycle.py:172–186` — único teste de WebSocket, restrito a `ollama_log` no mesmo processo.
- `tests/test_issue_6_terminal_pty_persistence.py:86–122` — valida restauração de sessão PTY **bifurcando um shell** (consagra justamente o fork-no-boot que causa órfãos em produção).
- Suítes `test_issue_*` em geral são asserções de string/markup de UI.

**Não testado (lacunas relevantes):**
- `file_watch_loop` e `sync_from_legacy_if_modified` (split-brain default/bruno).
- `handle_port_conflict`/porta ocupada; `run_cockpit` e startup integrado.
- Consumo de steering entre fatias/prune; ids `msg-N`.
- `verify_completion_evidence`, `generate_handoff` (defaults de CWD) e localização de `TEST_RAW.log`.
- `apply_surgical_patch` no fallback de whitespace (corrupção).
- Ciclo de vida PTY: shutdown, órfãos, zombies, SIGKILL, close().
- Ollama: respawn, porta não-aberta, zombie de restart.
- Nenhum teste de integração real MCP+web com WebSocket completo; nenhum teste de concorrência entre os dois processos de estado; nenhum teste de "morte de cliente no meio da fila".

---

# 4. RESUMO POR SEVERIDADE

| Camada | CRÍTICO | ALTO | MÉDIO | BAIXO |
|---|---|---|---|---|
| Backend | 3 | 3 | 9 | 12 |
| Frontend | 1 | 4 | 10 | 5 |
| Lógica de Funcionamento | 4 | 7 | 8 | 3 |
| **Total** | **8** | **14** | **27** | **20** |

## Priorização recomendada (primeira onda)

1. **Segurança (primeiro):** corrigir os Path Traversals (1.1, 1.2, 1.12), o vazamento de API key (1.5), a injeção de `node.id` (2.1) e adicionar autenticação/restrição de CORS (1.6).
2. **Split-brain de estado (3.1, 3.4):** alinhar `project_root` aos repositórios reais, padronizar resolução de raiz entre MCP e web e corrigir o `sync_from_legacy_if_modified` (3.5).
3. **Persistência (1.3, 3.6):** escrita atômica (tempfile+rename) e lock de arquivo entre processos.
4. **Ciclo de vida de processos (3.3, 3.8):** parar PTY no shutdown, reaping correto, respawn do Ollama e validação de porta.
5. **Fila/concorrência (3.2, 1.9, 1.8):** fila compartilhada/observável, `notify_all` no enqueue, lock no Ollama.
6. **Frontend (2.2–2.5):** remover duplo POST, dedupe/limite dos logs, limpar polling redundante e não manter a chave no DOM.