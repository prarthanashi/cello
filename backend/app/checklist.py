"""L4 — document checklist built only from the scheme record's required_documents."""
from . import constants as c
from .catalogue import Scheme


def build_checklist(scheme: Scheme) -> dict:
    ref = scheme.official_source_urls[0] if scheme.official_source_urls else None
    items = [{
        "name": d["name"], "requirement_type": d["requirement_type"],
        "label": c.REQUIREMENT_LABELS[d["requirement_type"]],
        "notes": d.get("notes") or "", "source_reference": ref,
    } for d in scheme.required_documents]
    return {
        "scheme_id": scheme.scheme_id, "scheme_name": scheme.name, "items": items,
        "last_verified_at": scheme.last_verified_at, "official_source_urls": list(scheme.official_source_urls),
        "disclaimer": "These items reflect the catalogue record and may change. Confirm the current list on the official source.",
        "unavailable_message": None if items else "Document requirements are not specified in the available source.",
    }
