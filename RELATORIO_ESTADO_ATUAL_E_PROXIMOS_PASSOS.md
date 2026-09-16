# 🛰️ Agent Cockpit — Relatório do Estado Atual & Próximos Passos

**Data da Auditoria:** 16 de Setembro de 2026  
**Ambiente de Teste:** Google Chrome DevTools MCP (Navegador Real headless/live)  
**Host do Cockpit:** `http://127.0.0.1:8765`  
**Status dos Testes Automatizados:** **348/348 testes passando (100% OK)**  
**Status das Issues no GitHub:** **0 issues abertas (100% resolvidas e fechadas)**  

---

## 1. Resumo Executivo & Estado Atual do Sistema

O **Agent Cockpit** passou por uma bateria intensiva de estabilização estrutural, governança e ampliação de funcionalidades, culminando na resolução e fechamento de todas as 10 issues que compunham o backlog do repositório:

1. **#19 [Security]**: Eliminação de Path Traversals com resolução canônica segura, mitigação de XSS na UI e proteção contra vazamento de credenciais via CORS.
2. **#20 [State Store]**: Persistência atômica (`.tmp` + `os.replace`), locks multi-processo (`fcntl.flock`) e unificação da raiz de projeto.
3. **#21 [Process Lifecycle]**: Gerenciamento de ciclo de vida do Ollama e PTY com terminação por grupo de processos (`os.killpg`) e verificação ativa de liberação de portas TCP.
4. **#22 [Worker Queue & MCP]**: Fila FIFO de inferência local compartilhada entre processos, observabilidade em tempo real e notificações síncronas via `threading.Condition`.
5. **#23 [Frontend/Architecture]**: Limpeza de código legado, buffer circular de logs com deduplicação e prevenção de duplo POST em trocas de aba.
6. **#14 [Settings/OmniRoute]**: Detecção automática de credenciais do OpenCode (`~/.config/opencode/opencode.jsonc`) e rotas de status/conectores enriquecidas.
7. **#15 [Local Worker/GPU]**: Integração direta com a API do Hugging Face Hub, busca de modelos GGUF com tags de quantização (Q4_K_M, Q8_0, etc.) e pipeline de download.
8. **#16 [Customizations & MCP]**: Central de gerenciamento de servidores MCP (Stdio e SSE) e diretrizes de Skills no diretório de AppData do usuário.
9. **#17 [Settings/Projects]**: Configurações desacopladas por projeto (`.cockpit/config.json`) com suporte a herança de padrões globais e overrides individuais.
10. **#18 [OpenCode/Multi-Agent]**: Motor headless do OpenCode em background, interpretador visual de chat integrado e abas dedicadas e isoladas no workspace para subagentes.

---

## 2. Validação Interativa no Navegador (Funcionalidade por Funcionalidade)

Utilizando a integração com o **Chrome DevTools Protocol (MCP)**, realizamos uma validação funcional ponta a ponta simulando o usuário final em um navegador real conectado à instância viva do servidor local:

| Componente / Funcionalidade | Cenário Testado | Resultado | Detalhes & Evidências |
| :--- | :--- | :---: | :--- |
| **Console & Rede** | Carregamento inicial da SPA | ✅ **APROVADO** | Zero erros no console JavaScript (`0 errors`). Rota 404 de detecção do OpenCode corrigida com criação do alias `/api/opencode/detect`. |
| **OpenCode Visual Chat (#18)** | Clique em `+ Novo Terminal` > `Chat Visual (OpenCode)` | ✅ **APROVADO** | Container flutuante abre com transição suave, exibe badge `READY`, mensagem de boas-vindas do OpenCode Engine e caixa de texto responsiva. Fechamento via `✕` funciona perfeitamente. |
| **Abas Dedicadas de Subagentes (#18)** | Criação dinâmica de abas de Builder e Critic | ✅ **APROVADO** | Subagentes renderizados com badges de status (`RUNNING`, `COMPLETED`), ícones semânticos (`🤖 [Builder]`, `🧐 [Critic]`) e terminal contextual isolado. |
| **Local Worker & GPU (#22)** | Visualização de status da GPU e Fila FIFO | ✅ **APROVADO** | Exibe aceleração GPU (Vulkan/ROCm), status do Ollama (Parado/Ativo), modelo selecionado e monitor da fila FIFO (LIVRE, 0 na fila). |
| **Hugging Face Hub (#15)** | Busca no catálogo de modelos GGUF | ✅ **APROVADO** | Consulta live para `Qwen2.5-Coder` retornou 20 modelos reais do HF Hub em tempo recorde, exibindo contadores de downloads, curtidas e autor. |
| **Gerenciador de MCPs (#16)** | Aba Customizations & MCP em Settings | ✅ **APROVADO** | Exibição limpa de lista vazia quando nenhum MCP está configurado (eliminado bug visual que tratava chaves JSON como cards). Formulário de cadastro de Stdio/SSE abre e fecha com validações. |
| **Configurações por Projeto (#17)** | Seleção de projeto na barra lateral de Settings | ✅ **APROVADO** | O painel `#ag-panel-project-settings` abre com o projeto selecionado (`bruno`), indica status `HERDADO (100% Padrão Geral)` e permite configurar overrides individuais. |
| **Navegação Geral da Aplicação** | Alternância entre abas principais | ✅ **APROVADO** | Todas as 5 visões (`view-flow`, `view-graph`, `view-gauntlet`, `view-handoff`, `view-terminal`) renderizam seu conteúdo sem engasgos ou duplicidades. |
| **Modal de Terminais Ativos** | Abertura via botão `Terminais Ativos (N)` | ✅ **APROVADO** | Listagem correta de todos os terminais instanciados com botões de alternância de visibilidade e backdrop com fechamento ao clique externo. |

---

## 3. Auditoria Detalhada de Usabilidade (UX/UI & Experiência do Desenvolvedor)

Durante a navegação profunda e análise da árvore de acessibilidade no navegador, foram identificados pontos que podem elevar o Agent Cockpit ao patamar de excelência em usabilidade:

### 🟡 1. Naming & Identificação de Projetos ("Projeto Sem Nome")
* **Problema Encontrado:** Na barra lateral de workspaces e no cabeçalho do file explorer, alguns projetos são listados como `PROJETO SEM NOME` quando não há uma propriedade `name` gravada explicitamente no estado do Cockpit.
* **Impacto na Usabilidade:** O usuário fica em dúvida sobre qual pasta ou repositório aquele workspace representa, precisando inspecionar os arquivos para se localizar.
* **Solução Recomendada:** Implementar um fallback inteligente: se `project.name` for nulo, vazio ou genérico, usar o nome base do diretório físico (ex: `os.path.basename(project_root)`).

### 🟡 2. Descoberta do Hugging Face Hub na Página do Local Worker
* **Problema Encontrado:** O motor de busca no Hugging Face Hub (Issue #15) está alocado dentro do modal `#modal-model-download`. Na página principal da aba `Local Worker`, o usuário visualiza os modelos já baixados e o catálogo fixo do Ollama, mas não há um botão claro convidando o usuário a explorar os milhares de modelos GGUF da comunidade do Hugging Face.
* **Impacto na Usabilidade:** Subutilização de um dos recursos mais poderosos do sistema por falta de affordance visual na view principal.
* **Solução Recomendada:** Adicionar um banner/card de destaque na aba do Local Worker: *"🔍 Procurando um modelo específico? Explore milhares de modelos GGUF no Hugging Face Hub"* com botão direto de abertura da busca.

### 🟡 3. Persistência e Histórico da Conversa do Chat Visual OpenCode
* **Problema Encontrado:** O Chat Visual renderiza as mensagens em memória na sessão da página. Se a janela for recarregada (F5), a conversa do chat é resetada para a saudação inicial, embora a sessão do subagente possa continuar viva no servidor backend.
* **Impacto na Usabilidade:** Perda de contexto visual em caso de reinício da interface web ou troca de dispositivo.
* **Solução Recomendada:** Sincronizar o buffer de mensagens do chat visual com o endpoint `/api/opencode/headless/session/{id}/history`, permitindo que ao reabrir o chat, as mensagens trocadas sejam hidratadas imediatamente.

### 🟢 4. Acessibilidade e Semântica de Formulários (DevTools Issues)
* **Problema Encontrado:** O console do DevTools emitiu avisos sobre 4 campos de entrada (inputs) sem atributo `name` ou `id` vinculados a um `<label for="...">`, e campos de senha de chave API fora de elementos `<form>`.
* **Impacto na Usabilidade:** Dificulta a navegação por teclado para usuários com leitores de tela e impede sugestões inteligentes de gerenciadores de senhas seguros (ex: Bitwarden, 1Password).
* **Solução Recomendada:** Encapsular seções de credenciais em `<form onsubmit="return false;">` e garantir `id` e `name` únicos em todos os inputs.

### 🟢 5. Overflow Horizontal de Abas em Frotas com Muitos Subagentes
* **Problema Encontrado:** Quando uma frota 3x3 de agentes é disparada, são criadas 6 ou mais abas de terminais dedicados (`3 Builders + 3 Critics + Orquestrador`). Em telas com largura menor que 1400px, as abas podem disputar espaço com os botões de ação do workspace (`Zoom`, `Grid`, `Novo Terminal`).
* **Impacto na Usabilidade:** As abas podem ser truncadas ou quebrar o alinhamento dos botões de controle do terminal.
* **Solução Recomendada:** Adicionar uma barra de rolagem horizontal estilizada (`overflow-x: auto`) com botões de navegação lateral (`<` e `>`), ou um agrupador suspenso *"Subagentes da Fatia (6) ▾"*.

---

## 4. Próximos Passos & Roadmap de Implementação

Com base nas conclusões da auditoria, propõe-se o seguinte plano ordenado para a próxima etapa:

### Fase 1: Polimento Imediato de UX (Quick Wins)
1. **Fallback de Nomes de Projetos**: Atualizar `server/project_manager.py` e `web/js/sidebar.js` para garantir que todo workspace tenha como nome padrão o nome da sua pasta raiz.
2. **Atalho de Descoberta do HF Hub**: Incluir botão/chamada visual na página do Local Worker levando diretamente à busca do Hugging Face.
3. **Reforço de Semântica e Acessibilidade**: Adicionar atributos `id`/`name` e tags `<form>` nos inputs de configurações de segurança e credenciais.

### Fase 2: Robustecimento do OpenCode Headless
1. **Persistência de Sessões de Chat**: Armazenar o histórico de interações do chat visual em arquivo leve de estado ou banco local para restauração automática pós-reload.
2. **Streaming em Tempo Real de Pensamento (`Thinking Tokens`)**: Exibir indicador de digitação e expansão automática da aba do subagente ativo quando ele invocar ferramentas de arquivos.

### Fase 3: Telemetria e Dashboard de Métricas
1. **Métricas de Performance da GPU**: Exibir gráfico de consumo de VRAM e velocidade de geração de tokens (tokens/segundo) durante a escrita física de código pelos subagentes Builders.
2. **Exportação de Relatórios de Gauntlet**: Permitir exportar os veredictos dos Harsh Critics em formato PDF ou Markdown consolidado para auditorias externas.

---

> [!TIP]
> O sistema encontra-se plenamente funcional, com estabilidade comprovada tanto em nível de backend quanto na interface web. Todas as funcionalidades centrais estão prontas para operação.
