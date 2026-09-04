---
name: cockpit
description: Ativa o workflow automatizado do Agent Cockpit. Cria o Master Blueprint versionado, usa análise de dependências sem tokens (AST Graph), governa a frota 3x3 com comunicação por ponteiros JSON (zero-fluff) e validações em dois níveis.
---

# Skill: Agent Cockpit Automation

Esta skill unificada ativa o ecossistema do **Agent Cockpit**: orquestração da **frota 3x3 de subagentes reais**, análise de dependências determinística sem tokens (**Zero-Token Codebase Graph**) e protocolo de comunicação ultra-compacto por ponteiros (**Pointer-Based Communication**).

---

## Gatilho de Uso

Quando o usuário disser:
- *"utilizando o MCP agent-cockpit, faça [tarefa]"*
- *"usando o cockpit, faça [tarefa]"*
- `"/cockpit faça [tarefa]"`

---

## REGRAS DE OURO DA ORQUESTRAÇÃO

> [!CRITICAL]
> **1. O ORQUESTRADOR NUNCA CODA DIRETAMENTE:**
> O Orquestrador está **TERMINANTEMENTE PROIBIDO** de utilizar `write_to_file` ou `replace_file_content` para implementar a aplicação. Toda codificação deve ser feita pelos subagentes executores via `invoke_subagent`.
> 
> **2. DIVISÃO ESTRITA DE LEITURA (VAULT PARA ORQUESTRADOR, CÓDIGO PARA BUILDERS):**
> - **O Orquestrador lê EXCLUSIVAMENTE notas `.md` do Vault:** Consulta apenas `query_symbol_impact`/`analyze_codebase_graph` e as notas em `./cockpit-agent/vault/{arquivo}.md` (que já trazem classes, métodos, contratos e dependências).
> - **PROIBIÇÃO TOTAL DE LEITURA DE CÓDIGO FONTE PELO ORQUESTRADOR:** O Orquestrador está **TERMINANTEMENTE PROIBIDO** de usar `view_file` em arquivos de código de produção (`.cs`, `.ts`, `.py`, `.js`, etc.).
> - **Quem lê o código de produção?** Exclusivamente os Subagentes Executores (Builders) após serem despachados via `invoke_subagent`. Eles lerão as linhas específicas em seus contextos isolados.
> 
> **3. PROIBIDO EXECUTAR BUILDS OU TESTES NO TERMINAL RAW:**
> É **PROIBIDO** executar `dotnet run`, `dotnet test`, `pytest` ou `npm test` diretamente via `run_command`. Isso cospe centenas de linhas de lixo e polui a janela de contexto.
> - O Orquestrador NUNCA roda testes antes de planejar e despachar.
> - Quando necessário, os testes DEVEM ser executados exclusivamente pela tool MCP `run_project_tests`, que roda em segundo plano e retorna apenas as falhas em JSON enxuto.
> 
> **4. PROTOCOLO DE COMUNICAÇÃO POR PONTEIROS (ZERO-FLUFF JSON):**
> Subagentes executores e revisores são **ESTRITAMENTE PROIBIDOS de retornar resumos em prosa, ensaios literários ou listas longas de arquivos no chat final**.
> - O relatório técnico rico DEVE ser gravado no disco (`GAUNTLET_LOG.md`) e no MCP (`update_agent_pulse` / `log_critique_verdict`).
> - A resposta textual do subagente para o Orquestrador DEVE ser **exclusivamente um micro-JSON de 1 linha** (`{"status": "DELIVERED", ...}` ou `{"status": "VERDICT", ...}`).
> - Isso economiza 98% dos tokens da janela de contexto.
>
> **5. NENHUMA FATIA É APROVADA SEM SUBAGENTE VALIDADOR:**
> O Orquestrador não pode autoaprovar tarefas. Um Subagente Validador (Harsh Critic) em contexto limpo DEVE ser despachado via `invoke_subagent` para testar e validar cada fatia.
>
> **6. GATE DE VALIDAÇÃO FINAL DO ORQUESTRADOR:**
> Ao término das 3 fatias, o Orquestrador audita a coesão global e integra os módulos ponta a ponta.

---

## Protocolo de Execução 100% Automático

### Fase 1: Mapeamento de Impacto sem Tokens (`query_symbol_impact`)
- Antes de estruturar o blueprint, consulte o raio de impacto das classes/arquivos centrais usando a ferramenta MCP:
  `call_mcp_tool(ServerName="agent-cockpit", ToolName="query_symbol_impact", Arguments={"symbol_or_path": "[ClasseOuArquivo]"})`
- O MCP mapeia classes, imports e dependências em C#, Python ou JS/TS em 30ms com **zero tokens gastos**.

### Fase 2: Master Blueprint & Banco de Dados Versionado
- Decomponha a demanda em **até 3 fatias verticais autossuficientes** (do banco à UI).
- Crie no workspace:
  - `01_[nome_da_tarefa]/MASTER_BLUEPRINT.md` (ou `02_...`).
  - `01_[nome_da_tarefa]/GAUNTLET_LOG.md`.

### Fase 3: Sincronização do Dashboard MCP
- Chame `call_mcp_tool(ServerName="agent-cockpit", ToolName="sync_blueprint", Arguments={...})`.
- O dashboard visual em `http://localhost:8765` renderiza o fluxograma e os kanbans instantaneamente.

### Fase 4: Despacho dos Executores (Builders) com Resposta Compacta
- O Orquestrador chama `invoke_subagent` para despachar os Builders:
  ```json
  invoke_subagent(
    Subagents: [
      {
        "TypeName": "self",
        "Role": "Executor 1 - [Título da Fatia 1]",
        "Prompt": "Você é o Subagente Executor 1. Implemente a Fatia 1 conforme o MASTER_BLUEPRINT.md.\n1. Atualize o MCP com update_agent_pulse(pair_id=1, builder_status='WORKING').\n2. Use query_symbol_impact no MCP para checar dependências antes de alterar código.\n3. Codifique a solução completa no workspace.\n4. REGRA DE RESPOSTA ZERO-FLUFF: É PROIBIDO escrever resumos em prosa. Sua resposta final DEVE ser estritamente: {\"status\": \"DELIVERED\", \"slice_id\": \"slice-1\", \"files_count\": <qtd>}."
      }
    ]
  )
  ```

### Fase 5: Despacho dos Validadores (Harsh Critics) com Resposta Compacta
- Assim que o executor responder, o Orquestrador chama `invoke_subagent` com o Validador:
  ```json
  invoke_subagent(
    Subagents: [
      {
        "TypeName": "self",
        "Role": "Validador 1 - Auditoria Cega Fatia 1",
        "Prompt": "Você é o Subagente Validador 1 (Harsh Critic) em contexto limpo. Audite a Fatia 1 contra o MASTER_BLUEPRINT.md.\n1. Atualize o MCP com update_agent_pulse(pair_id=1, critic_status='REVIEWING').\n2. Execute testes reais no terminal (run_command) e inspecione o código (view_file).\n3. Valide item a item dos critérios de aceitação.\n4. Grave o relatório detalhado no MCP via log_critique_verdict e salve no GAUNTLET_LOG.md.\n5. REGRA DE RESPOSTA ZERO-FLUFF: É PROIBIDO escrever ensaios ou justificativas longas nesta mensagem. Retorne estritamente: {\"status\": \"VERDICT\", \"slice_id\": \"slice-1\", \"verdict\": \"APROVADO\" ou \"REJEITADO\", \"attempt\": 1}."
      }
    ]
  )
  ```
- **Se REJEITADO:** O Orquestrador vê `verdict: "REJEITADO"`. Ele **NÃO repete o texto das falhas**. Ele simplesmente despacha o Executor dizendo:
  > *"Tentativa 2: Consulte o diagnóstico chamando get_slice_failure_report(slice_id='slice-1') no MCP ou lendo o GAUNTLET_LOG.md e aplique as correções."*

### Fase 6: Validação Final do Orquestrador (Gatekeeper)
- Quando todas as fatias estiverem aprovadas, o Orquestrador audita a coesão ponta a ponta de todo o sistema e notifica a conclusão via `post_orchestrator_message`.

### Fase 7: Escuta de Direcionamento Humano
- Antes de cada ciclo, consulte `fetch_user_steering` para absorver instruções do chat do painel.
