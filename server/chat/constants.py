"""
server/chat/constants.py: Definições de ferramentas disponíveis e prompts de sistema do Zeus.
"""

from typing import Dict, List, Any

DEFAULT_ZEUS_SYSTEM_PROMPT = """Você é o Orquestrador Zeus (Chief Architect & Staff Orchestrator) do Agent Cockpit.
Sua missão é atuar como Arquiteto e Orquestrador Chefe com visão sistêmica, diálogo de alto nível e planejamento estratégico:
1. DIÁLOGO CONVERSACIONAL E PLANEJAMENTO DE ALTO NÍVEL:
   - Atue no nível arquitetural, dialogando com clareza, autoridade e liderança técnica com o Diretor.
   - Para perguntas conceituais, dúvidas sobre o projeto ou saudações (ex: "esse projeto se trata de que?", "como está a integridade do sistema?"), responda diretamente em linguagem natural explicando o propósito, status e arquitetura do Agent Cockpit, sem acionar testes ou subagentes desnecessariamente.
   - Avalie rigorosamente o escopo antes de qualquer execução técnica.
   - Não codificar diretamente no chat principal: NUNCA tente resolver de forma sequencial ou monolítica diretamente no chat. Para tarefas complexas ou que afetam múltiplos arquivos, não codifique diretamente sem delegar.
   - Analise dependências, impactos arquiteturais e decomponha demandas em fatias verticais concisas.
2. FUNCTION CALLING TÁTICO E DESPACHO DE TOOLS:
   - Para implementar recursos, novos subsistemas ou modificar múltiplos arquivos, despache subagentes utilizando `dispatch_subagent`:
     * task_description: Descrição técnica clara do objetivo a ser executado no ambiente isolado.
     * target_slice: Identificador único da fatia vertical (ex: 'slice-auth', 'slice-database').
     * isolation_level: Nível de isolamento ('worktree' para Git Worktree dedicado ou 'shared').
   - Para verificar estabilidade e qualidade técnica, utilize `run_test_suite`:
     * test_target: Caminho ou escopo dos testes (ex: 'all' ou 'tests/test_mod.py').
     * run_mode: Modo de execução ('fast' ou 'standard').
   - Para diagnosticar o andamento global antes de tomar decisões, invoque `read_project_status`.
   - Mantenha suporte ao legado `subagent_spawn` fornecendo slice_id, role (builder ou critic), task e target_files quando aplicável.
3. PADRÃO DE ENGENHARIA LIMPA E COMUNICAÇÃO:
   - Manter alto padrão de engenharia ("Sem gambiarras, sempre encontrando a melhor solução para o problema").
   - Responder sempre em Português do Brasil (PT-BR) de forma técnica, limpa, executiva e assertiva.
   - Limite de leitura pontual: evite inspecionar arquivos inteiros com 'cat' quando buscas pontuais (grep/head) forem suficientes (limite de 3 a 5 por turno).
   - NUNCA encerre seu turno sem emitir uma síntese explicativa completa em Markdown para o usuário: a síntese final textual é obrigatória."""

ZEUS_VOICE_SYSTEM_PROMPT = """Você é o Zeus em diálogo por voz com o Diretor em canal oculto.
Responda sempre em Português do Brasil com fala natural, direta e concisa (máximo 2 a 3 frases curtas).
NUNCA use formatação Markdown, títulos (#), negrito (**), listas de marcadores (-), códigos ou símbolos técnicos.
Para conversas normais, saudações ou dúvidas conceituais sobre o projeto, responda apenas oralmente.
Se o Diretor solicitar uma modificação no código, criação de arquivos, correção de bugs ou testes, responda confirmando oralmente e inclua no final: [ACTION:OPEN_CHAT prompt="descrição técnica da tarefa"]"""

AVAILABLE_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "dispatch_subagent",
            "description": (
                "Despacha um subagente/worker para executar uma tarefa em fatia vertical isolada, "
                "criando automaticamente uma Git Worktree dedicada e enfileirando na WorkerQueue."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Descrição clara e completa da tarefa a ser executada no ambiente isolado."
                    },
                    "target_slice": {
                        "type": "string",
                        "description": "Identificador único da fatia vertical (ex: 'slice-auth', 'slice-database')."
                    },
                    "isolation_level": {
                        "type": "string",
                        "enum": ["worktree", "shared"],
                        "default": "worktree",
                        "description": "Nível de isolamento para a execução: 'worktree' (padrão isolado) ou 'shared'."
                    }
                },
                "required": ["task_description"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_test_suite",
            "description": (
                "Dispara a suíte de testes de forma determinística via test_runner do Cockpit, "
                "retornando resumo destilado com exit_code e eventuais falhas."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "test_target": {
                        "type": "string",
                        "default": "all",
                        "description": "Alvo dos testes ('all' para todos os testes ou caminho específico como 'tests/')."
                    },
                    "run_mode": {
                        "type": "string",
                        "enum": ["fast", "standard", "full"],
                        "default": "fast",
                        "description": "Modo de execução: 'fast' (rápido/otimizado) ou 'standard'."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_project_status",
            "description": (
                "Retorna um sumário estruturado e consolidado do estado do projeto ativo: "
                "épico, fatias, gates de aprovação, pares 3x3 e status da fila de workers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "ID opcional do projeto. Se omitido, retorna o estado do projeto ativo."
                    }
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "subagent_spawn",
            "description": (
                "Despacha um subagente autônomo e especializado (Builder ou Critic) em uma fatia vertical "
                "com workspace/git-worktree isolado para executar tarefas complexas sem poluir o chat principal."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slice_id": {
                        "type": "string",
                        "description": "Identificador único da fatia vertical (ex: 'slice-1', 'slice-auth')."
                    },
                    "task": {
                        "type": "string",
                        "description": "Descrição técnica clara e completa do objetivo do subagente."
                    },
                    "role": {
                        "type": "string",
                        "enum": ["builder", "critic", "code_reviewer", "specialist"],
                        "description": "Papel do subagente: 'builder' ou 'critic'."
                    },
                    "target_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de arquivos ou caminhos que o subagente deve modificar."
                    },
                    "worktree_path": {
                        "type": "string",
                        "description": "Caminho relativo para o Git Worktree isolado da fatia."
                    }
                },
                "required": ["slice_id", "task", "role"]
            }
        }
    }
]

ZEUS_TOOLS = AVAILABLE_TOOLS
