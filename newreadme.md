# BenefitBridge — Small Business Benefit Navigator (MVP)

A full-stack web app that helps small business owners in India discover government schemes that **may** fit their business.
A user builds a profile → a **deterministic, rules-based** matcher compares it with a small curated catalogue → the app shows
ranked results with reasons, missing details, a document checklist and **official links** → an assistant answers questions
grounded in the catalogue's source notes (with a clearly labelled demo mode when no AI is configured).

> BenefitBridge is an independent information tool, **not** a government website. Matches are indicative, not eligibility decisions.
> The catalogue is **small and limited** (4 records) and must be re-verified by a human before any real-world use (see *Known limitations*).

## Stack and layout

| Part | Choice | Why |
|---|---|---|
| Backend | Python 3.10+, **Flask**, stdlib `unittest` | Minimal dependencies; typed dataclasses; JSON-file catalogue |
| Frontend | Dependency-free native **ES modules**, no framework | Builds and tests with plain Node, no `npm install` needed |
| Data | `data/schemes.json` + `data/documents/*.md` | Replaceable repository and retriever interfaces |

```
backend/   app/ (routes, matching, catalogue, validation, retrieval, ai_service, checklist) · tests/ · run.py
frontend/  src/ (index.html, styles.css, js/…) · scripts/ (dev server, build) · tests/
data/      schemes.json (seed catalogue) · documents/ (source notes used for retrieval)
e2e/       optional Playwright journey test
```

## Prerequisites
Python 3.10+, Node 18+ (22 tested). Nothing else is required to run or test.

## Run locally
```bash
# 1) Backend  (http://127.0.0.1:8000)
cd backend
python3 -m venv .venv && source .venv/bin/activate      # optional
pip install -r requirements.txt
cp .env.example .env                                     # optional; the app runs with no keys
python run.py

# 2) Frontend dev server  (http://127.0.0.1:5173, proxies /api to the backend)
cd frontend
npm run dev
```
Open **http://127.0.0.1:5173**, click **Use sample profile**, then **Find relevant schemes**.
Production-style build: `cd frontend && npm run build && npm run preview` (serves `dist/` on http://127.0.0.1:4173).
Use `BACKEND_URL=http://host:port npm run dev` if the backend is elsewhere.

## Test
```bash
cd backend  && python3 -m unittest discover -s . -t . -p "test_*.py"    # 66 tests (pytest also works if installed)
cd frontend && npm test && npm run build                                   # 8 tests + build validation
```
**End-to-end check (optional)**: with both servers up (`npm run preview` on 4173), run
`NODE_PATH=<global node_modules> node e2e/e2e.cjs` (needs `playwright` + Chromium). It walks validation errors →
sample profile → matches → filters → scheme detail → checklist → assistant demo mode.

"Build" here means: syntax-check every module, verify imports resolve, scan for secrets/AI-provider URLs, copy to `dist/`.
There is no bundler because there are no dependencies.

## API
| Endpoint | Purpose |
|---|---|
| `GET /api/health` | `{status, ai_configured, catalogue_count}` |
| `GET /api/schemes` | List/filter (`state_ut`, `jurisdiction`, `support_type`, `status`, `q`, `include_inactive=true`) |
| `GET /api/schemes/{id}` | `{scheme, freshness, catalogue_notice}`; `404` if unknown |
| `GET /api/schemes/{id}/checklist` | Items labelled Required / Conditional / Confirm with official source |
| `POST /api/eligibility/match` | Profile → `{recommendations, not_likely, historical, ranking_note, catalogue_notice, profile_used}` |
| `POST /api/assistant/ask` | `{question, scheme_id?, profile?}` → `{answer, citations, uncertainty_note, mode, …}` |
| `GET /api/demo/profile` | Fictional sample profile |
| `GET /api/meta/options` | Enum lists for the form (addition to the suggested API) |

Errors are always `{error: {code, message, fields?}}`. Each response carries an `X-Request-ID`.

**Matching (L3).** Each criterion is `met` / `not_met` / `unknown` (missing data is always `unknown`; “Other”, “I'm not sure” answers are `unknown`).
Only criteria marked `mandatory` decide the status: any `not_met` → `unlikely_to_qualify`; else any `unknown` → `needs_more_information`; else `potential_match`.
Supporting (non-mandatory) criteria are shown but never change the status. There is no numeric score.
`recommendations` holds potential/needs-info schemes; `unlikely_to_qualify` schemes are returned separately in `not_likely`
(so “no likely matches” is a genuine empty list); expired/withdrawn/unverified records appear only in `historical`.

## AI integration boundary (manual step)
All AI code lives in **`backend/app/ai_service.py`** — the only file with `TODO(manual)` markers, and the only place a provider may be called.
Implemented: `answer_scheme_question(question, context_chunks) -> AssistantAnswer`, question validation, no-context fallback,
a deterministic excerpt-only demo answer, output schema validation, and a **citation allow-list** (citations are rebuilt from retrieval metadata; unknown URLs are rejected).
**Not implemented (by design): the live provider call.** To finish it:
1. Implement `_call_provider` (timeout → `AITimeoutError`, provider errors → `AIProviderError`, no auto-retry, never log prompts or keys).
2. Set `PROVIDER_IMPLEMENTED = True`, set `AI_API_KEY` and `AI_MODEL` in `backend/.env`.
3. `/api/health` then reports `ai_configured: true` (it needs both the flag and the key).

Without it: no relevant text → `200` with the specified “couldn’t verify” message and no citations; relevant text but AI not configured →
`503 ai_not_configured` whose body includes a `fallback` of labelled source excerpts, which the UI displays. Matching, browsing, checklists and links are unaffected.

## Adding or updating schemes / documents
- Add records to `data/schemes.json`. Active records need a stable ID, jurisdiction, verification date, structured eligibility and **https official URLs on an allowed domain** (`OFFICIAL_DOMAIN_SUFFIXES`). A record that fails validation is loaded as `unverified` and never recommended; problems are logged.
- To deactivate: set `scheme_status` to `expired`, `withdrawn` or `unverified`.
- Records older than `REVIEW_WINDOW_DAYS` (default 90) are labelled “Needs re-verification” (a product warning, not a government expiry).
- Retrieval documents: Markdown with front matter (`scheme_id, title, url, verified`) split on `## ` headings, or text-based PDFs with a `<name>.pdf.json` sidecar. A document is indexed only if its `scheme_id` exists and its `url` is one of that scheme's official URLs; scanned PDFs with no text are reported, not indexed.

## Assumptions
- Stack chosen by the implementer (the spec allows it); no persistence beyond the JSON catalogue. Profiles are **never stored server-side**; the browser keeps them in `sessionStorage` for the tab and clears them on reset.
- Added profile field `business_type_other` and the business type “Street vending / hawking” (needed to express PM SVANidhi's mandatory criterion). Scheme records gain `conditions_to_confirm` (criteria with no profile field, e.g. age or residence history) and `review_notes`.
- The assistant's retrieval is a small keyword/BM25-style index behind a replaceable `Retriever` interface (no embeddings, to stay dependency-free).
- Nice-to-haves (PDF export, comparison view, second language, admin UI) are not built; checklist copy and `.txt` download are.
- The “low-income assistance” need is selectable, but no dedicated low-income programme is seeded; PM SVANidhi (street vendors) is the closest seeded record.

## Known limitations
- **Seed data needs human verification.** The 4 records were curated from official-domain pages (myScheme, KVIC/state DIC, MUDRA, TIIC, Tamil Nadu government, PM SVANidhi portal) located by web search on 2026-10-31. Some pages (e.g. myScheme) are script-rendered and could only be read as search excerpts, and the retrieval notes in `data/documents/` are **curator paraphrases, not official extracts**. Where sources disagreed (NEEDS subsidy ceiling, SVANidhi tranche amounts) the figure is omitted and the record is `possibly_changed`. Document lists are mostly `confirm` items for the same reason. Replace the notes with real official extracts before any real use.
- Eligibility facts that depend on fields the profile doesn't collect (age, residence history, first-generation status, special category) are listed under “conditions to confirm”, never inferred. The matcher therefore says “potential match”, never “eligible”.
- No authentication or rate limiting (not required for the MVP; add before public deployment). CORS is limited to `FRONTEND_ORIGIN`.
- The frontend CSP only allows the dev/preview origin plus a backend on `127.0.0.1:8000`/`localhost:8000`; edit `connect-src` in `frontend/src/index.html` if you host the API elsewhere.
- Not verified here: a live AI provider (unimplemented), ingestion of a real text-based PDF (only the no-text case is tested), and non-Chromium browsers.

## Troubleshooting
- **Page loads but “Backend unavailable”**: start the backend (`python run.py`) and check `BACKEND_URL`. The UI keeps your profile and offers Retry.
- **`localhost` refused, `127.0.0.1` works**: the servers bind IPv4 loopback; use `http://127.0.0.1:…`.
- **CORS error with a separate API origin**: add the frontend origin to `FRONTEND_ORIGIN` (comma-separated) and set `window.BENEFITBRIDGE_API_BASE` in `frontend/src/config.js`.
- **“Scheme information is temporarily unavailable”**: `DATA_PATH` is wrong or `schemes.json` is malformed; check the backend log.
- **Ingestion warnings at startup**: a document failed review (unknown scheme, non-official URL, missing metadata, or no extractable text); the log names the file.

## Acceptance criteria coverage
AC1–AC20 are exercised by `backend/tests/test_api.py`, `test_matching.py`, `test_catalogue.py`, `test_ai_service.py`, `test_retrieval.py`, the frontend tests and the E2E script
(AC16/AC20 UI notices are asserted in the E2E script). AC21–AC23 apply after the manual AI integration and are not testable until `_call_provider` exists
(AC21's mechanism and the citation/validation path are tested with a stubbed provider).
