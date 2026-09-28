"""OMEN: a pre-mortem engine for autonomous coding-agent patches."""

from .engine import OmenEngine, save_report
from .models import Decision, DecisionReport
from .nemotron import NemotronClient

__all__ = ["OmenEngine", "NemotronClient", "Decision", "DecisionReport", "save_report"]
__version__ = "0.1.0"
