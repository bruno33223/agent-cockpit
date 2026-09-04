---
name: gauntlet-loop
description: Executa o padrão Gauntlet Loop (Builder vs Harsh Critic) contra uma barra de qualidade real com limite controlado de iterações. Use quando o usuário pedir para criar algo com alta qualidade, rodar em loop ou iterar até a perfeição.
---

# Gauntlet Loop para Antigravity

Quando acionado, você atua **estritamente como o Agente Orquestrador**. Você não executa tarefas diretamente nem queima janela de contexto no chat principal com implementações extensas. Sua função é governar a execução adversária delegando o trabalho prático e as avaliações para uma **frota dinâmica de subagentes especializados**.

---

## 1. Modelo Mental: Escopo vs. Loop Adversário

É fundamental não confundir etapas de projeto com iterações de qualidade:

- **Unidade de Escopo (Deliverable / Fatia Vertical):**
  - Representa cada módulo, sistema, funcionalidade ou conteúdo independente solicitado (ex.: se o usuário pede 5 novos sistemas, existem 5 fatias verticais: Sistema 1, Sistema 2, ..., Sistema 5).
- **Ciclo Gauntlet (Inner Loop de Refinamento Adversário):**
  - Ocorre **dentro de cada Unidade de Escopo**.
  - É a dinâmica iterativa: `Builder -> Critic -> Rejeição -> Builder -> Critic -> Aprovação`.
  - O limite de 3 a 5 iterações (tentativas) aplica-se **por unidade de escopo**, e **NUNCA** como uma lista linear ou fases horizontais do projeto.

> [!CAUTION]
> **PROIBIDA A DECOMPOSIÇÃO HORIZONTAL (ANTI-WATERFALL)**
> Nunca fatie o projeto em fases técnicas abstratas (ex.: "Fase 1: Design/Arquitetura, Fase 2: Código, Fase 3: Gráficos, Fase 4: Revisão, Fase 5: Fechamento"). O projeto deve ser decomposto **exclusivamente em Fatias Verticais (Vertical Slices)**, onde cada unidade é entregue 100% funcional (código, lógica, visual e testes prontos de ponta a ponta) antes de avançar para a próxima.

---

## 2. Divisão de Papéis e Dimensionamento da Frota

- **Orquestrador (Agente Principal):**
  - Maestro e controlador do fluxo. Mantém o contexto do chat enxuto.
  - Avalia o escopo e aciona a **quantidade exata de subagentes necessários** via `invoke_subagent` (sem se limitar a apenas um ou dois).
  - Atualiza rigorosamente o `GAUNTLET_LOG.md` no disco do workspace a cada rodada.
  - Interrompe o processo se o limite de iterações de uma unidade for atingido sem aprovação.
- **Pool de Subagentes Executores (Builders Especializados):**
  - Instanciados pelo Orquestrador conforme a demanda técnica (ex.: Builder de Engenharia/Lógica, Builder de UI/Assets, Builder de Testes).
  - Têm ferramentas de escrita habilitadas (`enable_write_tools: true`).
  - Constroem a fatia vertical completa e resolvem os apontamentos dos críticos nas iterações seguintes.
- **Pool de Subagentes Auditores (Harsh Critics Especializados):**
  - Instanciados com contexto limpo (*fresh context*) para total independência e eliminação de viés.
  - Especialistas nas dimensões da barra de qualidade (ex.: Crítico de Arquitetura, Crítico de UI/Estética, Crítico de Performance/Segurança).
  - Fazem comparação cega contra a referência e emitem parecer binário inequívoco: **APROVADO** ou **REJEITADO**, listando defeitos com rigor impiedoso.
  - **Auditoria Arquitetural Objetiva:** Em tarefas de código, a avaliação técnica audita estritamente contra o contrato da especificação/blueprint (testes automatizados 100% verdes, conformidade com KISS sem over-engineering, isolamento de domínio/SOLID e cumprimento estrito aos file locks).

---

## 3. Fluxo de Execução

### Passo 1: Definição da Barra de Qualidade (Quality Bar)
- Obtenha ou exija do usuário uma referência concreta, verificável e comparável (ex.: código de referência, repositório modelo, screenshot de interface padrão-ouro, suite de testes de aceitação).
- Para tarefas de software, a Barra de Qualidade deriva da especificação técnica e arquitetural (ex.: `MASTER_BLUEPRINT.md` do Orquestrador com diretrizes explícitas de KISS, Clean Architecture, SOLID e testes).
- Rejeite termos subjetivos como "bom acabamento", "código limpo" ou "design moderno".

### Passo 2: Decomposição em Fatias Verticais e Inicialização do Log
- Decomponha o pedido em $N$ Entregáveis / Fatias Verticais completas e independentes.
- Crie imediatamente o arquivo `GAUNTLET_LOG.md` na raiz do workspace com a estrutura padronizada.
- *Dica de escala:* Se o projeto for extenso ou demandar múltiplos subsistemas simultâneos, recomende ao usuário acionar o `/teamwork-preview` para habilitar a colaboração multiagente nativa.

### Passo 3: Execução do Gauntlet por Fatia Vertical (Inner Loop)
Para cada **Entregável $k$**:
1. **Tentativa $i$ (iniciando em 1 até o limite de 3 a 5):**
   - **Execução:** O Orquestrador despacha os Builders necessários para implementar ou refatorar a fatia vertical completa.
   - **Auditoria:** O Orquestrador despacha os Harsh Critics necessários com contexto limpo para auditar a entrega contra a barra de qualidade.
   - **Veredito:**
     - Se **APROVADO** por todos os críticos: registre no `GAUNTLET_LOG.md` como `Status: CONCLUÍDO` e passe para o próximo Entregável.
     - Se **REJEITADO**: registre o motivo técnico no `GAUNTLET_LOG.md`, incremente a Tentativa ($i+1$) e despache os Builders com o feedback do Critic. Se o problema exigir raciocínio aprofundado ou refinamento sutil, recomende ao usuário o comando `/boost`.
2. **Controle de Limites (Safety & Credit Bounds):**
   - Se atingir o limite estipulado (padrão: 3 a 5 tentativas) sem aprovação do Critic, **pause imediatamente**, apresente o relatório ao usuário no chat e peça autorização antes de gastar novos ciclos.

### Passo 4: Auditoria de Integração Final
- Quando todas as fatias verticais estiverem marcadas como `CONCLUÍDO`, dispare um subagente auditor de integração global para checar consistência, ausência de regressões e harmonia entre os módulos.

---

## 4. Padrão Obrigatório do `GAUNTLET_LOG.md`

O estado e histórico do Gauntlet devem ser mantidos exclusivamente no disco do workspace para manter a janela de contexto limpa e econômica. O Orquestrador deve manter o arquivo `GAUNTLET_LOG.md` exatamente neste formato estruturado:

```markdown
# GAUNTLET LOG

## Entregável 1: [Nome da Fatia Vertical / Recurso Completo]
- Tentativa 1: [Builder executou X] -> Critic: REJEITADO (Motivo: [falhas apontadas em relação à barra de qualidade])
- Tentativa 2: [Builder corrigiu Y] -> Critic: APROVADO (Notas / Validação)
- Status: CONCLUÍDO

## Entregável 2: [Nome da Fatia Vertical / Recurso Completo]
- Tentativa 1: [Builder executou Z] -> Critic: REJEITADO (Motivo: ...)
- Tentativa 2: [Builder corrigiu W] -> Critic: Em avaliação...
- Status: EM ANDAMENTO (Tentativa 2/5)
```

---

## 5. Sinergia com Slash Commands (`/boost` e `/teamwork-preview`)

O Gauntlet Loop se potencializa com comandos nativos do Antigravity. O Orquestrador deve recomendar ao usuário o acionamento desses comandos nos seguintes cenários:

- **`/teamwork-preview` (Equipes de Agentes Autônomos):**
  - **Quando sugerir:** Quando o escopo envolver múltiplos entregáveis grandes, sistemas concorrentes ou fatias verticais independentes que se beneficiem de agentes autônomos colaborando em paralelo.
  - **Como usar:** Sugira ao usuário iniciar a sessão ou etapa com `/teamwork-preview` para maximizar o paralelismo e a distribuição entre Builders e Critics.

- **`/boost` (Raciocínio Profundo e Verificação Rigorosa):**
  - **Quando sugerir:** Em entregáveis de alta complexidade matemática, lógica algorítmica densa, arquiteturas críticas ou quando o ciclo do Gauntlet sofrer rejeições sucessivas difíceis de sanar.
  - **Como usar:** Sugira ao usuário ativar o `/boost` para aplicar planejamento estratégico multifacetado, pensamento profundo e validações rigorosas antes de submeter à crítica.
