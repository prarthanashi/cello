"""L1 — business profile validation. Unknown values stay unknown; nothing is guessed."""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from . import constants as c

MAX_DETAILS = 1000
MAX_OTHER = 100


class ValidationError(Exception):
    def __init__(self, fields: dict[str, str], message: str | None = None):
        super().__init__(message or "Please complete the highlighted fields to find relevant schemes.")
        self.fields = fields
        self.message = message or str(self)


@dataclass(frozen=True)
class Profile:
    state_ut: str
    business_type: str
    ownership_category: str
    business_stage: str
    assistance_need: list[str]
    district: str | None = None
    business_type_other: str | None = None
    annual_turnover_inr: float | None = None
    turnover_is_approximate: bool = False
    employee_count: int | None = None
    registration_status: str | None = None
    additional_details: str | None = None

    def for_matching(self) -> dict:
        d = asdict(self)
        d.pop("additional_details", None)  # never needed for matching
        return d


def normalise_state(value: str) -> str | None:
    key = " ".join(value.strip().lower().split())
    for state in c.STATES_UT:
        if state.lower() == key:
            return state
    return c.STATE_ALIASES.get(key)


def _clean_str(v) -> str | None:
    if v is None:
        return None
    if not isinstance(v, str):
        return ""
    v = " ".join(v.split())
    return v or None


def _parse_number(v, name: str, errors: dict, integer: bool = False):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    if isinstance(v, bool):
        errors[name] = "Enter a valid non-negative value, or choose ‘I’m not sure’."
        return None
    try:
        num = float(v.replace(",", "")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        errors[name] = "Enter a valid non-negative value, or choose ‘I’m not sure’."
        return None
    if math.isnan(num) or math.isinf(num) or num < 0 or num > 1e13:
        errors[name] = "Enter a valid non-negative value, or choose ‘I’m not sure’."
        return None
    if integer:
        if num != int(num):
            errors[name] = "Enter a whole number, or choose ‘I’m not sure’."
            return None
        return int(num)
    return num


def validate_profile(payload) -> Profile:
    if not isinstance(payload, dict):
        raise ValidationError({"_": "Profile must be a JSON object."}, "Invalid request body.")
    errors: dict[str, str] = {}

    state_raw = _clean_str(payload.get("state_ut"))
    state = None
    if not state_raw:
        errors["state_ut"] = "Select your state or union territory."
    else:
        state = normalise_state(state_raw)
        if state is None:
            errors["state_ut"] = "Select a supported state or union territory from the list."

    def enum_field(name: str, allowed: list[str], label: str) -> str | None:
        raw = _clean_str(payload.get(name))
        if not raw:
            errors[name] = f"Select {label}."
            return None
        if raw not in allowed:
            errors[name] = f"Select a supported value for {label}."
            return None
        return raw

    business_type = enum_field("business_type", c.BUSINESS_TYPES, "a business type")
    ownership = enum_field("ownership_category", c.OWNERSHIP, "an ownership category")
    stage = enum_field("business_stage", c.STAGES, "a business stage")

    needs_raw = payload.get("assistance_need")
    needs: list[str] = []
    if not isinstance(needs_raw, list) or not needs_raw:
        errors["assistance_need"] = "Choose at least one type of support you need."
    else:
        for n in needs_raw:
            if n not in c.ASSISTANCE_NEEDS:
                errors["assistance_need"] = "Choose supported support types only."
                break
            if n not in needs:
                needs.append(n)

    other = _clean_str(payload.get("business_type_other"))
    if other and len(other) > MAX_OTHER:
        errors["business_type_other"] = f"Use at most {MAX_OTHER} characters."
    district = _clean_str(payload.get("district"))
    if district and len(district) > 80:
        errors["district"] = "Use at most 80 characters."

    turnover = _parse_number(payload.get("annual_turnover_inr"), "annual_turnover_inr", errors)
    employees = _parse_number(payload.get("employee_count"), "employee_count", errors, integer=True)

    reg = _clean_str(payload.get("registration_status"))
    if reg and reg not in c.REGISTRATION:
        errors["registration_status"] = "Select a supported value, or choose ‘Unsure’."

    details = payload.get("additional_details")
    if details is not None and not isinstance(details, str):
        errors["additional_details"] = "Additional details must be text."
        details = None
    elif isinstance(details, str):
        details = details.strip() or None
        if details and len(details) > MAX_DETAILS:
            errors["additional_details"] = f"Use at most {MAX_DETAILS:,} characters."

    if errors:
        raise ValidationError(errors)

    return Profile(
        state_ut=state, business_type=business_type, ownership_category=ownership,
        business_stage=stage, assistance_need=needs, district=district,
        business_type_other=other, annual_turnover_inr=turnover,
        turnover_is_approximate=bool(payload.get("turnover_is_approximate", False)),
        employee_count=employees, registration_status=reg, additional_details=details,
    )


DEMO_PROFILE = {
    "state_ut": "Tamil Nadu",
    "district": "Chennai",
    "business_type": "food_processing",
    "ownership_category": "individual_proprietorship",
    "annual_turnover_inr": 1200000,
    "turnover_is_approximate": True,
    "employee_count": 3,
    "business_stage": "newly_operating",
    "assistance_need": ["credit_loan", "subsidy_grant", "equipment_technology"],
    "registration_status": "unsure",
    "additional_details": "Fictional demo profile: a small home-kitchen snack business.",
}
