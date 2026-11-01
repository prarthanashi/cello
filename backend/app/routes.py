"""HTTP API. Routes never call an AI provider; they only call ai_service.answer_scheme_question."""
from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from . import constants as c
from .ai_service import (AIServiceError, QuestionError, ai_configured, answer_scheme_question,
                         validate_question)
from .checklist import build_checklist
from .matching import freshness_warnings, recommend, review_overdue
from .validation import DEMO_PROFILE, ValidationError, validate_profile

bp = Blueprint("api", __name__, url_prefix="/api")


def ctx():
    return current_app.extensions["bb"]


def err(code: str, message: str, status: int, fields: dict | None = None, **extra):
    body = {"error": {"code": code, "message": message}}
    if fields:
        body["error"]["fields"] = fields
    body.update(extra)
    return jsonify(body), status


def json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _require_catalogue():
    if len(ctx().catalogue) == 0:  # E17: never invent fallback schemes
        return err("catalogue_unavailable", "Scheme information is temporarily unavailable.", 503)
    return None


def _summary(s) -> dict:
    b = ctx()
    return {
        "scheme_id": s.scheme_id, "name": s.name, "summary": s.summary, "jurisdiction": s.jurisdiction,
        "state_ut": s.state_ut, "support_types": s.support_types, "scheme_status": s.scheme_status,
        "last_verified_at": s.last_verified_at,
        "needs_reverification": review_overdue(s, b.today(), b.settings.review_window_days),
        "official_source_urls": s.official_source_urls,
    }


@bp.get("/health")
def health():
    b = ctx()
    return jsonify({"status": "ok", "ai_configured": ai_configured(b.settings),
                    "catalogue_count": len(b.catalogue)})


@bp.get("/meta/options")
def options():
    return jsonify({
        "states_ut": c.STATES_UT, "business_types": c.BUSINESS_TYPES, "ownership_categories": c.OWNERSHIP,
        "business_stages": c.STAGES, "assistance_needs": c.ASSISTANCE_NEEDS,
        "registration_statuses": c.REGISTRATION, "jurisdictions": c.JURISDICTIONS,
        "scheme_statuses": c.SCHEME_STATUSES, "requirement_labels": c.REQUIREMENT_LABELS,
        "catalogue_notice": c.CATALOGUE_NOTICE,
    })


@bp.get("/demo/profile")
def demo_profile():
    return jsonify({"profile": DEMO_PROFILE, "note": "Fictional sample profile for demonstration only."})


@bp.get("/schemes")
def list_schemes():
    unavailable = _require_catalogue()
    if unavailable:
        return unavailable
    a = request.args
    state = a.get("state_ut")
    if state:
        from .validation import normalise_state
        state = normalise_state(state)
        if state is None:
            return err("invalid_filter", "Select a supported state or union territory.", 400, {"state_ut": "Unknown state/UT."})
    found = ctx().catalogue.filter(
        state_ut=state, jurisdiction=a.get("jurisdiction"), support_type=a.get("support_type"),
        status=a.get("status"), q=(a.get("q") or "")[:100] or None,
        include_inactive=a.get("include_inactive") == "true")
    return jsonify({"schemes": [_summary(s) for s in found], "count": len(found),
                    "catalogue_notice": c.CATALOGUE_NOTICE})


@bp.get("/schemes/<scheme_id>")
def scheme_detail(scheme_id):
    unavailable = _require_catalogue()
    if unavailable:
        return unavailable
    b = ctx()
    s = b.catalogue.get(scheme_id)
    if s is None:  # E9
        return err("scheme_not_found", "We couldn’t find that scheme. Return to recommendations.", 404)
    warnings = freshness_warnings(s, b.today(), b.settings.review_window_days)
    if s.is_inactive:
        warnings.insert(0, f"This scheme is marked {s.scheme_status}. Check the official department for current options.")
    return jsonify({
        "scheme": s.to_dict(),
        "freshness": {"last_verified_at": s.last_verified_at, "warnings": warnings,
                      "needs_reverification": review_overdue(s, b.today(), b.settings.review_window_days),
                      "review_window_days": b.settings.review_window_days},
        "catalogue_notice": c.CATALOGUE_NOTICE,
    })


@bp.get("/schemes/<scheme_id>/checklist")
def scheme_checklist(scheme_id):
    s = ctx().catalogue.get(scheme_id)
    if s is None:
        return err("scheme_not_found", "We couldn’t find that scheme. Return to recommendations.", 404)
    return jsonify(build_checklist(s))


@bp.post("/eligibility/match")
def match():
    unavailable = _require_catalogue()
    if unavailable:
        return unavailable
    body = json_body()
    if body is None:
        return err("invalid_json", "Request body must be a JSON object.", 400)
    try:
        profile = validate_profile(body)
    except ValidationError as exc:  # E1-E3
        return err("validation_error", exc.message, 400, exc.fields)
    b = ctx()
    result = recommend(b.catalogue.all(), profile.for_matching(), b.today(), b.settings.review_window_days)
    result["profile_used"] = profile.for_matching()
    return jsonify(result)


PROFILE_KEYS = ("state_ut", "business_type", "ownership_category", "business_stage", "assistance_need")


@bp.post("/assistant/ask")
def ask():
    b = ctx()
    body = json_body()
    if body is None:
        return err("invalid_json", "Request body must be a JSON object.", 400)
    try:
        question = validate_question(body.get("question"))  # E10
    except QuestionError as exc:
        return err("invalid_question", str(exc), 400)
    scheme_id = body.get("scheme_id")
    scheme = None
    if scheme_id is not None:
        scheme = b.catalogue.get(scheme_id) if isinstance(scheme_id, str) else None
        if scheme is None:
            return err("scheme_not_found", "We couldn’t find that scheme. Return to recommendations.", 404)
    profile = body.get("profile") if isinstance(body.get("profile"), dict) else {}
    profile_fields = {k: profile[k] for k in PROFILE_KEYS if k in profile}

    chunks = [ch for ch in b.retriever.search(question, scheme_id=scheme_id)
              if (s := b.catalogue.get(ch.scheme_id)) is not None and not s.is_inactive]
    urls = list(scheme.official_source_urls) if scheme else sorted({ch.url for ch in chunks})
    verified = sorted({ch.last_verified_at for ch in chunks})
    freshness = (f"Based on scheme information last verified {', '.join(verified)}. Confirm on the official source."
                 if verified else "No scheme details were retrieved.")
    try:
        answer = answer_scheme_question(question, chunks, settings=b.settings, profile_fields=profile_fields)
    except AIServiceError as exc:
        extra = {"fallback": {**exc.fallback.to_dict(), "official_source_urls": urls, "freshness_note": freshness}} \
            if exc.fallback else {}
        return err(exc.code, exc.message, exc.http_status, **extra)
    return jsonify({**answer.to_dict(), "official_source_urls": urls, "freshness_note": freshness})
