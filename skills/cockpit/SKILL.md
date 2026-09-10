---
name: cockpit
description: Central de comando do Agent Cockpit. Governa o ciclo completo acionando a skill spec-orchestrator para arquitetura e a skill gauntlet-loop para a banca revisora, com telemetria visual e comunicação por ponteiros.
---

# Skill: Agent Cockpit Automation

Esta skill é a **porta de entrada e controladora de voo** do ecossistema **Agent Cockpit**. Ela conecta a telemetria do servidor local, ativa os protocolos de contenção de tokens e **governa a orquestração multiagente unindo as 14 skills do Superpowers e as ferramentas do servidor MCP**:
1. **`spec-orchestrator`**: para mapeamento AST, fatiamento vertical, KISS, Clean Architecture, SOLID e geração da Blueprint.
2. **`gauntlet-loop`**: para governança da execução adversária (Builders vs. Harsh Critics) e auditoria de qualidade.
3. **Superpowers Suite (14 Skills)**: integradas diretamente aos portões de governança, TDD Iron Law, worktrees e code review.

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
> O Orquestrador está **TERMINANTEMENTE PROIBIDO** de utilizar `write_to_file` ou `replace_file_content` para implementar código da aplicação. Toda codificação deve ser feita pelos subagentes executores via `invoke_subagent`.
> 
> **2. DIVISÃO ESTRITA DE LEITURA (VAULT PARA ORQUESTRADOR, CÓDIGO PARA BUILDERS):**
> - **O Orquestrador lê EXCLUSIVAMENTE notas `.md` do Vault:** Consulta apenas `query_symbol_impact`/`analyze_codebase_graph` e as notas em `./cockpit-agent/vault/{arquivo}.md` (que já trazem classes, métodos públicos, contratos e dependências).
> - **PROIBIÇÃO TOTAL DE LEITURA DE CÓDIGO FONTE PELO ORQUESTRADOR:** O Orquestrador está **TERMINANTEMENTE PROIBIDO** de usar `view_file` em arquivos de código de produção (`.cs`, `.ts`, `.py`, `.js`, etc.).
> - **Quem lê o código de produção?** Exclusivamente os Subagentes Executores (Builders) após serem despachados via `invoke_subagent`. Eles lerão as linhas específicas em seus contextos isolados.
> 
> **3. PROIBIDO EXECUTAR BUILDS OU TESTES NO TERMINAL RAW:**
> É **PROIBIDO** executar `dotnet run`, `dotnet test`, `pytest` ou `npm test` diretamente via `run_command`. Isso cospe centenas de linhas de lixo e polui a janela de contexto.
> - O Orquestrador NUNCA roda testes antes de planejar e despachar.
>   - Quando necessário, os testes DEVEM ser executados exclusivamente pela tool MCP `run_project_tests(test_command='...', working_dir='...')`, passando explicitamente o comando desejado (ex: `'dotnet build'` ou comando específico da suíte de testes), que roda em segundo plano e retorna apenas as falhas em JSON enxuto. NUNCA omita o `test_command`.
> 
> **4. PROTOCOLO DE COMUNICAÇÃO POR PONTEIROS (ZERO-FLUFF JSON):**
> Subagentes executores e revisores são **ESTRITAMENTE PROIBIDOS de retornar resumos em prosa, ensaios literários ou listas longas de arquivos no chat final**.
> - Toda documentação detalhada fica gravada no disco (`HANDOFF.md`) e no MCP (`update_agent_pulse` / `log_critique_verdict`).
> - A resposta textual final do Orquestrador no chat DEVE ser **um micro-ponteiro de 4 linhas**, sem textão de resumo:
>   ```markdown
>   ✅ **Épico Concluído: [Nome]**
>   - Fatias: 3/3 aprovadas pelo Harsh Critic
>   - Handoff & Detalhes: [cockpit-agent/blueprints/{epico}/HANDOFF.md]
>   - Telemetria & Grafo: http://localhost:8765
>   ```

---

## 🔗 Matriz Unificada de Skills & Ferramentas MCP

| Fase | Skill Superpowers / Cockpit | Tool MCP Correspondente | Papel & Protocolo |
| :--- | :--- | :--- | :--- |
| **0. Concepção** | `using-superpowers`, `brainstorming` | `fetch_user_steering`, `read_last_handoff` | Alinhamento de intenção, portão de aprovação humana, leitura do último handoff. |
| **1. Arquitetura** | `writing-plans`, `spec-orchestrator` | `query_symbol_impact`, `analyze_codebase_graph`, `sync_blueprint` | Mapeamento AST de baixo custo, fatiamento vertical e sincronização visual. |
| **2. Isolamento** | `using-git-worktrees` | `create_slice_worktree` | Workspaces isolados em `.worktrees/slice-N` sem poluir a branch principal. |
| **3. Context Briefing** | `subagent-driven-development`, `dispatching-parallel-agents` | `prepare_task_context`, `get_slice_spec` | Briefing cirúrgico isolado por fatia; despacho simultâneo da frota 3x3. |
| **4. Construção TDD** | `test-driven-development` | `run_project_tests(tdd_mode='verify_red' / 'verify_green')`, `update_agent_pulse` | TDD Iron Law: teste falha antes de codar; passa após codar; telemetria em tempo real. |
| **5. Auditoria Cega** | `requesting-code-review`, `receiving-code-review`, `gauntlet-loop` | `run_project_tests`, `log_critique_verdict` | Inspeção cega de `git diff` e métricas estruturadas (`critical`, `important`, `minor`). |
| **6. Diagnóstico** | `systematic-debugging` | `get_slice_failure_report` | Causa-raiz obrigatória antes de propor correção; zero tokens no chat principal. |
| **7. Anti-Slop Gate** | `verification-before-completion` | `verify_completion_evidence` | Bloqueio de conclusão se o teste tiver >180s ou falhas não resolvidas. |
| **8. Finalização** | `finishing-a-development-branch` | `cleanup_slice_worktree`, `check_human_gate`, `generate_handoff`, `context_pruner` | Limpeza de worktree, portão humano, emissão de handoff e compactação de contexto. |

---

## ⚠️ Diagnóstico de Redundâncias (O que NÃO Usar)

1. **`executing-plans` (REDUNDANTE / PRETERIDO):**
   - Esta skill do Superpowers é um fallback para terminais mono-agente sem capacidade de invocar subagentes. Como o Cockpit opera nativamente com a frota 3x3 (`invoke_subagent`), **`executing-plans` NUNCA deve ser acionada**; use sempre `spec-orchestrator` + `subagent-driven-development`.
2. **Scripts Bash em `skills/subagent-driven-development/scripts/` (REDUNDANTE):**
   - Scripts como `review-package`, `task-brief` e `sdd-workspace` foram feitos para ambientes Unix/Bash. O Cockpit substituiu essa necessidade pelas tools MCP nativas em Python `prepare_task_context` e `get_slice_spec`, que rodam 100% no Windows sem dependência de terminal.
3. **Comandos de Shell de Worktree manuais (REDUNDANTE):**
   - Não execute comandos manuais como `git worktree add` via `run_command`. Use sempre a tool MCP `create_slice_worktree`, que trata normalização de diretórios e bloqueios de arquivos no Windows automaticamente.
4. **Execução de Testes no Terminal Raw (PROIBIDO):**
   - Nunca use `run_command` para rodar suítes de teste diretamente. Use sempre `run_project_tests` para filtrar 95% do ruído e manter o chat econômico.

---

## 🚀 Fluxo Operacional Encadeado

### Etapa 1: Governança Inicial & Escuta Humana
1. Ative `using-superpowers` e consulte `fetch_user_steering` no MCP para absorver mensagens e direcionamentos do usuário no painel.
2. Execute `read_last_handoff` no MCP para retomar o contexto do último épico sem gastar tokens.
3. Se a tarefa for nova ou criativa, rode a skill `brainstorming` e aguarde a aprovação da abordagem pelo usuário antes de codificar.

### Etapa 2: Planejamento Arquitetural (Skill: `spec-orchestrator` + `writing-plans`)
1. Mapeie o impacto de símbolos via `query_symbol_impact` ou consulte `./cockpit-agent/vault/INDEX.md`.
2. Decomponha a demanda em até 3 fatias verticais autossuficientes seguindo os critérios de granularidade do `writing-plans`.
3. Defina explicitamente no `MASTER_BLUEPRINT.md` as diretrizes arquiteturais (KISS, Clean Architecture, SOLID) e a **Matriz de File Locks Exclusivos**.
4. Sincronize o dashboard visual chamando `sync_blueprint` no MCP (gerando `blueprint.lock.json`).

### Etapa 3: Isolamento de Workspace (Skill: `using-git-worktrees`)
1. Para cada fatia vertical a ser executada, chame `create_slice_worktree(slice_id="slice-N")` no MCP para isolar branches e arquivos em `.worktrees/slice-N`.

### Etapa 4: Construção e Auditoria Adversária (Skill: `gauntlet-loop` + SDD)
1. **Despacho Concorrente dos Builders (Padrão SDD + TDD Iron Law):**
   - Dispare os 3 executores simultaneamente via `invoke_subagent` em lote único.
   - Cada Builder chama `prepare_task_context(slice_id="slice-N", role_type="implementer")` no MCP.
   - Aplica a Iron Law do `test-driven-development`: cria o teste que falha e valida com `run_project_tests(tdd_mode="verify_red")`.
   - Implementa o código de produção mínimo e valida com `run_project_tests(tdd_mode="verify_green")`.
   - Atualiza a seção `<!-- COCKPIT_NOTES_START -->` no vault e retorna estritamente: `{"status": "DELIVERED", "slice_id": "slice-N", "files_count": <N>}`.
2. **Despacho Concorrente dos Harsh Critics (Skill: `requesting-code-review` & `receiving-code-review`):**
   - Dispare os 3 revisores em contexto limpo via `invoke_subagent` em lote único.
   - Crítico audita `git diff` real e executa a verificação via `run_project_tests`.
   - Classifica achados em `critical`, `important`, `minor`.
   - Registra o veredito via `log_critique_verdict` e no `GAUNTLET_LOG.md`.
   - Se rejeitado: Builder aciona a skill `systematic-debugging` e consulta o relatório via `get_slice_failure_report(slice_id="slice-N")`.

### Etapa 5: Anti-Slop Gate, Finalização & Handoff
1. Execute a skill `verification-before-completion` chamando a tool MCP `verify_completion_evidence` para garantir evidência de teste fresca (<180s) e 0 falhas.
2. Verifique aprovação humana com `check_human_gate("gate_ship_approved")`.
3. Limpe as worktrees executando `cleanup_slice_worktree(slice_id="slice-N")`.
4. Gere o handoff formal chamando `generate_handoff` no MCP.
5. Chame a tool MCP `context_pruner` para consolidar o estado e limpar o contexto.
6. Emite exclusivamente o micro-ponteiro de conclusão no chat.
