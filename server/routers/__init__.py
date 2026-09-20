"""
routers: Pacote de APIRouters modulares do Agent Cockpit Server.
"""

from . import telemetry
from . import settings
from . import omniroute
from . import models
from . import pty
from . import orchestrator
from . import zeus_chat
from . import auth

__all__ = [
    "telemetry",
    "settings",
    "omniroute",
    "models",
    "pty",
    "orchestrator",
    "zeus_chat",
    "auth",
]
