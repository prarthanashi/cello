"""L3 — deterministic eligibility matching. No LLM is involved in any eligibility decision."""
from __future__ import annotations

from datetime import date

from . import constants as c
from .catalogue import Scheme, parse_iso_date

STATUS_RANK = {"potential_match": 0, "needs_more_information": 1, "unlikely_to_qualify": 2}
OUTCOME_PRIORITY = {
    "potential_match": {"met": 0, "unknown": 1, "not_met": 2},
    "needs_more_information": {"unknown": 0, "met": 1, "not_met": 2},
    "unlikely_to_qualify": {"not_met": 0, "unknown": 1, "met": 2},
}
RANKING_NOTE = (
    "Ranked by match status first (potential matches, then schemes needing more information), "
    "then by how many documented criteria are met, then by overlap with the support you asked for. "
    "This is not a probability of approval."
)


def evaluate_rule(profile: dict, rule: dict) -> str:
    """Return 'met', 'not_met' or 'unknown'. Missing profile data is always 'unknown'."""
    field, op, target = rule["field"], rule["operator"], rule["value"]
    value = profile.get(field)
    if value is None or value == "" or value == []:
        return "unknown"
    # "I'm not sure" / "Other" answers are unknown, never a guess in either direction.
    if (field == "ownership_category" and value == "other_unsure") or \
       (field == "business_type" and value == "other") or \
       (field == "registration_status" and value == "unsure"):
        return "unknown"
    try:
        if op == "eq":
            ok = value == target
        elif op == "ne":
            ok = value != target
        elif op == "in":
            ok = value in target
        elif op == "not_in":
            ok = value not in target
        elif op == "lte":
            ok = float(value) <= float(target)
        elif op == "gte":
            ok = float(value) >= float(target)
        elif op == "between":
            ok = float(target[0]) <= float(value) <= float(target[1])
        elif op == "contains_any":
            ok = bool(set(value if isinstance(value, list) else [value]) & set(target))
        else:
            return "unknown"
    except (TypeError, ValueError):
        return "unknown"
    return "met" if ok else "not_met"


def _jurisdiction_result(scheme: Scheme, profile: dict) -> dict:
    if scheme.jurisdiction == "central":
        return {"outcome": "met", "explanation": "Central scheme: it may apply across India, subject to its other criteria."}
    if scheme.jurisdiction == "state_ut":
        mine = profile.get("state_ut")
        if mine == scheme.state_ut:
            return {"outcome": "met", "explanation": f"This is a {scheme.state_ut} scheme and your business is in {mine}."}
        return {"outcome": "not_met", "explanation": f"This scheme is specific to {scheme.state_ut}; your business is in {mine}."}
    # local: state must match, and district when the record names one
    if profile.get("state_ut") != scheme.state_ut:
        return {"outcome": "not_met", "explanation": f"This is a local scheme in {scheme.state_ut}."}
    if scheme.district:
        d = (profile.get("district") or "").strip().lower()
        if not d:
            return {"outcome": "unknown", "explanation": f"This scheme is specific to {scheme.district}; add your district to check."}
        if d != scheme.district.strip().lower():
            return {"outcome": "not_met", "explanation": f"This scheme is specific to {scheme.district}."}
    return {"outcome": "met", "explanation": f"Local scheme in {scheme.state_ut}."}


def review_overdue(scheme: Scheme, today: date, window_days: int) -> bool:
    verified = parse_iso_date(scheme.last_verified_at)
    return verified is None or (today - verified).days > window_days


def freshness_warnings(scheme: Scheme, today: date, window_days: int) -> list[str]:
    warnings = []
    if scheme.scheme_status == "possibly_changed":
        warnings.append("This record may have changed. Verify the current rules on the official source before relying on it.")
    if review_overdue(scheme, today, window_days):
        warnings.append(f"Needs re-verification: last verified {scheme.last_verified_at}. This is a product warning, not a government expiry.")
    return warnings


def match_scheme(scheme: Scheme, profile: dict, today: date, window_days: int = 90) -> dict:
    criteria = []  # (field, outcome, mandatory, explanation)
    j = _jurisdiction_result(scheme, profile)
    criteria.append(("jurisdiction", j["outcome"], True, j["explanation"]))
    rules = scheme.effective_rules()
    for r in rules:
        criteria.append((r["field"], evaluate_rule(profile, r), bool(r["mandatory"]), r["explanation"]))
    data_gap = not rules
    if data_gap:  # E5: incomplete record is unknown, never a match
        criteria.append(("eligibility_details", "unknown", True,
                         "Eligibility details are incomplete in the available source."))

    mandatory = [x for x in criteria if x[2]]
    if any(x[1] == "not_met" for x in mandatory):
        status = "unlikely_to_qualify"
    elif any(x[1] == "unknown" for x in mandatory):
        status = "needs_more_information"
    else:
        status = "potential_match"

    prio = OUTCOME_PRIORITY[status]
    reasons = [
        {"code": f"{f.upper()}_{o.upper()}", "field": f, "outcome": o, "mandatory": m, "explanation": e}
        for f, o, m, e in sorted(criteria, key=lambda x: (prio[x[1]], not x[2]))
    ]
    missing = sorted({f for f, o, m, _ in criteria if o == "unknown" and f in c.RULE_FIELDS})
    overlap = len(set(profile.get("assistance_need") or []) & set(scheme.support_types))
    return {
        "scheme_id": scheme.scheme_id, "name": scheme.name, "match_status": status,
        "reasons": reasons, "missing_fields": missing,
        "last_verified_at": scheme.last_verified_at,
        "official_source_urls": list(scheme.official_source_urls),
        "jurisdiction": scheme.jurisdiction, "state_ut": scheme.state_ut,
        "support_types": list(scheme.support_types), "scheme_status": scheme.scheme_status,
        "needs_reverification": review_overdue(scheme, today, window_days),
        "warnings": freshness_warnings(scheme, today, window_days),
        "conditions_to_confirm": list(scheme.conditions_to_confirm),
        "data_incomplete": data_gap,
        "ranking": {"criteria_met": sum(1 for x in criteria if x[1] == "met"),
                    "criteria_total": len(criteria), "need_overlap": overlap},
    }


def sort_key(rec: dict):
    r = rec["ranking"]
    return (STATUS_RANK[rec["match_status"]], -r["criteria_met"], -r["need_overlap"], rec["name"].lower())


def recommend(schemes: list[Scheme], profile: dict, today: date, window_days: int = 90) -> dict:
    """Split results into likely/possible recommendations, unlikely schemes, and inactive records.
    Expired/withdrawn/unverified records never appear as active recommendations (AC8, E7)."""
    recs, unlikely, historical = [], [], []
    for s in schemes:
        if s.is_inactive:
            historical.append({
                "scheme_id": s.scheme_id, "name": s.name, "scheme_status": s.scheme_status,
                "last_verified_at": s.last_verified_at,
                "official_source_urls": list(s.official_source_urls),
                "message": f"This scheme is marked {s.scheme_status}. Check the official department for current options.",
            })
            continue
        rec = match_scheme(s, profile, today, window_days)
        (unlikely if rec["match_status"] == "unlikely_to_qualify" else recs).append(rec)
    recs.sort(key=sort_key)
    unlikely.sort(key=sort_key)
    return {"recommendations": recs, "not_likely": unlikely, "historical": historical,
            "ranking_note": RANKING_NOTE, "catalogue_notice": c.CATALOGUE_NOTICE}
