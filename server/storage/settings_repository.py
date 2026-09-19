import os
import time
from typing import Dict, Any, Optional

class SettingsRepository:
    """Gerencia configurações gerais, governança, human gates, handoffs e estado do local worker."""
    def __init__(self, facade: Any):
        self.facade = facade

    @property
    def lock(self):
        return self.facade.lock

    def approve_gate(self, gate_name: str, approved_by: str = "user", project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            gates = state.setdefault("human_gates", {})
            gates[gate_name] = True
            gates["last_approved_at"] = time.strftime("%H:%M:%S")
            gates["approved_by"] = approved_by
            self.facade._save_state(state, target_pid)
        self.facade._notify("GATE_APPROVED", {"gate": gate_name, "approved_by": approved_by}, target_pid)
        self.facade._notify("STATE_FULL", state, target_pid)
        return {"status": "APPROVED", "gate": gate_name, "approved_by": approved_by, "project_id": target_pid}

    def get_gate_status(self, gate_name: str, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            gates = state.get("human_gates", {})
            return {
                "gate": gate_name, "approved": bool(gates.get(gate_name, False)),
                "last_approved_at": gates.get("last_approved_at"),
                "approved_by": gates.get("approved_by"), "project_id": target_pid
            }

    def get_governance_settings(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            gov = state.get("governance_settings")
            if not gov:
                gov = {"autostart_slices": False, "security_preset": "standard", "human_gate_policy": "manual", "artifact_review_policy": "strict"}
                state["governance_settings"] = gov
                self.facade._save_state(state, target_pid)
            return dict(gov)

    def update_governance_settings(self, updates: Dict[str, Any], project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            gov = state.setdefault("governance_settings", {"autostart_slices": False, "security_preset": "standard", "human_gate_policy": "manual", "artifact_review_policy": "strict"})
            gov.update(updates)
            self.facade._save_state(state, target_pid)
        self.facade._notify("GOVERNANCE_SETTINGS_UPDATED", gov, target_pid)
        self.facade._notify("STATE_FULL", state, target_pid)
        return dict(gov)

    def set_last_handoff(self, handoff_meta: Dict[str, Any], project_id: Optional[str] = None):
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            state["last_handoff"] = handoff_meta
            self.facade._save_state(state, target_pid)
        self.facade._notify("HANDOFF_UPDATED", handoff_meta, target_pid)
        self.facade._notify("STATE_FULL", state, target_pid)

    def get_last_handoff(self, project_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.facade.get_state(self.facade.resolve_project_id(project_id)).get("last_handoff")

    def get_settings(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            cfg = state.setdefault("local_worker", {})
            st = state.setdefault("settings", {})
            return {
                "enable_local_ai": bool(st.get("enable_local_ai", cfg.get("enabled", False))),
                "delegate_styles_to_cloud": bool(st.get("delegate_styles_to_cloud", cfg.get("delegate_styles_to_cloud", True))),
                "model": cfg.get("model", "deepseek-coder-v2:16b-q3_k_m"),
                "endpoint": cfg.get("endpoint", "http://127.0.0.1:11434"),
                "auto_start_ollama": cfg.get("auto_start_ollama", False),
                "circuit_breaker_threshold": cfg.get("circuit_breaker_threshold", 2),
                "project_root": state.get("project_root")
            }

    def update_settings(self, updates: Dict[str, Any], project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            cfg, st = state.setdefault("local_worker", {}), state.setdefault("settings", {})
            if "enable_local_ai" in updates:
                v = bool(updates["enable_local_ai"])
                st["enable_local_ai"], cfg["enabled"] = v, v
            if "delegate_styles_to_cloud" in updates:
                v = bool(updates["delegate_styles_to_cloud"])
                st["delegate_styles_to_cloud"], cfg["delegate_styles_to_cloud"] = v, v
            if updates.get("model"):
                cfg["model"] = str(updates["model"]).strip()
            if "auto_start_ollama" in updates:
                cfg["auto_start_ollama"] = bool(updates["auto_start_ollama"])
            if "circuit_breaker_threshold" in updates:
                cfg["circuit_breaker_threshold"] = int(updates["circuit_breaker_threshold"])
            if updates.get("project_root"):
                state["project_root"] = os.path.abspath(updates["project_root"])
            self.facade._save_state(state, target_pid)
        updated = self.get_settings(project_id=target_pid)
        self.facade._notify("SETTINGS_UPDATED", updated, target_pid)
        self.facade._notify("LOCAL_WORKER_CONFIG_UPDATED", cfg, target_pid)
        self.facade._notify("STATE_FULL", state, target_pid)
        return updated

    def get_general_defaults(self) -> Dict[str, Any]:
        gov = self.get_governance_settings("default")
        st = self.get_settings("default")
        return {
            "autostart_slices": bool(gov.get("autostart_slices", False)),
            "security_preset": str(gov.get("security_preset", "standard")),
            "human_gate_policy": str(gov.get("human_gate_policy", "manual")),
            "artifact_review_policy": str(gov.get("artifact_review_policy", "strict")),
            "enable_local_ai": bool(st.get("enable_local_ai", False)),
            "delegate_styles_to_cloud": bool(st.get("delegate_styles_to_cloud", True)),
            "model": str(st.get("model", "deepseek-coder-v2:16b-q3_k_m")),
            "endpoint": str(st.get("endpoint", "http://127.0.0.1:11434")),
            "auto_start_ollama": bool(st.get("auto_start_ollama", False)),
            "circuit_breaker_threshold": int(st.get("circuit_breaker_threshold", 2)),
        }

    def get_project_settings(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            raw = state.get("project_settings_overrides")
            overrides = dict(raw) if isinstance(raw, dict) else {}
            gen_defaults = self.get_general_defaults()
            effective = dict(gen_defaults)
            for k, v in overrides.items():
                if v is not None:
                    effective[k] = v
            return {"project_id": target_pid, "overrides": overrides, "general_defaults": gen_defaults, "effective_settings": effective}

    def set_project_settings(self, project_id: Optional[str], overrides: Dict[str, Any]) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            curr = state.setdefault("project_settings_overrides", {})
            for k, v in overrides.items():
                if v is None:
                    curr.pop(k, None)
                else:
                    curr[k] = v
            self.facade._save_state(state, target_pid)
            result = self.get_project_settings(project_id=target_pid)
        self.facade._notify("PROJECT_SETTINGS_UPDATED", result, target_pid)
        self.facade._notify("STATE_FULL", state, target_pid)
        return result

    def clear_project_settings_overrides(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            state["project_settings_overrides"] = {}
            self.facade._save_state(state, target_pid)
            result = self.get_project_settings(project_id=target_pid)
        self.facade._notify("PROJECT_SETTINGS_UPDATED", result, target_pid)
        self.facade._notify("STATE_FULL", state, target_pid)
        return result

    def get_local_worker_config(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            cfg = state.setdefault("local_worker", {})
            cfg.setdefault("enabled", False)
            cfg.setdefault("provider", "ollama")
            cfg.setdefault("endpoint", "http://127.0.0.1:11434")
            cfg.setdefault("model", "deepseek-coder-v2:16b-q3_k_m")
            cfg.setdefault("circuit_breaker_threshold", 2)
            cfg.setdefault("consecutive_failures", {})
            cfg.setdefault("auto_start_ollama", False)
            if "delegate_styles_to_cloud" not in cfg:
                cfg["delegate_styles_to_cloud"] = state.get("settings", {}).get("delegate_styles_to_cloud", True)
            return dict(cfg)

    def set_local_worker_config(self, updates: Dict[str, Any], project_id: Optional[str] = None) -> Dict[str, Any]:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            cfg = state.setdefault("local_worker", {})
            cfg.setdefault("enabled", False)
            cfg.setdefault("provider", "ollama")
            cfg.setdefault("endpoint", "http://127.0.0.1:11434")
            cfg.setdefault("model", "deepseek-coder-v2:16b-q3_k_m")
            cfg.setdefault("circuit_breaker_threshold", 2)
            cfg.setdefault("consecutive_failures", {})
            cfg.setdefault("auto_start_ollama", False)
            cfg.setdefault("delegate_styles_to_cloud", True)
            cfg.update(updates)
            if "enabled" in updates:
                state.setdefault("settings", {})["enable_local_ai"] = bool(updates["enabled"])
            if "delegate_styles_to_cloud" in updates:
                state.setdefault("settings", {})["delegate_styles_to_cloud"] = bool(updates["delegate_styles_to_cloud"])
            self.facade._save_state(state, target_pid)
        self.facade._notify("LOCAL_WORKER_CONFIG_UPDATED", cfg, target_pid)
        self.facade._notify("STATE_FULL", state, target_pid)
        return dict(cfg)

    def update_local_worker_config(self, updates: Dict[str, Any], project_id: Optional[str] = None) -> Dict[str, Any]:
        return self.set_local_worker_config(updates, project_id=project_id)

    def get_local_worker_attempts(self, slice_id: str, project_id: Optional[str] = None) -> int:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            cfg = self.facade.get_state(target_pid).setdefault("local_worker", {"provider": "ollama", "endpoint": "http://127.0.0.1:11434", "model": "qwen2.5-coder:7b-instruct-q4_k_m", "circuit_breaker_threshold": 2, "consecutive_failures": {}})
            return int(cfg.setdefault("consecutive_failures", {}).get(slice_id, 0))

    def increment_local_worker_attempts(self, slice_id: str, project_id: Optional[str] = None) -> int:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            cfg = state.setdefault("local_worker", {"provider": "ollama", "endpoint": "http://127.0.0.1:11434", "model": "qwen2.5-coder:7b-instruct-q4_k_m", "circuit_breaker_threshold": 2, "consecutive_failures": {}})
            failures = cfg.setdefault("consecutive_failures", {})
            failures[slice_id] = int(failures.get(slice_id, 0)) + 1
            val = failures[slice_id]
            self.facade._save_state(state, target_pid)
        self.facade._notify("LOCAL_WORKER_ATTEMPTS_UPDATED", {"slice_id": slice_id, "attempts": val}, target_pid)
        return val

    def reset_local_worker_attempts(self, slice_id: str, project_id: Optional[str] = None) -> None:
        target_pid = self.facade.resolve_project_id(project_id)
        with self.lock:
            state = self.facade.get_state(target_pid)
            cfg = state.setdefault("local_worker", {"provider": "ollama", "endpoint": "http://127.0.0.1:11434", "model": "qwen2.5-coder:7b-instruct-q4_k_m", "circuit_breaker_threshold": 2, "consecutive_failures": {}})
            cfg.setdefault("consecutive_failures", {})[slice_id] = 0
            self.facade._save_state(state, target_pid)
        self.facade._notify("LOCAL_WORKER_ATTEMPTS_RESET", {"slice_id": slice_id}, target_pid)

    def get_circuit_breaker_count(self, slice_id: str, project_id: Optional[str] = None) -> int:
        return self.get_local_worker_attempts(slice_id, project_id=project_id)

    def increment_circuit_breaker(self, slice_id: str, project_id: Optional[str] = None) -> int:
        return self.increment_local_worker_attempts(slice_id, project_id=project_id)

    def reset_circuit_breaker(self, slice_id: str, project_id: Optional[str] = None) -> None:
        self.reset_local_worker_attempts(slice_id, project_id=project_id)
