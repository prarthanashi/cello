"""Load scheme records and their related data from Supabase."""
from __future__ import annotations

import logging
from typing import Any

from .catalogue import Catalogue, build_catalogue
from .config import Settings

log = logging.getLogger("benefitbridge.catalogue")
PAGE_SIZE = 1000


def _read_table(client: Any, table: str) -> list[dict]:
    rows = []
    start = 0
    while True:
        response = client.table(table).select("*").range(start, start + PAGE_SIZE - 1).execute()
        page = response.data
        if not isinstance(page, list):
            raise TypeError(f"Supabase table {table} did not return a row list")
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        start += PAGE_SIZE


def load_supabase_catalogue(
    settings: Settings,
    suffixes: tuple[str, ...],
    client: Any | None = None,
) -> Catalogue:
    if client is None:
        if not settings.supabase_url or not settings.supabase_secret_key:
            log.error("supabase_catalogue_not_configured")
            return Catalogue([], [{"scheme_id": None, "errors": ["Supabase credentials are not configured"]}])
        from supabase import create_client
        client = create_client(settings.supabase_url, settings.supabase_secret_key)
    schemes = _read_table(client, "schemes")
    rules = _read_table(client, "eligibility_rules")
    documents = _read_table(client, "scheme_documents")
    sources = _read_table(client, "scheme_sources")

    rules_by_scheme: dict[str, list[dict]] = {}
    for row in rules:
        rules_by_scheme.setdefault(row["scheme_id"], []).append({
            "field": row["field"],
            "operator": row["operator"],
            "value": row["value"],
            "mandatory": row.get("is_mandatory"),
            "explanation": row["explanation"],
            "source_excerpt": row.get("source_excerpt", ""),
        })

    documents_by_scheme: dict[str, list[dict]] = {}
    for row in documents:
        documents_by_scheme.setdefault(row["scheme_id"], []).append({
            "name": row["name"],
            "requirement_type": row["requirement_type"],
            "notes": row.get("notes") or "",
        })

    sources_by_scheme: dict[str, list[dict]] = {}
    for row in sources:
        sources_by_scheme.setdefault(row["scheme_id"], []).append(row)

    records = []
    for row in schemes:
        scheme_id = row["scheme_id"]
        scheme_sources = sorted(sources_by_scheme.get(scheme_id, []), key=lambda source: source["url"])
        records.append({
            "scheme_id": scheme_id,
            "name": row["name"],
            "summary": row["summary"],
            "jurisdiction": row["jurisdiction"],
            "state_ut": row.get("state_ut"),
            "district": row.get("district"),
            "support_types": row.get("support_types") or [],
            "eligible_business_types": row.get("eligible_business_types") or [],
            "eligibility_rules": rules_by_scheme.get(scheme_id, []),
            "required_documents": documents_by_scheme.get(scheme_id, []),
            "conditions_to_confirm": row.get("conditions_to_confirm") or [],
            "benefits": row.get("benefits") or [],
            "exclusions": row.get("exclusions") or [],
            "application_steps": row.get("application_steps") or [],
            "review_notes": row.get("review_notes") or [],
            "official_source_urls": [source["url"] for source in scheme_sources],
            "source_title": next(
                (source["title"] for source in scheme_sources if source.get("title")),
                "",
            ),
            "last_verified_at": row["last_verified_at"],
            "scheme_status": row["scheme_status"],
        })

    catalogue = build_catalogue(records, suffixes)
    log.info("supabase_catalogue_loaded count=%d validation_errors=%d",
             len(catalogue), len(catalogue.load_errors))
    return catalogue
