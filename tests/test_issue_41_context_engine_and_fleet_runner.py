import unittest
import os
import sys
import shutil
import tempfile
from typing import Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "server"))

from state_store import StateStore
from context_engine import (
    estimate_tokens,
    TokenBudgetManager,
    truncate_tool_output,
    prune_chat_context,
)
from fleet_runner import GauntletFleetRunner


class TestIssue41ContextEngine(unittest.TestCase):
    def setUp(self):
        self.scratch_dir = tempfile.mkdtemp(prefix="test_scratch_")

    def tearDown(self):
        shutil.rmtree(self.scratch_dir, ignore_errors=True)

    def test_estimate_tokens_various_inputs(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertEqual(estimate_tokens(None), 0)
        
        # Teste com string: ~4 chars por token
        short_text = "hello world"
        tokens = estimate_tokens(short_text)
        self.assertGreater(tokens, 0)
        self.assertLessEqual(tokens, 5)

        long_text = "x" * 1000
        self.assertEqual(estimate_tokens(long_text), 250)

        # Teste com dict e list
        dict_data = {"key": "value", "count": 42}
        self.assertGreater(estimate_tokens(dict_data), 0)

    def test_token_budget_manager_allocations(self):
        mgr = TokenBudgetManager(model_name="opencode/big-pickle")
        self.assertEqual(mgr.get_context_window(), 32768)

        # Suporte a modelos pré-configurados
        self.assertEqual(mgr.get_context_window("claude-3-5-sonnet"), 200000)
        self.assertEqual(mgr.get_context_window("nemotron-3.5"), 4096)
        self.assertEqual(mgr.get_context_window("unknown-model"), 8192)

        # Alocação de orçamento proporcional
        budget = mgr.allocate_budget("opencode/big-pickle")
        self.assertIn("system_prompt", budget)
        self.assertIn("tools", budget)
        self.assertIn("chat_history", budget)
        self.assertIn("reserve", budget)
        total_allocated = budget["system_prompt"] + budget["tools"] + budget["chat_history"] + budget["reserve"]
        self.assertLessEqual(total_allocated, 32768)

    def test_token_budget_manager_usage_monitoring(self):
        mgr = TokenBudgetManager(model_name="nemotron-3.5") # 4096 window
        # 1000 tokens < 60%
        check1 = mgr.check_budget_usage(1000)
        self.assertFalse(check1["near_limit"])
        self.assertFalse(check1["exceeded"])
        self.assertEqual(check1["remaining_tokens"], 3096)

        # 2600 tokens > 60% (2457 tokens é 60%)
        check2 = mgr.check_budget_usage(2600)
        self.assertTrue(check2["near_limit"])
        self.assertFalse(check2["exceeded"])

        # 4500 tokens > 100%
        check3 = mgr.check_budget_usage(4500)
        self.assertTrue(check3["near_limit"])
        self.assertTrue(check3["exceeded"])
        self.assertEqual(check3["remaining_tokens"], 0)

    def test_truncate_tool_output_within_budget(self):
        normal_output = "Build successful. 42 tests passed."
        res = truncate_tool_output(normal_output, max_tokens=2000, scratch_dir=self.scratch_dir)
        self.assertFalse(res["truncated"])
        self.assertEqual(res["content"], normal_output)
        self.assertIsNone(res.get("log_path"))
        self.assertEqual(res["tokens_saved"], 0)

    def test_truncate_tool_output_exceeding_budget(self):
        # 12.000 caracteres (~3.000 tokens) > 500 tokens limite
        large_output = "Line output with detailed tracing\n" * 400
        res = truncate_tool_output(large_output, max_tokens=500, scratch_dir=self.scratch_dir, command_name="pytest")
        
        self.assertTrue(res["truncated"])
        self.assertIn("file://", res["content"])
        self.assertIn("file://", res["file_pointer"])
        self.assertIsNotNone(res["log_path"])
        self.assertTrue(os.path.exists(res["log_path"]))
        
        # O arquivo em disco deve conter o output bruto completo
        with open(res["log_path"], "r", encoding="utf-8") as f:
            saved_content = f.read()
        self.assertEqual(saved_content, large_output)

        # O conteúdo truncado deve ser menor que o original e ter tokens economizados
        self.assertLess(res["tokens"], res["original_tokens"])
        self.assertGreater(res["tokens_saved"], 0)

    def test_prune_chat_context_under_limit(self):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there!"}
        ]
        res = prune_chat_context(messages, max_tokens=1000)
        self.assertFalse(res["pruned"])
        self.assertEqual(len(res["messages"]), 3)
        self.assertEqual(res["tokens_saved"], 0)

    def test_prune_chat_context_exceeding_limit(self):
        # Cria conversa longa com turnos antigos e recentes
        system_msg = {"role": "system", "content": "System prompt com diretrizes rígidas."}
        old_turn_1 = {"role": "user", "content": "Texto longo antigo 1 " * 100}
        old_turn_2 = {"role": "assistant", "content": "Resposta longa antiga 2 " * 100}
        old_turn_3 = {"role": "user", "content": "Texto longo antigo 3 " * 100}
        recent_1 = {"role": "user", "content": "Pergunta recente sobre o status."}
        recent_2 = {"role": "assistant", "content": "Resposta recente sobre a fatia."}

        messages = [system_msg, old_turn_1, old_turn_2, old_turn_3, recent_1, recent_2]
        # Limite baixo para forçar poda
        res = prune_chat_context(messages, max_tokens=200, retain_recent=2)

        self.assertTrue(res["pruned"])
        self.assertGreater(res["tokens_saved"], 0)
        
        pruned_msgs = res["messages"]
        # System prompt preservado na primeira posição
        self.assertEqual(pruned_msgs[0]["role"], "system")
        self.assertEqual(pruned_msgs[0]["content"], system_msg["content"])

        # As 2 mensagens mais recentes foram preservadas intactas no final
        self.assertEqual(pruned_msgs[-2]["content"], recent_1["content"])
        self.assertEqual(pruned_msgs[-1]["content"], recent_2["content"])

        # Mensagens antigas consolidadas em resumo intermediário
        middle_summary = [m for m in pruned_msgs if "[CONTEXT_PRUNED]" in m["content"]]
        self.assertTrue(len(middle_summary) >= 1)


class TestIssue41GauntletFleetRunner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_runner_states_")
        self.store = StateStore(states_dir=self.temp_dir)
        self.project_id = "test-fleet-proj"
        
        # Inicializa épico com 3 fatias
        self.slices = [
            {"id": "slice-1", "title": "Setup Core DB", "acceptance_criteria": "DB criado", "max_attempts": 3},
            {"id": "slice-2", "title": "API Routes", "acceptance_criteria": "Rotas 200 OK", "max_attempts": 3},
            {"id": "slice-3", "title": "Frontend UI", "acceptance_criteria": "Cards visíveis", "max_attempts": 3}
        ]
        self.store.sync_epic("Épico Teste", "Meta Teste", self.slices, project_id=self.project_id)
        self.runner = GauntletFleetRunner(state_facade=self.store)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_step_slice_dag_two_phase_approval(self):
        phase_events = []

        def mock_builder(project_id, slice_id, attempt, spec):
            phase_events.append(("BUILDER", slice_id, attempt))
            return {"patch": "diff --git ...", "files": ["db.py"]}

        def mock_critic(project_id, slice_id, attempt, builder_output, spec):
            phase_events.append(("CRITIC", slice_id, attempt))
            return {
                "verdict": "APROVADO",
                "reason_md": "Todos os critérios atendidos com testes robustos.",
                "review_metrics": {"critical": 0, "important": 0, "minor": 0}
            }

        result = self.runner.step_slice(
            self.project_id,
            "slice-1",
            builder_fn=mock_builder,
            critic_fn=mock_critic
        )

        # Valida execução em 2 tempos
        self.assertEqual(phase_events, [("BUILDER", "slice-1", 1), ("CRITIC", "slice-1", 1)])
        self.assertTrue(result["approved"])
        self.assertEqual(result["verdict"], "APROVADO")

        # Valida atualização no StateFacade
        state = self.store.get_state(self.project_id)
        node1 = next(n for n in state["nodes"] if n["id"] == "slice-1")
        self.assertEqual(node1["kanban_status"], "APPROVED")

        # Gauntlet log deve registrar o veredito
        self.assertEqual(len(state["gauntlet_log"]), 1)
        self.assertEqual(state["gauntlet_log"][0]["slice_id"], "slice-1")
        self.assertEqual(state["gauntlet_log"][0]["verdict"], "APROVADO")

        # Pulse do par 1 deve estar atualizado
        pair1 = next(p for p in state["pairs_3x3"] if p["id"] == 1)
        self.assertEqual(pair1["critic_status"], "APPROVED")

    def test_step_slice_rejection_and_retry(self):
        # 1a tentativa rejeita, 2a tentativa aprova
        attempts_builder = []
        attempts_critic = []

        def mock_builder(project_id, slice_id, attempt, spec):
            attempts_builder.append(attempt)
            return {"patch": f"patch_attempt_{attempt}"}

        def mock_critic(project_id, slice_id, attempt, builder_output, spec):
            attempts_critic.append(attempt)
            if attempt == 1:
                return {
                    "verdict": "REJEITADO",
                    "reason_md": "Faltam testes de borda.",
                    "review_metrics": {"critical": 1, "important": 0, "minor": 0}
                }
            return {
                "verdict": "APROVADO",
                "reason_md": "Testes de borda adicionados.",
                "review_metrics": {"critical": 0, "important": 0, "minor": 0}
            }

        # Passo 1: tentativa 1 (rejeitada)
        res1 = self.runner.step_slice(self.project_id, "slice-2", builder_fn=mock_builder, critic_fn=mock_critic)
        self.assertFalse(res1["approved"])
        self.assertEqual(res1["verdict"], "REJEITADO")
        self.assertEqual(res1["attempt"], 1)

        state1 = self.store.get_state(self.project_id)
        node2 = next(n for n in state1["nodes"] if n["id"] == "slice-2")
        self.assertEqual(node2["kanban_status"], "REJEITADO")
        self.assertEqual(node2["attempt"], 2) # Preparado para próxima tentativa

        # Passo 2: tentativa 2 (aprovada)
        res2 = self.runner.step_slice(self.project_id, "slice-2", builder_fn=mock_builder, critic_fn=mock_critic)
        self.assertTrue(res2["approved"])
        self.assertEqual(res2["verdict"], "APROVADO")
        self.assertEqual(res2["attempt"], 2)

        state2 = self.store.get_state(self.project_id)
        node2_final = next(n for n in state2["nodes"] if n["id"] == "slice-2")
        self.assertEqual(node2_final["kanban_status"], "APPROVED")
        self.assertEqual(len(state2["gauntlet_log"]), 2)

    def test_run_fleet_cycle_3x3_full_autonomous_approval(self):
        def mock_builder(project_id, slice_id, attempt, spec):
            return {"output": f"built {slice_id}"}

        def mock_critic(project_id, slice_id, attempt, builder_output, spec):
            # slice-3 falha na primeira tentativa e passa na segunda
            if slice_id == "slice-3" and attempt == 1:
                return {"verdict": "REJEITADO", "reason_md": "CSS quebrado", "review_metrics": {"critical": 1, "important": 0, "minor": 0}}
            return {"verdict": "APROVADO", "reason_md": "Perfeito", "review_metrics": {"critical": 0, "important": 0, "minor": 0}}

        fleet_result = self.runner.run_fleet_cycle(
            self.project_id,
            max_iterations=5,
            builder_fn=mock_builder,
            critic_fn=mock_critic
        )

        self.assertTrue(fleet_result["all_approved"])
        self.assertEqual(fleet_result["total_slices"], 3)
        self.assertEqual(fleet_result["approved_slices_count"], 3)
        self.assertGreaterEqual(fleet_result["iterations"], 2)

        # Confere persistência no StateStore
        state = self.store.get_state(self.project_id)
        for node in state["nodes"]:
            self.assertEqual(node["kanban_status"], "APPROVED", f"Nó {node['id']} deve estar APPROVED")

        # Todos os pares 3x3 devem estar com critic APPROVED
        for pair in state["pairs_3x3"]:
            self.assertEqual(pair["critic_status"], "APPROVED")


if __name__ == "__main__":
    unittest.main()
