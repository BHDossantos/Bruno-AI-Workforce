"""Bruno's applicant profile — the authoritative answers the Application Autopilot
uses to fill job applications (fields, work-authorization, screening questions,
and common short-answer essays). Identity (name/email/phone/linkedin) is read
from settings so PII stays in config/secrets; everything else lives here.
"""
from __future__ import annotations

from .config import settings

# Structured profile (mirrors the questions on most ATS application forms).
PROFILE: dict = {
    "personal": {
        "full_name": settings.applicant_name, "preferred_name": "Bruno",
        "email": settings.applicant_email, "phone": settings.applicant_phone,
        "linkedin": settings.applicant_linkedin, "github": settings.applicant_github,
        "address": "44 Howe Ln", "city": "Hollis", "state": "New Hampshire",
        "zip": "03049", "country": "United States",
        "current_title": "Head of Site Reliability Engineering",
        "current_employer": "Head of SRE / Cloud Engineering",
        "employment_status": "Open to New Opportunities",
        "available_start_date": "Immediately",
        "years_experience": "18+", "years_leadership": "10+", "years_managing": "10+",
        "direct_reports": "25+", "indirect_reports": "50+",
    },
    "work_authorization": {
        "authorized_us": "Yes", "us_citizen": "Yes", "authorized_any_employer": "Yes",
        "require_sponsorship": "No", "ever_require_sponsorship": "No",
        "hold_work_visa": "No", "permanent_work_authorization": "Yes",
    },
    "preferences": {
        "full_time": "Yes", "contract": "No", "part_time": "No",
        "remote": "Yes", "hybrid": "Yes", "onsite": "Yes",
        "open_to_relocation": "Yes", "open_to_travel": "Yes", "travel_percentage": "Up to 50%",
        "desired_location": "United States",
        "min_salary": "150000", "target_salary": "180000", "ideal_salary": "220000",
        "bonus": "Yes", "equity": "Yes", "commission": "Not Required",
        "current_salary": "Prefer Not to Disclose",
    },
    "education": {
        "highest_degree": "Master's Degree", "mba": "Yes", "bachelors": "Yes",
        "cs_degree": "Yes", "ai_education": "Yes", "ml_education": "Yes", "business_degree": "Yes",
    },
    "eligibility": {
        "background_check": "Yes", "felony": "No", "misdemeanor": "No",
        "pending_charges": "No", "drug_screen": "Yes",
        "drivers_license": "Yes", "reliable_transportation": "Yes", "valid_passport": "Yes",
        "willing_travel_international": "Yes", "security_clearance": "No",
        "eligible_for_clearance": "Yes",
    },
    "eeo": {  # self-ID; only used where a form explicitly asks
        "gender": "Male", "race": "Two or More Races", "veteran": "Not a Protected Veteran",
        "disability": "No", "need_accommodation": "No",
    },
}

# Authoritative answers to the common screening questions (no AI needed for these).
SCREENING: dict = {
    "why_interested": "I'm excited to contribute to a company that values innovation, "
        "engineering excellence, and customer impact — it aligns with my background "
        "building scalable cloud platforms and leading high-performing engineering teams.",
    "authorized_to_work": "Yes",
    "require_sponsorship": "No",
    "open_to_relocation": "Yes",
    "salary_expectation": "$180,000+ (open based on total compensation)",
    "notice_period": "Available immediately",
    "years_of_experience": "18+ years",
}

# Common short-answer / essay responses.
SHORT_ANSWERS: dict = {
    "tell_us_about_yourself": "I am a technology executive with more than 18 years of "
        "experience leading Site Reliability Engineering, Cloud Engineering, Platform "
        "Engineering, DevOps, and Infrastructure organizations. I specialize in building "
        "highly reliable cloud platforms, leading high-performing teams, driving automation "
        "and observability, and partnering with executive leadership to deliver scalable "
        "technology aligned with business goals.",
    "why_should_we_hire_you": "I bring a rare combination of deep technical expertise and "
        "executive leadership. I've built and led high-performing engineering teams, "
        "modernized cloud infrastructure, improved reliability, reduced operational costs "
        "through automation, and partnered with business leaders to deliver measurable outcomes.",
    "greatest_strength": "Building high-performing engineering organizations while improving "
        "reliability, automation, and operational excellence.",
    "greatest_weakness": "I set very high standards for myself and my teams. I've learned to "
        "balance that with effective delegation and coaching to maximize team growth.",
    "leadership_style": "Servant leadership focused on accountability, empowerment, technical "
        "excellence, and continuous improvement.",
    "why_this_company": "The role aligns with my background building scalable cloud platforms "
        "and leading high-performing engineering organizations, at a company that values "
        "innovation and customer impact.",
    "five_year_plan": "Leading a global engineering organization across cloud infrastructure, "
        "platform engineering, AI infrastructure, and operational excellence while mentoring "
        "future engineering leaders and shaping long-term business strategy.",
    "what_motivates_you": "Solving complex engineering challenges, building exceptional teams, "
        "mentoring engineers, and delivering technology that creates measurable business value.",
    "most_proud_of": "Building engineering organizations that consistently deliver reliable, "
        "scalable, automated platforms with a strong culture of ownership and continuous improvement.",
}


def flat_fields() -> dict:
    """Flatten the profile into a single field-name → value map for form filling."""
    out: dict[str, str] = {}
    for section in PROFILE.values():
        for k, v in section.items():
            if v:
                out[k] = str(v)
    return out
