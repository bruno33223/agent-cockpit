import os
import sys
import shutil
import tempfile
import unittest

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from server.state_store import StateStore


class TestProjectSettingsInheritanceBackend(unittest.TestCase):
    """Testa o modelo de herança de configurações de projeto e isolamento de overrides."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix='cockpit_test_settings_')
        self.store = StateStore(states_dir=self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_get_project_settings_default_inheritance(self):
        """Testa se um projeto novo sem overrides herda 100% dos defaults gerais."""
        settings_info = self.store.get_project_settings("proj-alpha")

        self.assertEqual(settings_info["project_id"], "proj-alpha")
        self.assertEqual(settings_info["overrides"], {})
        self.assertIn("general_defaults", settings_info)
        self.assertIn("effective_settings", settings_info)

        gen_defaults = settings_info["general_defaults"]
        eff = settings_info["effective_settings"]

        # Effective settings deve ser exatamente igual a general_defaults
        self.assertEqual(eff, gen_defaults)

        # Campos obrigatórios de governança e general settings
        self.assertIn("autostart_slices", eff)
        self.assertIn("security_preset", eff)
        self.assertIn("human_gate_policy", eff)
        self.assertIn("artifact_review_policy", eff)
        self.assertIn("enable_local_ai", eff)
        self.assertIn("delegate_styles_to_cloud", eff)
        self.assertIn("model", eff)
        self.assertIn("endpoint", eff)

    def test_inheritance_updates_dynamically_when_general_defaults_change(self):
        """Testa se alterações nos defaults gerais refletem automaticamente em projetos sem override."""
        # Altera defaults gerais via default project
        self.store.update_governance_settings({
            "security_preset": "turbo",
            "autostart_slices": True
        }, project_id="default")
        self.store.update_settings({
            "enable_local_ai": True,
            "model": "qwen2.5-coder:14b"
        }, project_id="default")

        info_alpha = self.store.get_project_settings("proj-alpha")
        eff_alpha = info_alpha["effective_settings"]

        self.assertEqual(eff_alpha["security_preset"], "turbo")
        self.assertTrue(eff_alpha["autostart_slices"])
        self.assertTrue(eff_alpha["enable_local_ai"])
        self.assertEqual(eff_alpha["model"], "qwen2.5-coder:14b")

    def test_set_project_settings_overrides_isolation(self):
        """Testa se overrides em um projeto afetam apenas ele e não tocam outros projetos nem os defaults gerais."""
        # Define overrides pontuais para proj-alpha
        overrides_alpha = {
            "security_preset": "strict",
            "model": "custom-specialist:7b"
        }
        res_alpha = self.store.set_project_settings("proj-alpha", overrides_alpha)

        # Verifica proj-alpha
        self.assertEqual(res_alpha["overrides"], overrides_alpha)
        self.assertEqual(res_alpha["effective_settings"]["security_preset"], "strict")
        self.assertEqual(res_alpha["effective_settings"]["model"], "custom-specialist:7b")
        # Chaves não sobrescritas devem continuar herdadas de General
        self.assertEqual(
            res_alpha["effective_settings"]["human_gate_policy"],
            res_alpha["general_defaults"]["human_gate_policy"]
        )

        # Verifica que proj-beta NÃO foi afetado
        info_beta = self.store.get_project_settings("proj-beta")
        self.assertEqual(info_beta["overrides"], {})
        self.assertNotEqual(info_beta["effective_settings"]["security_preset"], "strict")
        self.assertNotEqual(info_beta["effective_settings"]["model"], "custom-specialist:7b")
        self.assertEqual(
            info_beta["effective_settings"]["security_preset"],
            info_beta["general_defaults"]["security_preset"]
        )

        # Verifica que os defaults de General (default) continuam intactos
        gen_defaults = self.store.get_general_defaults()
        self.assertNotEqual(gen_defaults["security_preset"], "strict")
        self.assertNotEqual(gen_defaults["model"], "custom-specialist:7b")

    def test_clear_project_settings_overrides(self):
        """Testa se clear_project_settings_overrides limpa todos os overrides e volta a herdar 100% de General."""
        self.store.set_project_settings("proj-alpha", {
            "security_preset": "strict",
            "enable_local_ai": True,
            "artifact_review_policy": "lenient"
        })

        info_before = self.store.get_project_settings("proj-alpha")
        self.assertTrue(len(info_before["overrides"]) > 0)
        self.assertNotEqual(info_before["effective_settings"], info_before["general_defaults"])

        # Limpa overrides
        res_cleared = self.store.clear_project_settings_overrides("proj-alpha")

        self.assertEqual(res_cleared["overrides"], {})
        self.assertEqual(res_cleared["effective_settings"], res_cleared["general_defaults"])

        # Consulta subsequente também deve confirmar 100% de herança
        info_after = self.store.get_project_settings("proj-alpha")
        self.assertEqual(info_after["overrides"], {})
        self.assertEqual(info_after["effective_settings"], info_after["general_defaults"])

    def test_partial_override_updates_and_single_key_removal(self):
        """Testa atualização cumulativa de overrides e remoção pontual via None."""
        self.store.set_project_settings("proj-alpha", {
            "security_preset": "turbo",
            "model": "model-v1"
        })

        # Atualização cumulativa
        self.store.set_project_settings("proj-alpha", {
            "model": "model-v2"
        })
        info = self.store.get_project_settings("proj-alpha")
        self.assertEqual(info["overrides"]["security_preset"], "turbo")
        self.assertEqual(info["overrides"]["model"], "model-v2")

        # Remoção de chave única passando None
        self.store.set_project_settings("proj-alpha", {
            "security_preset": None
        })
        info_updated = self.store.get_project_settings("proj-alpha")
        self.assertNotIn("security_preset", info_updated["overrides"])
        self.assertEqual(info_updated["overrides"]["model"], "model-v2")
        self.assertEqual(
            info_updated["effective_settings"]["security_preset"],
            info_updated["general_defaults"]["security_preset"]
        )

    def test_preservation_across_reset_project(self):
        """Testa se overrides de configurações são preservados durante reset_project."""
        self.store.set_project_settings("proj-alpha", {
            "security_preset": "strict"
        })

        # Executa reset do projeto
        self.store.reset_project("proj-alpha")

        info_after_reset = self.store.get_project_settings("proj-alpha")
        self.assertEqual(info_after_reset["overrides"], {"security_preset": "strict"})
        self.assertEqual(info_after_reset["effective_settings"]["security_preset"], "strict")


if __name__ == '__main__':
    unittest.main()
