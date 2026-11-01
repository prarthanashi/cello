# BenefitBridge — Small Business Benefit Navigator (MVP)

A full-stack web app that helps small business owners in India discover government schemes that **may** fit their business.
A user builds a profile → a **deterministic, rules-based** matcher compares it with the Supabase scheme catalogue → the app shows
ranked results with reasons, missing details, a document checklist and **official links** → an assistant answers questions
grounded in scheme records and rule excerpts stored in Supabase (with a clearly labelled demo mode when no AI is configured).

> BenefitBridge is an independent information tool, **not** a government website. Matches are indicative, not eligibility decisions.
> Scheme records must be reviewed before any real-world use (see *Known limitations*).

## Stack and layout

| Part | Choice | Why |
|---|---|---|
| Backend | Python 3.10+, **Flask**, **Supabase**, stdlib `unittest` | Typed dataclasses; Supabase-backed catalogue |
| Frontend | Dependency-free native **ES modules**, no framework | Builds and tests with plain Node, no `npm install` needed |
| Data | Supabase `schemes`, `eligibility_rules`, `scheme_documents`, `scheme_sources` tables | Ingestion script and validated runtime loader |

```
backend/   app/ (routes, matching, catalogue, validation, retrieval, ai_service, checklist) · tests/ · run.py
frontend/  src/ (index.html, styles.css, js/…) · scripts/ (dev server, build) · tests/
e2e/       optional Playwright journey test
```

## Prerequisites
Python 3.10+, Node 18+ (22 tested), and a Supabase project with the four tables listed above.

## Run locally
```bash
# 1) Backend  (http://127.0.0.1:8000)
cd backend
python3 -m venv .venv && source .venv/bin/activate      # optional
pip install -r requirements.txt
# Create backend/.env and set SUPABASE_URL and SUPABASE_SECRET_KEY.
# For scheme ingestion, also set GEMINI_API_KEY and GEMINI_MODEL.
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
cd backend  && python3 -m unittest discover -s . -t . -p "test_*.py"    # 69 tests (pytest also works if installed)
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

## Adding or updating schemes
- Run the standalone ingester from `backend/` once per scheme: `python ingest_schemes.py --scheme-id <stable-id> --url <official-https-url> --jurisdiction central`. For a state scheme, use `--jurisdiction state_ut --state "Tamil Nadu"`. Add `--dry-run` to fetch, extract and validate without writing.
- The ingester writes the scheme, eligibility rules, required documents, and source URL/fetch metadata to Supabase. It retries Gemini extraction with Python validation errors; records with ungrounded rule quotes are saved as `unverified`.
- The Flask app does not run ingestion. It reads the four Supabase tables at startup; restart it to load database changes.
- To deactivate: set `scheme_status` to `expired`, `withdrawn` or `unverified` in the `schemes` table.
- Records older than `REVIEW_WINDOW_DAYS` (default 90) are labelled “Needs re-verification” (a product warning, not a government expiry).

## Assumptions
- Profiles are **never stored server-side**; the browser keeps them in `sessionStorage` for the tab and clears them on reset.
- Added profile field `business_type_other` and the business type “Street vending / hawking” (needed to express PM SVANidhi's mandatory criterion). Scheme records gain `conditions_to_confirm` (criteria with no profile field, e.g. age or residence history) and `review_notes`.
- The assistant's retrieval is a small keyword/BM25-style index over scheme fields and grounded rule excerpts loaded from Supabase.
- Nice-to-haves (PDF export, comparison view, second language, admin UI) are not built; checklist copy and `.txt` download are.

## Known limitations
- Supabase records still require review before real-world use. Extraction is constrained to one fetched page; the app does not browse source websites. Verify every record and its official URL before relying on it.
- Eligibility facts that depend on fields the profile doesn't collect (age, residence history, first-generation status, special category) are listed under “conditions to confirm”, never inferred. The matcher therefore says “potential match”, never “eligible”.
- No authentication or rate limiting (not required for the MVP; add before public deployment). CORS is limited to `FRONTEND_ORIGIN`.
- The frontend CSP only allows the dev/preview origin plus a backend on `127.0.0.1:8000`/`localhost:8000`; edit `connect-src` in `frontend/src/index.html` if you host the API elsewhere.
- Not verified here: a live AI provider (unimplemented), ingestion of a real text-based PDF (only the no-text case is tested), and non-Chromium browsers.

## Troubleshooting
- **Page loads but “Backend unavailable”**: start the backend (`python run.py`) and check `BACKEND_URL`. The UI keeps your profile and offers Retry.
- **`localhost` refused, `127.0.0.1` works**: the servers bind IPv4 loopback; use `http://127.0.0.1:…`.
- **CORS error with a separate API origin**: add the frontend origin to `FRONTEND_ORIGIN` (comma-separated) and set `window.BENEFITBRIDGE_API_BASE` in `frontend/src/config.js`.
- **“Scheme information is temporarily unavailable”**: confirm `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, and access to all four catalogue tables; check the backend log.

## Acceptance criteria coverage
AC1–AC20 are exercised by `backend/tests/test_api.py`, `test_matching.py`, `test_catalogue.py`, `test_ai_service.py`, `test_retrieval.py`, the frontend tests and the E2E script
(AC16/AC20 UI notices are asserted in the E2E script). AC21–AC23 apply after the manual AI integration and are not testable until `_call_provider` exists
(AC21's mechanism and the citation/validation path are tested with a stubbed provider).