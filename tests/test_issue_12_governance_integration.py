import unittest
import os
import sys
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE_DIR, "server"))

from state_store import db
from mcp_server import handle_tool_call

class TestIssue12GovernanceIntegration(unittest.TestCase):
    def test_governance_settings_defaults(self):
        gov = db.get_governance_settings()
        self.assertIn("autostart_slices", gov)
        self.assertIn("security_preset", gov)
        self.assertIn("human_gate_policy", gov)
        self.assertIn("artifact_review_policy", gov)

    def test_governance_settings_update(self):
        updated = db.update_governance_settings({
            "autostart_slices": True,
            "security_preset": "turbo",
            "human_gate_policy": "auto"
        })
        self.assertTrue(updated["autostart_slices"])
        self.assertEqual(updated["security_preset"], "turbo")
        self.assertEqual(updated["human_gate_policy"], "auto")

    def test_mcp_check_human_gate_auto(self):
        target_pid = db.resolve_project_id()
        db.update_governance_settings({"human_gate_policy": "auto"}, project_id=target_pid)
        state = db.get_state(target_pid)
        state.setdefault("human_gates", {})["gate_ship_approved"] = False
        state["nodes"] = [
            {"id": "slice-1", "kanban_status": "APPROVED"}
        ]
        state["gauntlet_log"] = [
            {"slice_id": "slice-1", "verdict": "APROVADO"}
        ]
        db._save_state(state, target_pid)

        res = handle_tool_call("check_human_gate", {"gate_name": "gate_ship_approved", "project_id": target_pid})
        content = json.loads(res["content"][0]["text"])
        self.assertTrue(content["approved"])

if __name__ == '__main__':
    unittest.main()
