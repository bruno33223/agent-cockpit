import unittest
import tempfile
import os
import json
import time

from server.state_store import StateStore


class TestIssue20SteeringLegacy(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.states_dir = self.tmpdir.name
        self.legacy_file = os.path.join(self.tmpdir.name, "workflow_state.json")
        self.store = StateStore(states_dir=self.states_dir)
        self.store.legacy_file = self.legacy_file

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_fetch_unconsumed_steering_isolation_per_slice(self):
        """Valida que fetch_unconsumed_steering isola mensagens por fatia e mensagens globais,
        sem marcar indevidamente como consumidas as mensagens de fatias concorrentes."""
        # 1. Cria mensagens destinadas a fatias específicas e uma mensagem global
        self.store.add_user_steering("Direcionamento Slice 1", project_id="test-proj", slice_id="slice-1")
        self.store.add_user_steering("Direcionamento Slice 2", project_id="test-proj", slice_id="slice-2")
        self.store.add_user_steering("Aviso Global", project_id="test-proj", slice_id=None)

        # Fatia 1 consome suas mensagens
        s1_msgs = self.store.fetch_unconsumed_steering(project_id="test-proj", slice_id="slice-1")
        s1_texts = [m["text"] for m in s1_msgs]
        self.assertIn("Direcionamento Slice 1", s1_texts)
        self.assertIn("Aviso Global", s1_texts)
        self.assertNotIn("Direcionamento Slice 2", s1_texts)

        # Fatia 2 consome suas mensagens - NUNCA deve ter sido roubada pela Fatia 1
        s2_msgs = self.store.fetch_unconsumed_steering(project_id="test-proj", slice_id="slice-2")
        s2_texts = [m["text"] for m in s2_msgs]
        self.assertIn("Direcionamento Slice 2", s2_texts)
        self.assertIn("Aviso Global", s2_texts, "Mensagem global deve poder ser consumida por fatias parceiras concorrentes sem roubo")
        self.assertNotIn("Direcionamento Slice 1", s2_texts)

        # Nova busca pela Fatia 1 deve retornar vazia (já consumidas)
        s1_again = self.store.fetch_unconsumed_steering(project_id="test-proj", slice_id="slice-1")
        self.assertEqual(len(s1_again), 0)

        # Nova busca pela Fatia 2 deve retornar vazia (já consumidas)
        s2_again = self.store.fetch_unconsumed_steering(project_id="test-proj", slice_id="slice-2")
        self.assertEqual(len(s2_again), 0)

        # Mensagens de fatia específica não devem ser consumidas por buscas globais (slice_id=None)
        self.store.add_user_steering("Mensagem Slice 3 Exclusiva", project_id="test-proj", slice_id="slice-3")
        global_fetch = self.store.fetch_unconsumed_steering(project_id="test-proj", slice_id=None)
        global_texts = [m["text"] for m in global_fetch]
        self.assertNotIn("Mensagem Slice 3 Exclusiva", global_texts, "Busca global não deve consumir mensagens de fatias específicas")

        # Fatia 3 ainda deve receber sua mensagem intacta
        s3_msgs = self.store.fetch_unconsumed_steering(project_id="test-proj", slice_id="slice-3")
        self.assertEqual(len(s3_msgs), 1)
        self.assertEqual(s3_msgs[0]["text"], "Mensagem Slice 3 Exclusiva")

    def test_steering_message_ids_unique_post_prune(self):
        """Valida que IDs de mensagens são únicos e não colidem após prune de contexto."""
        # Adiciona 10 mensagens
        for i in range(1, 11):
            self.store.add_user_steering(f"Mensagem {i}", project_id="test-proj")

        # Executa compactação/prune mantendo apenas as últimas 3
        prune_res = self.store.prune_session_context(
            retain_last_messages=3,
            retain_last_verdicts=3,
            project_id="test-proj"
        )
        self.assertGreater(prune_res.get("pruned_messages_count", 0), 0)

        # Adiciona mais 10 novas mensagens pós-prune
        for i in range(11, 21):
            self.store.add_user_steering(f"Nova Mensagem {i}", project_id="test-proj")

        state = self.store.get_state("test-proj")
        messages = state.get("steering_messages", [])

        ids = [m["id"] for m in messages]
        # Todos os IDs devem ser estritamente únicos
        self.assertEqual(len(ids), len(set(ids)), f"Colisão detectada em IDs de mensagens: {ids}")

    def test_file_watch_loop_does_not_hijack_current_project_id(self):
        """Valida que atualizações no arquivo de estado legado ou sincronizações do watcher
        não alteram o current_project_id do usuário."""
        # 1. Configura projeto ativo do usuário
        user_proj_id = "projeto-usuario-ativo"
        self.store.switch_current_project(user_proj_id)
        self.assertEqual(self.store.get_current_project_id(), user_proj_id)

        # 2. Cria arquivo workflow_state.json legado simulando alteração externa por outro projeto
        legacy_data = {
            "project_root": "/tmp/legacy_external_repo",
            "epic": {"name": "Projeto Legado Externo", "goal": "Legado"},
            "nodes": [],
            "steering_messages": []
        }
        with open(self.legacy_file, "w", encoding="utf-8") as f:
            json.dump(legacy_data, f)

        # 3. Executa sync_from_legacy_if_modified
        synced_pid = self.store.sync_from_legacy_if_modified()
        self.assertIsNotNone(synced_pid)
        self.assertNotEqual(synced_pid, user_proj_id)

        # O current_project_id NÃO deve ter sido alterado (anti-hijacking)
        self.assertEqual(
            self.store.get_current_project_id(),
            user_proj_id,
            "O watcher legado alterou indevidamente o current_project_id do usuário!"
        )


if __name__ == "__main__":
    unittest.main()
