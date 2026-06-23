"""Daily agents. Each exposes ``run(db) -> dict`` and a cron schedule."""
from .ceo_dashboard import CEODashboardAgent
from .instagram import InstagramAgent
from .insurance import InsuranceAgent
from .job_hunter import JobHunterAgent
from .music import MusicAgent
from .savorymind import SavoryMindAgent

# Registry keyed by agent key; order = daily run order.
AGENTS = {
    "job_hunter": JobHunterAgent,
    "insurance": InsuranceAgent,
    "savorymind": SavoryMindAgent,
    "music": MusicAgent,
    "instagram": InstagramAgent,
    "ceo_dashboard": CEODashboardAgent,
}

__all__ = ["AGENTS"]
