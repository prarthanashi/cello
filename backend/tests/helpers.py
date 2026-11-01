from datetime import date

from app.catalogue import Scheme, build_catalogue
from app.config import DEFAULT_OFFICIAL_SUFFIXES, Settings

TODAY = date(2026, 10, 31)


def make_settings(**over) -> Settings:
    base = dict(ai_api_key=None, ai_model="unset", frontend_origins=("http://localhost:5173",),
                supabase_url=None, supabase_secret_key=None,
                review_window_days=90, official_domain_suffixes=DEFAULT_OFFICIAL_SUFFIXES)
    base.update(over)
    return Settings(**base)


def raw_scheme(**over) -> dict:
    base = {
        "scheme_id": "test-central-scheme", "name": "Test Central Scheme", "summary": "Synthetic record for tests.",
        "jurisdiction": "central", "state_ut": None, "support_types": ["credit_loan"],
        "eligible_business_types": [], "eligibility_rules": [
            {"field": "business_stage", "operator": "in", "value": ["newly_operating"], "mandatory": True,
             "explanation": "Stage rule.", "source_excerpt": "Stage rule."}],
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


def api_catalogue():
    stage_rule = {
        "field": "business_stage", "operator": "in",
        "value": ["idea_pre_launch", "newly_operating"], "mandatory": True,
        "explanation": "Applicants must be setting up or newly operating a business.",
        "source_excerpt": "Applicants must be setting up or newly operating a business.",
    }
    ownership_rule = {
        "field": "ownership_category", "operator": "in",
        "value": ["individual_proprietorship", "partnership"], "mandatory": True,
        "explanation": "The applicant must use an eligible business structure.",
        "source_excerpt": "The applicant must use an eligible business structure.",
    }
    return catalogue_of(
        raw_scheme(
            scheme_id="test-central-grant", name="Central Example Grant",
            summary="Example central assistance for a new small business.",
            support_types=["credit_loan", "subsidy_grant"],
            eligible_business_types=["food_processing"],
            eligibility_rules=[stage_rule],
            benefits=["Example grant benefit."],
            exclusions=["Existing businesses are excluded."],
            application_steps=["Submit an application online."],
            required_documents=[{"name": "Project proposal", "requirement_type": "required", "notes": ""}],
            source_title="Central Example Grant source",
        ),
        raw_scheme(
            scheme_id="test-central-loan", name="Central Example Loan",
            summary="Example central credit support for small businesses.",
            support_types=["credit_loan"],
            eligibility_rules=[stage_rule, ownership_rule],
            required_documents=[
                {"name": "Identity document", "requirement_type": "confirm", "notes": ""},
                {"name": "Business records", "requirement_type": "conditional", "notes": ""},
            ],
            source_title="Central Example Loan source",
        ),
        raw_scheme(
            scheme_id="test-tn-support", name="Tamil Nadu Example Support",
            summary="Example state support for small businesses.",
            jurisdiction="state_ut", state_ut="Tamil Nadu",
            support_types=["training_mentoring"],
            eligible_business_types=["food_processing"],
            eligibility_rules=[stage_rule],
            required_documents=[{"name": "Business plan", "requirement_type": "confirm", "notes": ""}],
            source_title="Tamil Nadu Example Support source",
        ),
        raw_scheme(
            scheme_id="test-street-vendor", name="Street Vendor Example Support",
            summary="Example support specifically for street vendors.",
            support_types=["working_capital"],
            eligible_business_types=["street_vending"],
            eligibility_rules=[{
                "field": "business_type", "operator": "in", "value": ["street_vending"],
                "mandatory": True, "explanation": "The business must be street vending.",
                "source_excerpt": "The business must be street vending.",
            }],
            source_title="Street Vendor Example Support source",
        ),
    )
