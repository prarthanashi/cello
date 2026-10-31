from datetime import date
from pathlib import Path

from app.catalogue import Scheme, build_catalogue
from app.config import DEFAULT_OFFICIAL_SUFFIXES, PROJECT_ROOT, Settings

TODAY = date(2026, 10, 31)


def make_settings(**over) -> Settings:
    base = dict(ai_api_key=None, ai_model="unset", frontend_origins=("http://localhost:5173",),
                data_path=PROJECT_ROOT / "data" / "schemes.json", documents_path=PROJECT_ROOT / "data" / "documents",
                review_window_days=90, official_domain_suffixes=DEFAULT_OFFICIAL_SUFFIXES)
    base.update(over)
    return Settings(**base)


def raw_scheme(**over) -> dict:
    base = {
        "scheme_id": "test-central-scheme", "name": "Test Central Scheme", "summary": "Synthetic record for tests.",
        "jurisdiction": "central", "state_ut": None, "support_types": ["credit_loan"],
        "eligible_business_types": [], "eligibility_rules": [
            {"field": "business_stage", "operator": "in", "value": ["newly_operating"], "mandatory": True,
             "explanation": "Stage rule."}],
        "required_documents": [], "official_source_urls": ["https://example.gov.in/scheme"],
        "last_verified_at": "2026-10-31", "scheme_status": "active",
    }
    base.update(over)
    return base


def make_scheme(**over) -> Scheme:
    return Scheme.from_dict(raw_scheme(**over))


def profile(**over) -> dict:
    base = {"state_ut": "Tamil Nadu", "district": None, "business_type": "manufacturing",
            "ownership_category": "individual_proprietorship", "business_stage": "newly_operating",
            "assistance_need": ["credit_loan"], "annual_turnover_inr": None, "employee_count": None,
            "registration_status": None}
    base.update(over)
    return base


def catalogue_of(*raws):
    return build_catalogue(list(raws), DEFAULT_OFFICIAL_SUFFIXES)
