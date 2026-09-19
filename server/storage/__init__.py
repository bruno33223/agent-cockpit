"""
Pacote de persistência e gerenciamento de estado do Agent Cockpit.
Desacoplado em repositórios de Projetos, Fatias, Configurações e Fachada de Estado.
"""

from .project_repository import (
    ProjectRepository,
    canonical_project_id,
    normalize_canonical_path,
    default_initial_state,
)
from .slice_repository import SliceRepository
from .settings_repository import SettingsRepository
from .state_facade import StateFacade

__all__ = [
    "StateFacade",
    "ProjectRepository",
    "SliceRepository",
    "SettingsRepository",
    "canonical_project_id",
    "normalize_canonical_path",
    "default_initial_state",
]
