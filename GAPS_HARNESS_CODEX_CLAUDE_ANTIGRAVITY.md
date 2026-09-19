# Diagnóstico de Engenharia: GAPs do Agent Cockpit vs. Codex, Claude Code & Antigravity

> **Classificação:** Documento Técnico de Arquitetura & Roadmap de Produto  
> **Data:** Setembro de 2026  
> **Autor:** Staff Principal AI Systems Architect  
> **Alvo:** Agent Cockpit — Plataforma Autônoma de Engenharia de Software  

---

## 1. Visão Executiva & O que é um "Agent Harness"?

No ecossistema moderno de desenvolvimento guiado por IA, existe uma diferença fundamental entre uma **ferramenta de chat com LLM** e um **Agent Harness de Engenharia (como Claude Code, OpenAI Codex CLI e Google Antigravity)**.

* **Chat com LLM:** Recebe texto, cospe texto em streaming. Se o modelo errar um comando, alucinar um caminho ou entrar em loop, o usuário precisa intervir manualmente.
* **Agent Harness:** É um **sistema operacional para agentes autônomos**. Ele provê:
  1. **Governança de Contexto:** Gerenciamento rígido de janela de contexto, compactação semântica, árvore de dependências (AST) e poda de tokens irrelevantes.
  2. **Isolamento de Execução:** Sandboxing de processos, PTY multiplexado, git worktrees descartáveis para evitar poluição da branch principal.
  3. **Multi-Agent Orchestration & Hierarchy:** Capacidade de despachar subagentes especializados em paralelo (Builders vs. Critics/Auditors).
  4. **Feedback Loops & Self-Correction:** Validação via testes automatizados (TDD), linters e verificadores estáticos antes de declarar uma tarefa concluída.
  5. **Controle e Observabilidade (Human-in-the-Loop):** Transparência total de pensamento (Chain-of-Thought), rastreabilidade de chamadas de ferramentas e capacidade de intervenção imediata.

O **Agent Cockpit** já possui fundações extraordinárias — interface visual PTY, integração com OpenCode, backend assíncrono em Python e orquestrador Zeus. No entanto, para atingir o nível dos líderes de mercado (e superá-los com ferramentas extras), é necessário fechar os GAPs identificados abaixo.

---

## 2. Matriz Comparativa de Capacidades

| Capacidade Arquitetural | OpenAI Codex | Anthropic Claude Code | Google Antigravity | Agent Cockpit (Estado Atual) | Meta Cockpit (Próximo Nível) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Context Window Engine** | Alto (embeddings) | Excelente (prompt caching + subagentes) | Estado da Arte (AST Graph + Pruning) | Básico (Histórico linear + System Prompts) | **AST Graph Engine + Pruner Dinâmico** |
| **Isolamento de Execução** | Sandbox em Cloud | Local (permissão por comando) | Worktrees Git + MCPs | Worktree manual + PTY local direto | **Git Worktrees Automáticos por Subagente** |
| **Subagentes Paralelos** | Limitado | Tasks em Background | Frotas Paralelas 3x3 (Branching) | Planejado / Parcial | **3x3 Fleet (3 Builders x 3 Harsh Critics)** |
| **Banca Revisora (Harsh Critic)**| Ausente | Ausente (auto-revisão) | Integrado via Prompts de Auditoria | Gauntlet Loop planejado | **Gauntlet Loop Automático com Vetos** |
| **Interface Visual & Telemetria**| CLI puro | CLI puro | IDE nativa (Webview/VSCode fork) | **Web Cockpit Completo (Painel + Terminais)** | **IDE Cockpit com PTY, Chat e Grafo Visual** |
| **STT / Áudio Local em RAM** | Ausente | Ausente | Ausente | **Whisper/WAV Engine Integrado em Memória** | **Voz em Tempo Real com Zero Dependência de Nuvem** |
| **MCP (Model Context Protocol)**| Parcial | Nativo (Claude Desktop/CLI) | Nativo (Lazy-loaded Servers) | MCP Server implementado | **Dynamic Tool Registration & Schema Auto-heal** |

---

## 3. Diagnóstico Detalhado dos GAPs

### GAP 1: Context Engine & Token Budgeting (O "Gargalo dos Tokens")
* **O Problema Atual:**
  Quando o contexto cresce (múltiplos arquivos lidos, saídas longas de comandos no terminal), o histórico enviado ao modelo se torna gigantesco. Modelos menores (como `nemotron-3.5` ou modelos locais) entram em colapso autorregressivo (repetição infinita de tokens sem sentido).
* **Como os Gigantes Fazem:**
  - **Claude Code:** Usa Prompt Caching agressivo e ferramentas de leitura (`read_file`) que suportam `offset` e `limit`, além de truncar outputs excessivos no harness.
  - **Antigravity:** Mantém um grafo semântico da base de código (AST / ctags / tree-sitter). Em vez de jogar arquivos inteiros, injeta assinaturas de funções e apenas o miolo relevante. Possui um `context_pruner` nativo.
* **A Solução para o Cockpit:**
  1. Implementar truncamento automático de outputs de ferramentas no backend (`zeus_chat_engine.py`): se um `bash` ou `grep` retornar mais de 2.000 tokens, o harness compacta e salva o log completo em disco/scratch, fornecendo um ponteiro ao modelo.
  2. Context Pruner: condensar turnos antigos do chat em um sumário semântico antes que ultrapassem 60% da janela do modelo selecionado.

---

### GAP 2: Execução com Worktrees Git Isolados (Segurança e Concorrência)
* **O Problema Atual:**
  Se o Zeus ou um subagente rodar um comando que edita arquivos ou quebra o código, a branch ativa do usuário é diretamente afetada. Se dois subagentes rodarem em paralelo na mesma pasta, haverá conflito de escrita no disco.
* **Como os Gigantes Fazem:**
  - **Antigravity:** Cada subagente recebe um workspace mode (`branch` ou `share`), criando um Git Worktree temporário em `/tmp` ou `.worktrees/`. Se a tarefa falhar ou o revisor reprovar, o worktree é simplesmente descartado sem afetar a árvore principal.
* **A Solução para o Cockpit:**
  1. Utilizar a ferramenta nativa `create_slice_worktree` e `cleanup_slice_worktree` já esboçada no MCP do Cockpit.
  2. Ao disparar uma tarefa via chat que envolva modificação de código, criar automaticamente um worktree isolado (`git worktree add .cockpit/worktrees/<task-id> HEAD`).
  3. Somente após a aprovação da banca revisora, fazer cherry-pick ou fast-forward merge na branch principal.

---

### GAP 3: Frotas de Subagentes & Padrão Gauntlet Loop (Harsh Critic)
* **O Problema Atual:**
  O usuário notou: *"as harsh critic foram invocadas junto com os builders, como vão validar algo que ainda não foi feito?"*. O fluxo multi-agente precisa de sincronização temporal estrita.
* **Como os Gigantes Fazem:**
  - No Antigravity e Claude Code, subagentes operam em fases DAG (Grafo Acíclico Dirigido):
    1. **Fase de Planejamento (Spec/Blueprint):** Gera o contrato da fatia vertical.
    2. **Fase de Execução (Builders):** Implementam os arquivos e rodam os testes.
    3. **Fase de Auditoria (Harsh Critic):** Executa após o Builder declarar conclusão, inspeciona o `git diff` e a evidência de testes, emitindo um veredito binário (`PASS` ou `REJECT`).
* **A Solução para o Cockpit:**
  1. Ajustar o `spec-orchestrator` para seguir estritamente o pipeline de 2 tempos:
     - **Tempo 1:** Builders codificam na fatia isolada.
     - **Tempo 2:** Ao receber o evento `BUILDER_FINISHED`, disparar a respectiva Harsh Critic com foco em quebrar a solução (análise de corner cases, vazamentos de memória, testes faltantes).

---

### GAP 4: Robustez no Parsing de Ferramentas & Tolerância a Falhas
* **O Problema Atual:**
  Identificado nas capturas de tela: eventos de `tool_use` vinham sem mapeamento correto de argumentos (`part.tool`, `part.state.input`), resultando em caixas vazias `🔧 tool EXEC {} OK` e bloqueio visual.
* **A Solução Implementada & Melhorias Futuras:**
  - **Já corrigido:** Backend agora normaliza `part.get("tool")`, `state.get("input")`, `state.get("title")`, `state.get("output")`, e o frontend renderiza cards ricos categorizados (`EXEC`, `READ`, `WRITE`) com saída expansível e sem blocos vazios.
  - **Próximo passo:** Permitir cancelamento imediato de comandos em execução (botão "Interromper Tool") via sinal SIGINT direto ao processo subjacente do OpenCode.

---

### GAP 5: Seleção Dinâmica de Modelos & Prevenção de Degeneração
* **O Problema Atual:**
  Modelos com fine-tuning fraco para raciocínio estruturado (ex: `nemotron-3.5-lightning-free`) entram em loop de repetição de tokens ("womenomia... only only with The :").
* **A Solução para o Cockpit:**
  1. **Detector de Degeneração no Backend:** Adicionar uma heurística simples no streaming do `zeus_chat_engine.py`: se os últimos 5 chunks contiverem padrões de repetição n-gram idênticos mais de 4 vezes, o engine interrompe o streaming com erro amigável, sugerindo alternar para um modelo de raciocínio mais robusto (como `opencode/big-pickle` ou modelos Claude/GPT).
  2. **Defaults de Alta Confiabilidade:** Configurar `opencode/big-pickle` como padrão (já aplicado).

---

## 4. Onde o Agent Cockpit Já Supera os Gigantes (Vantagens Competitivas)

O Cockpit possui diferenciais que **Codex, Claude Code e Antigravity não oferecem nativamente**:

1. **Cockpit Visual Unificado com PTY Real:**
   - Claude Code e Codex rodam estritamente dentro de um terminal CLI clássico.
   - O Cockpit oferece um painel unificado com abas PTY interativas reais (xterm.js), permitindo usar bash, claude, opencode e visual chat lado a lado na mesma tela.
2. **STT Local em RAM com Zero Latência e Sem Nuvem:**
   - Permite falar com o orquestrador via microfone sem enviar áudio para servidores terceiros, com processamento rápido e seguro em RAM.
3. **Controle Físico das Instâncias:**
   - Kill switches visuais para cada terminal e subagente.
   - Visão de grid em tempo real com métricas de CPU, RAM e status do processo.

---

## 5. Roadmap de Ação Recomendado (Próximos Passos Práticos)

### 📌 Milestone 1: Estabilização & Polimento do Visual Chat (Imediato)
* [x] Normalização de ferramentas no streaming SSE do OpenCode (`server/zeus_chat_engine.py`).
* [x] Cards visuais de ferramentas com diferenciação por cor/ícone (READ, WRITE, EXEC) e saída expansível (`zeus_chat_workspace.js` e `zeus_chat_ui.js`).
* [x] Preferência padrão pelo modelo estável `opencode/big-pickle`.
* [ ] Adicionar watchdog anti-loop de tokens repetidos no backend.

### 📌 Milestone 2: Harness Sandbox & Isolamento por Worktrees (Curto Prazo)
* [ ] Integrar a criação automática de git worktree ao iniciar uma tarefa complexa no chat.
* [ ] Implementar visualizador de `git diff` direto dentro do card de conclusão da mensagem do Zeus.

### 📌 Milestone 3: Orquestração 3x3 Gauntlet Loop (Médio Prazo)
* [ ] Implementar a barreira de sincronização (Builders -> Conclusão -> Harsh Critics).
* [ ] Painel visual no Cockpit com os 3 cards dos pares (Builder 1 vs Critic 1, Builder 2 vs Critic 2, Builder 3 vs Critic 3) exibindo status verde/vermelho em tempo real.

### 📌 Milestone 4: Context Pruner & AST Engine (Longo Prazo)
* [ ] Integrar Tree-sitter para indexação rápida de símbolos no backend Python.
* [ ] Compactador automático de histórico de conversas antigas.
