---
name: cockpit
description: Central de comando do Agent Cockpit. Governa o ciclo completo acionando a skill spec-orchestrator para arquitetura e a skill gauntlet-loop para a banca revisora, com telemetria visual e comunicação por ponteiros.
---

# Skill: Agent Cockpit Automation

Esta skill é a **porta de entrada e controladora de voo** do ecossistema **Agent Cockpit**. Ela conecta a telemetria do servidor local, ativa os protocolos de contenção de tokens e **encadeia explicitamente as skills especializadas**:
1. **`spec-orchestrator`**: para mapeamento AST, fatiamento vertical, KISS, Clean Architecture, SOLID e geração da Blueprint.
2. **`gauntlet-loop`**: para governança da execução adversária (Builders vs. Harsh Critics) e auditoria de qualidade.

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
> - Quando necessário, os testes DEVEM ser executados exclusivamente pela tool MCP `run_project_tests`, que roda em segundo plano e retorna apenas as falhas em JSON enxuto.
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

## 🔗 Fluxo Encadeado de Execução

### Etapa 1: Governança Inicial & Escuta Humana
1. Consulte `fetch_user_steering` no MCP para absorver instruções ou correções do painel web.
2. Verifique se existe handoff anterior com `read_last_handoff` no MCP para retomar o contexto sem ler arquivos.

### Etapa 2: Planejamento Arquitetural (Ativar Skill: `spec-orchestrator`)
> O Orquestrador DEVE seguir rigorosamente a skill **`spec-orchestrator`** (`SKILL.md`):
1. Mapeie o impacto via `query_symbol_impact` ou consulte `./cockpit-agent/vault/INDEX.md`.
2. Decomponha a demanda em até 3 fatias verticais autossuficientes.
3. Defina explicitamente no `MASTER_BLUEPRINT.md` as diretrizes arquiteturais (KISS, Clean Architecture, SOLID) e a **Matriz de File Locks Exclusivos**.
4. Sincronize o dashboard visual chamando `sync_blueprint` no MCP (gerando `blueprint.lock.json`).

### Etapa 3: Construção e Auditoria Adversária (Ativar Skill: `gauntlet-loop`)
> O Orquestrador DEVE governar a execução adversária seguindo a skill **`gauntlet-loop`** (`SKILL.md`):
1. **Despacho Concorrente dos Builders:**
   - Dispare os 3 executores simultaneamente via `invoke_subagent` em lote único.
   - Cada Builder recebe sua fatia isolada via `get_slice_spec(slice_id="...")`.
   - **Obrigação do Builder (Living Documentation):** Ao codificar, o Builder deve atualizar o bloco `<!-- COCKPIT_NOTES_START -->` da nota correspondente em `./cockpit-agent/vault/{arquivo}.md` registrando as mudanças e decisões arquiteturais.
   - Retorno do Builder: micro-JSON `{"status": "DELIVERED", "slice_id": "slice-N", "files_count": <N>}`.
2. **Despacho Concorrente dos Harsh Critics (Auditoria Cega):**
   - Dispare os 3 revisores em contexto limpo via `invoke_subagent` em lote único.
   - O Crítico audita contra o checklist quádruplo:
     ✓ Testes passando 100% via `run_project_tests`
     ✓ Filtro Anti-Overengineering (KISS)
     ✓ Respeito a fronteiras de domínio (Clean & SOLID)
     ✓ Cumprimento estrito dos File Locks
   - Registra veredito via `log_critique_verdict` e no histórico.
   - Retorno do Crítico: micro-JSON `{"status": "VERDICT", "slice_id": "slice-N", "verdict": "APROVADO"|"REJEITADO", "attempt": N}`.

### Etapa 4: Finalização & Handoff
1. Quando todas as 3 fatias forem aprovadas, o Orquestrador audita a coesão global e chama `generate_handoff` no MCP.
2. Emite exclusivamente o micro-ponteiro de conclusão no chat.
