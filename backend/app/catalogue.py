"""Scheme data model and record validation."""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from urllib.parse import urlparse

from . import constants as c

log = logging.getLogger("benefitbridge.catalogue")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{2,80}$")


def is_official_url(url, suffixes) -> bool:
    if not isinstance(url, str):
        return False
    try:
        p = urlparse(url.strip())
    except ValueError:
        return False
    host = (p.hostname or "").lower()
    if p.scheme != "https" or not host:
        return False
    return any(host == s or host.endswith("." + s) for s in suffixes)


def parse_iso_date(value) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@dataclass
class Scheme:
    scheme_id: str
    name: str
    summary: str
    jurisdiction: str
    scheme_status: str
    last_verified_at: str
    state_ut: str | None = None
    district: str | None = None
    support_types: list[str] = field(default_factory=list)
    eligible_business_types: list[str] = field(default_factory=list)
    eligibility_rules: list[dict] = field(default_factory=list)
    conditions_to_confirm: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    benefits: list[str] = field(default_factory=list)
    required_documents: list[dict] = field(default_factory=list)
    application_steps: list[str] = field(default_factory=list)
    official_source_urls: list[str] = field(default_factory=list)
    source_title: str = ""
    review_notes: list[str] = field(default_factory=list)  # data gaps flagged for review

    @classmethod
    def from_dict(cls, raw: dict) -> "Scheme":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_inactive(self) -> bool:
        return self.scheme_status in c.INACTIVE_STATUSES

    def effective_rules(self) -> list[dict]:
        """Explicit rules plus a business-type rule derived from eligible_business_types.
        An empty eligible_business_types list means *unknown*, never 'all'."""
        rules = list(self.eligibility_rules)
        if self.eligible_business_types:
            rules.append({
                "field": "business_type", "operator": "in",
                "value": list(self.eligible_business_types), "mandatory": True,
                "explanation": "The scheme record lists specific eligible business activities.",
            })
        return rules


def _validate_rules(rules, errors: list[str]) -> None:
    if not isinstance(rules, list):
        errors.append("eligibility_rules must be a list")
        return
    for i, r in enumerate(rules):
        tag = f"eligibility_rules[{i}]"
        if not isinstance(r, dict):
            errors.append(f"{tag} must be an object")
            continue
        if r.get("field") not in c.RULE_FIELDS:
            errors.append(f"{tag}.field is not a supported profile field")
        op = r.get("operator")
        if op not in c.OPERATORS:
            errors.append(f"{tag}.operator is not supported")
        val = r.get("value")
        if op in ("in", "not_in", "contains_any") and not isinstance(val, list):
            errors.append(f"{tag}.value must be a list for operator {op}")
        if op in ("lte", "gte") and (isinstance(val, bool) or not isinstance(val, (int, float))):
            errors.append(f"{tag}.value must be a number for operator {op}")
        if op == "between" and (
            not isinstance(val, list) or len(val) != 2 or
            any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in val)
        ):
            errors.append(f"{tag}.value must contain two numbers for operator {op}")
        if not isinstance(r.get("mandatory"), bool):
            errors.append(f"{tag}.mandatory must be true or false")
        if not isinstance(r.get("explanation"), str) or not r["explanation"].strip():
            errors.append(f"{tag}.explanation is required")
        if not isinstance(r.get("source_excerpt"), str) or not r["source_excerpt"].strip():
            errors.append(f"{tag}.source_excerpt is required")


def validate_scheme_record(raw, suffixes) -> list[str]:
    """L2: returns a list of problems. An ACTIVE record with problems must not be activated."""
    if not isinstance(raw, dict):
        return ["record must be an object"]
    errors: list[str] = []
    sid = raw.get("scheme_id")
    if not isinstance(sid, str) or not ID_RE.match(sid):
        errors.append("scheme_id must be a stable lowercase slug")
    for key in ("name", "summary"):
        if not isinstance(raw.get(key), str) or not raw[key].strip():
            errors.append(f"{key} is required")
    juris = raw.get("jurisdiction")
    if juris not in c.JURISDICTIONS:
        errors.append("jurisdiction must be central, state_ut or local")
    if juris in ("state_ut", "local") and raw.get("state_ut") not in c.STATES_UT:
        errors.append("state_ut must be a canonical state/UT name for state-specific schemes")
    status = raw.get("scheme_status")
    if status not in c.SCHEME_STATUSES:
        errors.append("scheme_status is not a supported value")
    if parse_iso_date(raw.get("last_verified_at")) is None:
        errors.append("last_verified_at must be an ISO date (YYYY-MM-DD)")
    for s in raw.get("support_types", []) or []:
        if s not in c.ASSISTANCE_NEEDS:
            errors.append(f"unsupported support type: {s}")
    for t in raw.get("eligible_business_types", []) or []:
        if t not in c.BUSINESS_TYPES:
            errors.append(f"unsupported business type: {t}")
    _validate_rules(raw.get("eligibility_rules", []) or [], errors)
    for i, d in enumerate(raw.get("required_documents", []) or []):
        if not isinstance(d, dict) or not d.get("name") or d.get("requirement_type") not in c.REQUIREMENT_TYPES:
            errors.append(f"required_documents[{i}] needs a name and a valid requirement_type")
    if status in ("active", "possibly_changed"):
        urls = raw.get("official_source_urls")
        if not isinstance(urls, list) or not urls:
            errors.append("active records need at least one official source URL")
        elif not all(is_official_url(u, suffixes) for u in urls):
            errors.append("every source URL must be an https URL on an allowed official domain")
        if not (raw.get("eligibility_rules") or raw.get("eligible_business_types")):
            errors.append("active records need structured eligibility information")
    return errors


class Catalogue:
    def __init__(self, schemes: list[Scheme], load_errors: list[dict] | None = None):
        self._schemes = {s.scheme_id: s for s in schemes}
        self.load_errors = load_errors or []

    def __len__(self) -> int:
        return len(self._schemes)

    def all(self) -> list[Scheme]:
        return list(self._schemes.values())

    def get(self, scheme_id: str) -> Scheme | None:
        return self._schemes.get(scheme_id)

    def filter(self, *, state_ut=None, jurisdiction=None, support_type=None, status=None,
               q=None, include_inactive=False) -> list[Scheme]:
        out = []
        for s in self._schemes.values():
            if s.is_inactive and not include_inactive:
                continue
            if status and s.scheme_status != status:
                continue
            if jurisdiction and s.jurisdiction != jurisdiction:
                continue
            if state_ut and s.jurisdiction != "central" and s.state_ut != state_ut:
                continue
            if support_type and support_type not in s.support_types:
                continue
            if q and q.lower() not in f"{s.name} {s.summary}".lower():
                continue
            out.append(s)
        return sorted(out, key=lambda s: s.name.lower())


def build_catalogue(raw_records: list, suffixes) -> Catalogue:
    schemes: list[Scheme] = []
    problems: list[dict] = []
    seen: set[str] = set()
    for raw in raw_records:
        errs = validate_scheme_record(raw, suffixes)
        sid = raw.get("scheme_id") if isinstance(raw, dict) else None
        if not isinstance(raw, dict) or not isinstance(sid, str) or not ID_RE.match(sid):
            problems.append({"scheme_id": sid, "errors": errs})
            continue
        if sid in seen:  # E18: never silently merge duplicates
            problems.append({"scheme_id": sid, "errors": ["duplicate scheme_id; record skipped"]})
            continue
        seen.add(sid)
        try:
            scheme = Scheme.from_dict(raw)
        except TypeError as exc:
            problems.append({"scheme_id": sid, "errors": [f"malformed record: {exc}"]})
            continue
        if errs:
            problems.append({"scheme_id": sid, "errors": errs})
            if scheme.scheme_status in ("active", "possibly_changed"):
                scheme.scheme_status = "unverified"  # reject activation (E6)
                scheme.review_notes.append("Record failed validation and was not activated.")
        schemes.append(scheme)
    for p in problems:
        log.warning("catalogue_validation scheme_id=%s problems=%d", p["scheme_id"], len(p["errors"]))
    return Catalogue(schemes, problems)
