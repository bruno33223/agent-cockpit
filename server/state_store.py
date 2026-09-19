"""
Fachada de retrocompatibilidade do StateStore para o Agent Cockpit.
Delega internamente para a arquitetura desacoplada em server/storage/.
"""

import os
import sys
from typing import Optional

_SERVER_DIR = os.path.dirname(os.path.abspath(__file__))
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

try:
    from storage import (
        StateFacade,
        canonical_project_id,
        normalize_canonical_path,
        default_initial_state,
    )
except ImportError:
    from server.storage import (
        StateFacade,
        canonical_project_id,
        normalize_canonical_path,
        default_initial_state,
    )

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
STATES_DIR = os.getenv("COCKPIT_STATES_DIR") or os.path.join(BASE_DIR, 'states')
INDEX_FILE = os.path.join(STATES_DIR, 'projects_index.json')
LEGACY_STATE_FILE = os.getenv("COCKPIT_LEGACY_FILE") or os.path.join(BASE_DIR, 'workflow_state.json')


class StateStore(StateFacade):
    """Fachada pública de persistência compatível com a API original do StateStore."""
    def __init__(self, states_dir: Optional[str] = None):
        super().__init__(states_dir=states_dir)


StateStoreFacade = StateStore

db = StateStore()

# Unificação de singleton de módulo: garante paridade entre 'state_store' e 'server.state_store'
if __name__ == "server.state_store":
    sys.modules["state_store"] = sys.modules[__name__]
elif __name__ == "state_store":
    sys.modules["server.state_store"] = sys.modules[__name__]