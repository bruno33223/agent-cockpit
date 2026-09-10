# Instruções Operacionais do Servidor MCP: Agent Cockpit

Sempre que o usuário solicitar uma tarefa, modificação ou épico referenciando o **`agent-cockpit`** (por exemplo: *"usando o cockpit faça X"*, *"utilizando o MCP agent-cockpit faça X"* ou `/cockpit`), você DEVE seguir estritamente as regras de orquestração multiagente de alta eficiência e a governança com as **14 skills do Superpowers**:

---

## REGRAS DE OURO DE EFICIÊNCIA DE TOKENS & ARQUITETURA

> [!CRITICAL]
> **1. O ORQUESTRADOR NUNCA CODA DIRETAMENTE:**
> O Orquestrador está **TERMINANTEMENTE PROIBIDO** de utilizar ferramentas de edição (`write_to_file`, `replace_file_content`) para implementar código da aplicação. Toda codificação deve ser feita por subagentes via `invoke_subagent`.
> 
> **2. DIVISÃO ESTRITA DE LEITURA (VAULT PARA ORQUESTRADOR, CÓDIGO PARA BUILDERS):**
> - **O Orquestrador lê EXCLUSIVAMENTE notas `.md` do Vault:** Consulta apenas `query_symbol_impact`/`analyze_codebase_graph` e as notas em `./cockpit-agent/vault/{arquivo}.md` (que já listam classes, métodos, contratos e dependências).
> - **PROIBIÇÃO TOTAL DE LEITURA DE CÓDIGO FONTE PELO ORQUESTRADOR:** O Orquestrador está **TERMINANTEMENTE PROIBIDO** de usar `view_file` ou abrir arquivos de código de produção (`.cs`, `.ts`, `.py`, `.js`, `.cpp`, etc.).
> - **Quem lê o código de produção?** Exclusivamente os Subagentes Executores (Builders) após serem despachados via `invoke_subagent`. Eles lerão as linhas específicas em seus contextos isolados sem gastar a janela do chat principal.
> 
> **3. PROIBIDO EXECUTAR BUILDS OU TESTES NO TERMINAL RAW:**
> É **PROIBIDO** executar `dotnet run`, `dotnet test`, `pytest` ou `npm test` diretamente via `run_command`. Isso cospe centenas de linhas de lixo e polui a janela de contexto.
> - O Orquestrador NUNCA roda testes antes de planejar e despachar.
> - Quando necessário, os testes DEVEM ser executados exclusivamente pela tool MCP `run_project_tests`, que roda em segundo plano e retorna apenas as falhas em JSON enxuto de poucas linhas.
> 
> **4. PROTOCOLO DE COMUNICAÇÃO POR PONTEIRO (ZERO-FLUFF JSON):**
> Subagentes executores e revisores são **ESTRITAMENTE PROIBIDOS de retornar relatórios em prosa ou listas prolixas de arquivos**.
> - Toda documentação detalhada fica gravada no disco (`HANDOFF.md`, `GAUNTLET_LOG.md`) e no MCP (`update_agent_pulse`, `log_critique_verdict`).
> - O retorno final do subagente DEVE ser um micro-JSON de 1 linha:
>   - Executor: `{"status": "DELIVERED", "slice_id": "slice-N", "files_count": <N>}`
>   - Revisor: `{"status": "VERDICT", "slice_id": "slice-N", "verdict": "APROVADO"|"REJEITADO", "attempt": <N>}`
> - Se rejeitado, o Orquestrador não repete os erros no prompt; ele apenas manda o Builder chamar `get_slice_failure_report(slice_id="...")` no MCP.
>
> **5. VALIDAÇÃO DUPLA OBRIGATÓRIA (BUILDER VS. HARSH CRITIC):**
> Nenhuma fatia avança sem Subagente Validador em contexto limpo (`invoke_subagent`), e o Orquestrador atua como Gatekeeper Final de integração.

---

## 🧭 Catálogo das 19 Ferramentas MCP

| Categoria | Ferramenta MCP | Descrição & Propósito |
| :--- | :--- | :--- |
| **Blueprint & Estado** | `sync_blueprint` | Sincroniza o Master Blueprint, fatias verticais e nós com o dashboard e cria `blueprint.lock.json`. |
| | `get_cockpit_state` | Retorna o snapshot completo de telemetria, nós, pares 3x3 e histórico de chat. |
| | `fetch_user_steering` | Obtém mensagens e direcionamentos enviados pelo usuário pelo chat da interface web. |
| | `post_orchestrator_message` | Envia avisos ou solicitações de autorização do orquestrador diretamente para a interface web. |
| **AST & Dependências** | `analyze_codebase_graph` | Mapeia o grafo de chamadas, imports e nós do repositório com 0 tokens. |
| | `query_symbol_impact` | Mapeia o raio de impacto de modificar uma classe, interface ou arquivo específico. |
| **Context Briefing** | `get_slice_spec` | Retorna exclusivamente a especificação técnica e contratos de uma fatia específica. |
| | `prepare_task_context` | Monta o briefing cirúrgico para o Implementer/Reviewer SDD unindo spec, critérios e AST. |
| **Worktrees** | `create_slice_worktree` | Cria workspace git isolado em `.worktrees/{slice_id}` e branch `cockpit/{slice_id}`. |
| | `cleanup_slice_worktree` | Remove o workspace da worktree e limpa branches temporárias após a aprovação. |
| **Telemetria & Gauntlet** | `update_agent_pulse` | Atualiza status dos pares 3x3 (`WORKING`, `WAITING`, `REVIEWING`, `APPROVED`, etc.) no Kanban. |
| | `log_critique_verdict` | Registra o veredito formal da banca revisora com métricas `critical`, `important`, `minor`. |
| | `get_slice_failure_report` | Entrega o diagnóstico compacto da falha diretamente para o Builder (sem tokens no chat). |
| **Testes & Gates** | `run_project_tests` | Executa testes de forma determinística; suporta modos TDD (`standard`, `verify_red`, `verify_green`). |
| | `verify_completion_evidence` | Anti-Slop Completion Gate: valida evidência fresca (<180s) e 0 falhas antes do encerramento. |
| | `check_human_gate` | Verifica se o portão humano (`gate_plan_approved` ou `gate_ship_approved`) foi liberado. |
| **Handoff & Contexto** | `generate_handoff` | Gera e salva `HANDOFF.md` consolidado em disco na pasta da blueprint. |
| | `read_last_handoff` | Lê o último handoff para retomada instantânea de contexto em novas sessões. |
| | `context_pruner` | Compacta histórico de chat e vereditos no servidor, liberando memória de contexto. |

---

## ⚡ Integração com as 14 Skills do Superpowers

1. **`using-superpowers` & `brainstorming`:** Executadas antes do código para elicitar escopo (Spike vs Bounded vs Architectural) e obter aprovação humana.
2. **`writing-plans` & `spec-orchestrator`:** Fatiamento vertical fino (máximo 3 fatias) e matriz de file locks exclusivos.
3. **`using-git-worktrees`:** Operado via MCP `create_slice_worktree`.
4. **`subagent-driven-development` & `dispatching-parallel-agents`:** Orquestrador despacha os 3 builders em lote único via `invoke_subagent`.
5. **`test-driven-development`:** Builder valida que o teste falha via `run_project_tests(tdd_mode='verify_red')` antes de implementar, e depois valida que passa com `tdd_mode='verify_green'`.
6. **`requesting-code-review` & `receiving-code-review`:** Harsh Critics inspecionam o `git diff` e reportam achados com severidades via `log_critique_verdict`.
7. **`systematic-debugging`:** Se rejeitado, o Builder consulta `get_slice_failure_report` e diagnostica a causa-raiz antes de qualquer edição.
8. **`verification-before-completion`:** Acionada via MCP `verify_completion_evidence` antes de finalizar qualquer entrega.
9. **`finishing-a-development-branch`:** Limpeza via `cleanup_slice_worktree` e aprovação do release gate via `check_human_gate`.
10. **`writing-skills`:** Usada para documentar novas convenções do projeto com rigor TDD.

---

## 🚫 Alertas de Redundância (O que NÃO Usar)

- **`executing-plans`:** Redundante e preterida em relação ao SDD + `spec-orchestrator`.
- **Scripts Bash em `skills/subagent-driven-development/scripts/`:** Redundantes; substituídos pelas ferramentas nativas em Python `prepare_task_context` e `get_slice_spec`.
- **Comandos manuais de terminal (`run_command`) para testes e worktrees:** Proibidos; substituídos por `run_project_tests` e `create_slice_worktree`.
