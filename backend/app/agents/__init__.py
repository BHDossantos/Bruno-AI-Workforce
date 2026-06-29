"""Daily agents. Each exposes ``run(db) -> dict`` and a cron schedule."""
from .bnbglobal import BnbGlobalAgent
from .ceo_dashboard import CEODashboardAgent
from .commercial_finder import CommercialLeadFinderAgent
from .followup import FollowUpAgent
from .foundation_outreach import FoundationOutreachAgent
from .grant_research import GrantResearchAgent
from .homeowner import HomeownerLeadAgent
from .school_partner import SchoolPartnershipAgent
from .instagram import InstagramAgent
from .insurance import InsuranceAgent
from .job_hunter import JobHunterAgent
from .life_ops import LifeOpsAgent
from .music import MusicAgent
from .music_outreach import CollaborationAgent, MusicPRAgent, SyncLicensingAgent
from .referral_partner import ReferralPartnerAgent
from .review_referral import ReviewReferralAgent
from .savorymind import SavoryMindAgent

# Registry keyed by agent key; order = daily run order.
AGENTS = {
    "job_hunter": JobHunterAgent,
    "insurance": InsuranceAgent,
    # Specialized insurance team (commercial is the priority engine).
    "commercial_finder": CommercialLeadFinderAgent,
    "homeowner": HomeownerLeadAgent,
    "referral_partner": ReferralPartnerAgent,
    "follow_up_agent": FollowUpAgent,
    "review_referral": ReviewReferralAgent,
    "bnbglobal": BnbGlobalAgent,
    "savorymind": SavoryMindAgent,
    "music": MusicAgent,
    "music_pr": MusicPRAgent,
    "music_collab": CollaborationAgent,
    "music_sync": SyncLicensingAgent,
    "instagram": InstagramAgent,
    # Life Commander — personal network nurture.
    "life_ops": LifeOpsAgent,
    # Esposito–Dossantos Foundation.
    "grant_research": GrantResearchAgent,
    "foundation_outreach": FoundationOutreachAgent,
    "school_partner": SchoolPartnershipAgent,
    "ceo_dashboard": CEODashboardAgent,
}

__all__ = ["AGENTS"]
