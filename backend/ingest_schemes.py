"""
ingest_schemes.py: fetch one official scheme page, extract it with Gemini,
validate it, and upsert it into Supabase.

Usage (from your backend folder):
    python ingest_schemes.py --scheme-id central-scheme --url https://<official-page> --jurisdiction central --dry-run
    python ingest_schemes.py --scheme-id central-scheme --url https://<official-page> --jurisdiction central
    python ingest_schemes.py --scheme-id state-scheme --url https://<official-page> --jurisdiction state_ut --state "Tamil Nadu"
    python ingest_schemes.py --scheme-id central-scheme --url https://<official-pdf> --jurisdiction central --dry-run --ocr

Environment variables (.env, never committed):
    SUPABASE_URL, SUPABASE_SECRET_KEY, GEMINI_API_KEY, GEMINI_MODEL
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import date, datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pydantic import BaseModel
from pypdf import PdfReader, PdfWriter

from app import constants as c

load_dotenv()

# ---------------------------------------------------------------------------
# Keep extraction values aligned with the profile and matcher constants.
# ---------------------------------------------------------------------------
ALLOWED_SUFFIXES = (".gov.in", ".nic.in")  # add official domains like ".org.in" only after checking
RULE_FIELDS = set(c.RULE_FIELDS)
OPERATORS = set(c.OPERATORS)
SUPPORT_TYPES = set(c.ASSISTANCE_NEEDS)
BUSINESS_TYPES = set(c.BUSINESS_TYPES)
FIELD_VALUES = {
    "business_type": set(c.BUSINESS_TYPES),
    "registration_status": set(c.REGISTRATION),
    "business_stage": set(c.STAGES),
    "ownership_category": set(c.OWNERSHIP),
}
REQUIREMENT_TYPES = {"required", "conditional", "confirm"}
MIN_TEXT_CHARS = 500
MAX_TEXT_CHARS = 80000
MAX_ATTEMPTS = 3
MAX_PDF_BYTES = 15 * 1024 * 1024
MAX_OCR_PAGES = 20
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}


class IngestError(Exception):
    pass


# ---------------------------------------------------------------------------
# Shape of what Gemini must return (structured output).
# value_json holds the rule value as a JSON string, e.g. '["Tamil Nadu"]' or '1000000'.
# ---------------------------------------------------------------------------
class Rule(BaseModel):
    field: str
    operator: str
    value_json: str
    is_mandatory: bool
    explanation: str
    source_excerpt: str


class Doc(BaseModel):
    name: str
    requirement_type: str
    notes: str


class Extraction(BaseModel):
    name: str
    summary: str
    support_types: list[str]
    eligible_business_types: list[str]
    benefits: list[str]
    exclusions: list[str]
    application_steps: list[str]
    rules: list[Rule]
    documents: list[Doc]


# ---------------------------------------------------------------------------
# Step 1: fetch and clean the official page
# ---------------------------------------------------------------------------
def check_domain(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise IngestError(f"Only https URLs are allowed: {url}")
    if not host.endswith(ALLOWED_SUFFIXES):
        raise IngestError(f"Not an allowed official domain {ALLOWED_SUFFIXES}: {host}")


def fetch_pdf(url: str) -> tuple[bytes, str]:
    """Fetch an official PDF, limiting input size and OCR pages."""
    check_domain(url)
    with requests.get(url, timeout=30, headers=REQUEST_HEADERS, stream=True) as resp:
        resp.raise_for_status()
        check_domain(resp.url)
        content_length = resp.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_PDF_BYTES:
                    raise IngestError("PDF exceeds the 15 MB size limit.")
            except ValueError as exc:
                raise IngestError("The PDF response has an invalid content length.") from exc

        chunks = []
        size = 0
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            size += len(chunk)
            if size > MAX_PDF_BYTES:
                raise IngestError("PDF exceeds the 15 MB size limit.")
            chunks.append(chunk)
        pdf_bytes = b"".join(chunks)
        content_type = resp.headers.get("content-type", "").lower()
        if "pdf" not in content_type and not resp.url.lower().endswith(".pdf") \
                and not pdf_bytes.startswith(b"%PDF-"):
            raise IngestError("--ocr requires a PDF URL.")
        title = os.path.basename(urlparse(resp.url).path) or url

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        if not reader.pages:
            raise IngestError("The PDF contains no pages.")
        if len(reader.pages) > MAX_OCR_PAGES:
            writer = PdfWriter()
            for page in reader.pages[:MAX_OCR_PAGES]:
                writer.add_page(page)
            limited_pdf = io.BytesIO()
            writer.write(limited_pdf)
            pdf_bytes = limited_pdf.getvalue()
    except IngestError:
        raise
    except Exception as exc:
        raise IngestError("The downloaded file could not be read as a PDF.") from exc
    return pdf_bytes, title


def fetch_text(url: str) -> tuple[str, str]:
    """Return (clean_text, title). Raises IngestError if the page is not usable."""
    check_domain(url)
    resp = requests.get(
        url, timeout=30,
        headers=REQUEST_HEADERS,
    )
    resp.raise_for_status()
    check_domain(resp.url)  # a redirect must not leave the official domains

    content_type = resp.headers.get("content-type", "").lower()
    if "pdf" in content_type or resp.url.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(resp.content))
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
        title = os.path.basename(urlparse(resp.url).path) or url
    else:
        soup = BeautifulSoup(resp.text, "html.parser")
        title = (soup.title.string or "").strip() if soup.title else url
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n")

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if len(text) < MIN_TEXT_CHARS:
        raise IngestError(
            "Page has almost no readable text (JavaScript-rendered page or scanned PDF?). "
            "Try another official URL."
        )
    if len(text) > MAX_TEXT_CHARS:
        print(f"WARNING: text truncated from {len(text)} to {MAX_TEXT_CHARS} characters")
        text = text[:MAX_TEXT_CHARS]
    return text, title


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Step 2: ask Gemini to extract structured data from the page text only
# ---------------------------------------------------------------------------
def build_prompt(url: str, text: str, previous_errors: list[str]) -> str:
    fixed_choice_values = {
        field: sorted(values) for field, values in FIELD_VALUES.items()
    }
    prompt = f"""You are extracting a government scheme record from an official source.
Use ONLY the source text below. Never use outside knowledge. Never invent values.
If something is not stated, use an empty list, or the text "not specified in the available source".

Rules for the output:
- support_types: only from {sorted(SUPPORT_TYPES)}
- eligible_business_types: only from {sorted(BUSINESS_TYPES)}. Empty list if the source does not say.
- rules: one item per eligibility criterion stated in the source.
  - field: one of {sorted(RULE_FIELDS)}
  - operator: one of {sorted(OPERATORS)}
  - value_json: a JSON-encoded value. Use a string or number for eq/ne, a list for in/not_in/contains_any,
    a number for gte/lte, and a two-number list for between.
  - Fixed-choice field values: {fixed_choice_values}
  - For fields with fixed choices, value_json must use exactly the allowed values for that field.
  - Extract every eligibility condition that maps to one of the allowed fields, not only the first one.
  - is_mandatory: true only for conditions an applicant must meet to be eligible to apply.
    Steps that happen after approval (such as registering after a loan is sanctioned) are not eligibility criteria.
  - explanation: one plain-language sentence for a shop owner
  - source_excerpt: a SHORT exact quote (under 200 characters) copied from the source text that supports the rule
  - Fix obvious missing spaces caused by PDF text extraction (for example "Ministryof" becomes "Ministry of").
- documents: requirement_type is one of {sorted(REQUIREMENT_TYPES)}. Use "confirm" if the source is unclear.
- benefits, exclusions, application_steps: short plain sentences taken from the source.

Source URL: {url}

SOURCE TEXT:
\"\"\"
{text}
\"\"\"
"""
    if previous_errors:
        prompt += "\nYour previous answer had these problems. Fix all of them:\n- " + "\n- ".join(previous_errors)
    return prompt


def call_gemini(prompt: str) -> Extraction:
    from google import genai
    from google.genai import errors
    from google.genai import types

    model = os.getenv("GEMINI_MODEL")
    if not model or not os.getenv("GEMINI_API_KEY"):
        raise IngestError("Set GEMINI_API_KEY and GEMINI_MODEL in your .env file")
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=Extraction,
        temperature=0,
    )
    resp = _generate_with_retries(client, model, prompt, config)
    try:
        return Extraction.model_validate_json(resp.text)
    except ValueError as exc:
        raise IngestError("Gemini returned invalid structured data.") from exc


def _generate_with_retries(client, model: str, contents, config):
    from google.genai import errors

    for attempt in range(4):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except errors.ClientError as exc:
            if exc.code != 429:
                raise IngestError(
                    f"Gemini rejected the request (HTTP {exc.code}). Check the request, API key, and model access."
                ) from exc
            if attempt == 3:
                break
            wait = 5 * (2 ** attempt)
            print(f"Gemini rate limited the request; retrying in {wait}s")
            time.sleep(wait)
        except errors.ServerError as exc:
            if not 500 <= exc.code < 600:
                raise IngestError(f"Gemini server request failed (HTTP {exc.code}).") from exc
            if attempt == 3:
                break
            wait = 5 * (2 ** attempt)
            print(f"Gemini server error (HTTP {exc.code}); retrying in {wait}s")
            time.sleep(wait)
    raise IngestError("Gemini failed after 4 retryable attempts")


def transcribe_pdf(pdf_bytes: bytes) -> str:
    from google import genai
    from google.genai import types

    model = os.getenv("GEMINI_MODEL")
    api_key = os.getenv("GEMINI_API_KEY")
    if not model or not api_key:
        raise IngestError("Set GEMINI_API_KEY and GEMINI_MODEL in your .env file")

    client = genai.Client(api_key=api_key)
    prompt = (
        "Transcribe the provided PDF verbatim in its original language. "
        "Do not summarize, translate, explain, or add any text."
    )
    pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    config = types.GenerateContentConfig(response_mime_type="text/plain", temperature=0)
    response = _generate_with_retries(client, model, [prompt, pdf_part], config)
    transcript = response.text
    if not isinstance(transcript, str) or len(transcript.strip()) < MIN_TEXT_CHARS:
        raise IngestError("Gemini transcription returned too little readable text.")
    return transcript.strip()


# ---------------------------------------------------------------------------
# Step 3: validate in plain Python (the AI is not trusted)
# ---------------------------------------------------------------------------
def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).lower().strip()


def value_is_valid(op: str, value) -> bool:
    is_num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)
    if op in ("eq", "ne"):
        return isinstance(value, (str, int, float, bool))
    if op in ("in", "not_in", "contains_any"):
        return isinstance(value, list) and bool(value)
    if op in ("gte", "lte"):
        return is_num(value)
    if op == "between":
        return isinstance(value, list) and len(value) == 2 and all(is_num(v) for v in value)
    return False


def validate(ex: Extraction, source_text: str) -> tuple[list[str], list[str]]:
    """Return (structural_errors, grounding_errors)."""
    structural, grounding = [], []
    if not ex.name.strip() or not ex.summary.strip():
        structural.append("name and summary must not be empty")
    for s in ex.support_types:
        if s not in SUPPORT_TYPES:
            structural.append(f"support_type '{s}' is not allowed")
    for b in ex.eligible_business_types:
        if b not in BUSINESS_TYPES:
            structural.append(f"business type '{b}' is not allowed")
    for d in ex.documents:
        if d.requirement_type not in REQUIREMENT_TYPES:
            structural.append(f"document '{d.name}' has invalid requirement_type '{d.requirement_type}'")

    haystack = norm(source_text)
    for i, r in enumerate(ex.rules):
        label = f"rule {i + 1} ({r.field})"
        if r.field not in RULE_FIELDS:
            structural.append(f"{label}: field not allowed")
        if r.operator not in OPERATORS:
            structural.append(f"{label}: operator not allowed")
        try:
            value = json.loads(r.value_json)
        except json.JSONDecodeError:
            structural.append(f"{label}: value_json is not valid JSON")
            continue
        allowed = FIELD_VALUES.get(r.field)
        if allowed is not None:
            items = value if isinstance(value, list) else [value]
            bad = [v for v in items if v not in allowed]
            if bad:
                structural.append(f"{label}: {bad} are not valid for '{r.field}'. Allowed: {sorted(allowed)}")
        if r.operator in OPERATORS and not value_is_valid(r.operator, value):
            structural.append(f"{label}: value does not fit operator '{r.operator}'")
        if not r.explanation.strip():
            structural.append(f"{label}: explanation is empty")
        if not r.source_excerpt.strip() or norm(r.source_excerpt) not in haystack:
            grounding.append(f"{label}: source_excerpt is not an exact quote from the source text")
    return structural, grounding


# ---------------------------------------------------------------------------
# Step 4: write to Supabase (order: schemes, rules, documents, sources)
# ---------------------------------------------------------------------------
def get_supabase():
    from supabase import create_client

    url, key = os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SECRET_KEY")
    if not url or not key:
        raise IngestError("Set SUPABASE_URL and SUPABASE_SECRET_KEY in your .env file")
    return create_client(url, key)


def save(sb, args, ex: Extraction, status: str, source_title: str, digest: str) -> None:
    now = datetime.now(timezone.utc).isoformat()

    # 1) parent row, upsert makes the script safe to rerun
    sb.table("schemes").upsert({
        "scheme_id": args.scheme_id,
        "name": ex.name,
        "summary": ex.summary,
        "jurisdiction": args.jurisdiction,
        "state_ut": args.state,
        "support_types": ex.support_types,
        "eligible_business_types": ex.eligible_business_types,
        "benefits": ex.benefits,
        "exclusions": ex.exclusions,
        "application_steps": ex.application_steps,
        "scheme_status": status,
        "last_verified_at": date.today().isoformat(),
    }, on_conflict="scheme_id").execute()

    # 2) child rows: replace the old ones so reruns never create duplicates
    sb.table("eligibility_rules").delete().eq("scheme_id", args.scheme_id).execute()
    if ex.rules:
        sb.table("eligibility_rules").insert([{
            "scheme_id": args.scheme_id,
            "field": r.field,
            "operator": r.operator,
            "value": json.loads(r.value_json),
            "is_mandatory": r.is_mandatory,
            "explanation": r.explanation,
            "source_excerpt": r.source_excerpt,
        } for r in ex.rules]).execute()

    sb.table("scheme_documents").delete().eq("scheme_id", args.scheme_id).execute()
    if ex.documents:
        sb.table("scheme_documents").insert([{
            "scheme_id": args.scheme_id,
            "name": d.name,
            "requirement_type": d.requirement_type,
            "notes": d.notes,
        } for d in ex.documents]).execute()

    # 3) where the data came from, and when
    sb.table("scheme_sources").upsert({
        "scheme_id": args.scheme_id,
        "url": args.url,
        "title": source_title,
        "fetched_at": now,
        "content_hash": digest,
    }, on_conflict="scheme_id,url").execute()


# ---------------------------------------------------------------------------
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--scheme-id", required=True)
    p.add_argument("--url", required=True)
    p.add_argument("--jurisdiction", required=True, choices=["central", "state_ut", "local"])
    p.add_argument("--state", default=None, help="required for state_ut schemes")
    p.add_argument("--dry-run", action="store_true", help="extract and validate, do not write")
    p.add_argument("--force", action="store_true", help="re-extract even if the page is unchanged")
    p.add_argument("--ocr", action="store_true", help="transcribe an official PDF with Gemini")
    args = p.parse_args()

    try:
        if args.jurisdiction == "state_ut" and not args.state:
            raise IngestError("--state is required when --jurisdiction is state_ut")

        print(f"[1/4] Fetching {args.url}")
        if args.ocr:
            pdf_bytes, title = fetch_pdf(args.url)
            text = transcribe_pdf(pdf_bytes)
            print(
                "WARNING: Text came from AI transcription of a scanned document. "
                "Check every rule against the original PDF before relying on this record."
            )
        else:
            text, title = fetch_text(args.url)
        digest = content_hash(text)

        sb = None if args.dry_run else get_supabase()
        if sb and not args.force:
            existing = (sb.table("scheme_sources").select("content_hash")
                        .eq("scheme_id", args.scheme_id).eq("url", args.url).execute().data)
            if existing and existing[0]["content_hash"] == digest:
                sb.table("scheme_sources").update(
                    {"fetched_at": datetime.now(timezone.utc).isoformat()}
                ).eq("scheme_id", args.scheme_id).eq("url", args.url).execute()
                print("Page unchanged since last ingestion. Updated fetched_at only. Use --force to redo.")
                return 0

        errors: list[str] = []
        ex = None
        structural: list[str] = []
        grounding: list[str] = []
        for attempt in range(1, MAX_ATTEMPTS + 1):
            print(f"[2/4] Extracting with Gemini (attempt {attempt}/{MAX_ATTEMPTS})")
            ex = call_gemini(build_prompt(args.url, text, errors))
            print("[3/4] Validating")
            structural, grounding = validate(ex, text)
            errors = structural + grounding
            if not errors:
                break
            print("  problems found:\n  - " + "\n  - ".join(errors))

        if structural:
            raise IngestError("Still invalid after retries. Nothing was saved.")
        status = "active" if not grounding else "unverified"
        if grounding:
            print("WARNING: some rules could not be matched to exact source text. "
                  "Saving as 'unverified'. Check them by hand against the official page.")

        if args.dry_run:
            print(json.dumps(ex.model_dump(), indent=2, ensure_ascii=False))
            print(f"\nDRY RUN: would save as status='{status}'. Nothing written.")
            return 0

        print("[4/4] Saving to Supabase")
        save(sb, args, ex, status, title, digest)
        print(f"Saved '{ex.name}' as {status}: {len(ex.rules)} rules, {len(ex.documents)} documents.")
        return 0
    except IngestError as exc:
        print(f"ERROR: {exc}")
        return 1
    except requests.RequestException as exc:
        print(f"ERROR fetching page: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())