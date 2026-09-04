# 🚀 Guia Rápido: Como Instalar e Usar o Agent Cockpit

Bem-vindo ao **Agent Cockpit**! Este pacote transforma a forma como a IA desenvolve código no seu computador, criando um ecossistema offline de **telemetria visual em tempo real**, **grafo de dependências de custo zero** e **orquestração de agentes com testes automatizados**.

---

## ⚡ Instalação em 1 Minuto (Modo 1-Clique)

### Pré-requisito:
- Ter o **Python 3.9+** instalado no computador ([Download Python](https://www.python.org/downloads/)).  
  *(Ao instalar, lembre-se de marcar a caixinha **"Add python.exe to PATH"**)*.

### Passo a Passo:
1. **Extraia o arquivo ZIP** em qualquer pasta de sua preferência (ex: `C:\agent-cockpit` ou na pasta de projetos).
2. Dê **dois cliques** no arquivo:
   👉 **`install.bat`**
3. O instalador vai automaticamente:
   - Instalar as dependências (`FastAPI`, `Uvicorn`, `WebSockets`, `Pydantic`).
   - Configurar o servidor MCP nas configurações da sua IA (Google Antigravity e Claude Desktop).
   - Instalar as skills necessárias (`cockpit`, `spec-orchestrator`, `gauntlet-loop`).

*Pronto! Não precisa digitar nenhum comando complexo no terminal.*

---

## 🖥️ Como Iniciar o Dashboard Visual

Sempre que for programar com a IA e quiser acompanhar tudo na tela:

1. Dê **dois cliques** em:
   👉 **`start_cockpit.bat`**
2. O dashboard abrirá automaticamente no seu navegador em:
   🌐 **http://localhost:8765**

---

## 🤖 Como Usar no Chat da IA (Antigravity ou Claude)

Com o servidor instalado e o dashboard aberto, abra o seu projeto e envie uma mensagem simples para a IA:

```text
Ative a skill /cockpit e orquestre a implementação deste épico usando a skill /spec-orchestrator.
```

### O que vai acontecer na sua tela:
1. **Sincronização da Blueprint:** A IA cria o plano de fatias verticais e os nós aparecem desenhados no dashboard em tempo real.
2. **Monitor da Frota 3x3:** Você verá 3 pares de agentes trabalhando juntos:
   - `Executor 1 ⟷ Revisor 1` (Infraestrutura e Contratos)
   - `Executor 2 ⟷ Revisor 2` (Lógica e Regras de Negócio)
   - `Executor 3 ⟷ Revisor 3` (Interface e Integração)
3. **Micro-Kanban nos Nós:** Conforme os subagentes criam e revisam código, os cartões transitam automaticamente de `Backlog` ➔ `Builder` ➔ `Critic` ➔ `Aprovado`.
4. **Destilador de Testes:** A IA roda os testes do seu projeto e, se houver erro, apenas as linhas exatas da falha são processadas, economizando milhares de tokens.
5. **Aba Code Graph:** Você pode explorar a árvore de arquivos e ver quais componentes se conectam e o impacto de cada alteração.
6. **Chat de Direcionamento Humano:** Se quiser intervir, basta digitar uma mensagem na caixa de chat do próprio Cockpit visual; a IA consumirá a instrução no próximo ciclo!

---

## 🛠️ Resolução de Problemas Comuns

- **"O comando python não foi encontrado":** Reinstale o Python marcando a opção *"Add python.exe to PATH"*.
- **"Porta 8765 já em uso":** O inicializador detecta e reinicia automaticamente instâncias antigas do Cockpit. Se a porta estiver ocupada por outro aplicativo alheio (ex: Docker, PostgreSQL), o Cockpit avisa e **não encerra** o outro programa por segurança. Você pode iniciá-lo em outra porta facilmente com: `python run_cockpit.py --port 8766`.
- **Configuração Manual do MCP (caso use Cursor ou outro cliente):**
  Adicione no seu `mcp_config.json`:
  ```json
  {
    "mcpServers": {
      "agent-cockpit": {
        "command": "python",
        "args": [
          "CAMINHO_COMPLETO_ATE_A_PASTA/agent-cockpit/server/mcp_server.py"
        ]
      }
    }
  }
  ```
