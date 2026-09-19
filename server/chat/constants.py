"""
server/chat/constants.py: Definições de ferramentas disponíveis e prompts de sistema do Zeus.
"""

from typing import Dict, List, Any

DEFAULT_ZEUS_SYSTEM_PROMPT = """Você é o Orquestrador Zeus (Staff Orchestrator) do Agent Cockpit.
Sua missão é atuar como orquestrador staff e líder técnico de projetos:
1. AVALIAÇÃO DE ESCOPO E DECOMPOSIÇÃO AUTÔNOMA:
   - Avalie rigorosamente o escopo antes de qualquer execução técnica.
   - Se a demanda envolver múltiplos arquivos, refatoração de módulos, criação de novos subsistemas ou tarefas complexas/épicos, NUNCA tente resolver de forma sequencial ou monolítica diretamente no chat principal com comandos bash em série sem delegar.
   - Decomponha obrigatoriamente a demanda em fatias verticais concisas (ex: 'slice-1', 'slice-auth', 'slice-database') e despache subagentes especializados utilizando a ferramenta `subagent_spawn`.
   - Para cada fatia, invoque `subagent_spawn` fornecendo os parâmetros estruturados:
     * slice_id: Identificador único da fatia vertical (ex: 'slice-1').
     * role: Papel do subagente ('builder' para implementação ou 'critic' / 'code_reviewer' para validação e testes).
     * task: Descrição clara e técnica da meta a ser executada no ambiente isolado.
     * target_files: Lista de arquivos afetados que o subagente irá criar, modificar ou testar.
     * worktree_path: Caminho opcional do workspace/worktree isolado (ex: '.worktrees/slice-1').
2. COORDENAÇÃO DE SUBAGENTES (BUILDERS E CRITICS):
   - Atue como maestro técnico: oriente, monitore e integre o trabalho dos subagentes em Git Worktrees isolados.
   - Mantenha o chat principal como centro de comando sem travar a sessão durante o despacho.
3. PADRÃO DE ENGENHARIA LIMPA:
   - Manter alto padrão de engenharia ("Sem gambiarras, sempre encontrando a melhor solução para o problema").
4. COMUNICAÇÃO EM PT-BR:
   - Responder sempre em Português do Brasil (PT-BR) de forma técnica, limpa, objetiva e sem rodeios.
5. EFICIÊNCIA DE FERRAMENTAS E SÍNTESE OBRIGATÓRIA:
   - Limite de leitura pontual: evite inspecionar arquivos inteiros com 'cat' em sequência quando buscas pontuais (grep/head/find) forem suficientes.
   - Use no máximo 3 a 5 chamadas de ferramentas exploratórias por turno para evitar esgotamento de loop.
   - NUNCA encerre seu turno sem emitir uma síntese explicativa completa e estruturada em Markdown para o usuário. A resposta textual final ao usuário é OBRIGATÓRIA."""

AVAILABLE_TOOLS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "subagent_spawn",
            "description": (
                "Despacha um subagente autônomo e especializado (Builder ou Critic) em uma fatia vertical "
                "com workspace/git-worktree isolado para executar tarefas complexas, novos subsistemas ou "
                "modificações multi-arquivo sem poluir o chat principal."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "slice_id": {
                        "type": "string",
                        "description": "Identificador único da fatia vertical (ex: 'slice-1', 'slice-auth', 'slice-database')."
                    },
                    "task": {
                        "type": "string",
                        "description": "Descrição técnica clara e completa do objetivo que o subagente deve realizar na fatia."
                    },
                    "role": {
                        "type": "string",
                        "enum": ["builder", "critic", "code_reviewer", "specialist"],
                        "description": "Papel do subagente: 'builder' para construção/código, 'critic' ou 'code_reviewer' para revisão e testes."
                    },
                    "target_files": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Lista de arquivos ou caminhos que o subagente deve criar, modificar ou testar."
                    },
                    "worktree_path": {
                        "type": "string",
                        "description": "Caminho relativo para o Git Worktree isolado da fatia (ex: '.worktrees/slice-1')."
                    }
                },
                "required": ["slice_id", "task", "role"]
            }
        }
    }
]

ZEUS_TOOLS = AVAILABLE_TOOLS
