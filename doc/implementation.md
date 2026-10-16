# Implementation guide: Review Insights

**Source of truth:** `doc/architecture.md` (behavior: `doc/PRD.md`)  
**How to use with Cursor:** one phase per chat (or one prompt per phase). Finish the **Done when** checklist before starting the next phase. Do not skip ahead.

---

## How to brief Cursor each phase

Paste this header, then paste the **Cursor prompt** for that phase:

```text
You are implementing Review Insights, a class-demo app.
Follow doc/architecture.md and doc/PRD.md.
Implement ONLY this phase. Do not start later phases.
Do not add auth, scraping, email send, Notion/Gmail live APIs, or extra features.
Stack is locked in this file (section: Stack lock).
After coding, verify the phase "Done when" checklist.
```

If a phase is already done, tell Cursor: “Phase N is complete. Start Phase N+1.”

---

## Stack lock

Do not reopen this unless the human explicitly changes it.

| Choice | Value |
| --- | --- |
| Language | Python 3.11+ |
| API | FastAPI |
| UI | Single-page HTML + vanilla JS served by FastAPI (`src/ui/`) |
| Models | Pydantic v2 |
| LLM | OpenAI-compatible chat + JSON schema (`OPENAI_API_KEY`, optional `OPENAI_BASE_URL` / `OPENAI_MODEL`) |
| MCP (demo) | File adapters only: `output/notes.md`, `output/email-draft.md` |
| Persistence | JSON run files under `output/runs/` — no database |
| Secrets | `.env` (gitignored); never commit keys |

Layout (from architecture §7):

```text
review-insights/
  doc/
  data/reviews.csv
  config/sources.json
  src/
    ui/
    intelligence/
    generate/
    mcp/
    models.py
    orchestrator.py
    main.py
  output/
  tests/
  README.md
  requirements.txt
  .env.example
```

---

## Phase map

| Phase | Name | Depends on | Demo value |
| --- | --- | --- | --- |
| 0 | Scaffold + contracts | — | Repo runs |
| 1 | CSV ingest | 0 | Load reviews |
| 2 | Review intelligence | 1 | Themes, quotes, fee |
| 3 | Pulse + explainer + validators | 2 | Two artifacts |
| 4 | Orchestrator + run state | 1–3 | One Run button path (API) |
| 5 | Approval gate + MCP files | 4 | Approve / Reject |
| 6 | Wizard UI | 4–5 | 3-minute demo |
| 7 | README, sample data, polish | 6 | Deliverables |

Optional later (not required for class): live Gmail draft / Notion. Only after Phase 7.

---

## Phase 0 — Scaffold and contracts

**Goal:** Empty app boots. Shared types exist. Folders match architecture.

**Build**

- `requirements.txt`: fastapi, uvicorn, pydantic, python-dotenv, httpx (or openai SDK), pytest
- `src/models.py`: all objects in architecture §6.2 (`Review`, `Theme`, `IntelligenceResult`, `WeeklyPulse`, `FeeExplainer`, `McpPayload`, `ToolLog`, `Run` + run `status` enum)
- `src/main.py`: FastAPI app, `GET /health`
- `config/sources.json`: 4–6 placeholder official Groww/help/regulator URLs (real URLs preferred; labels + url)
- `data/reviews.csv`: header + ~15–30 **synthetic but realistic** Groww-style reviews, including several that mention **one** fee confusion (e.g. exit load / account opening / AMC) so later phases have signal
- `.env.example`, `.gitignore` (`output/`, `.env`, `__pycache__/`)
- `output/.gitkeep`

**Do not** call the LLM, build UI, or write MCP files yet.

**Done when**

- `uvicorn src.main:app` serves `/health` → `{ "ok": true }`
- Pydantic models match architecture field names
- CSV has `review_id,text,rating,date,source`

### Cursor prompt — Phase 0

```text
Phase 0 only.
Create the repo scaffold from doc/implementation.md (Stack lock + Phase 0) and doc/architecture.md §6–7.
Add Pydantic models for every in-run object.
Add FastAPI GET /health.
Add data/reviews.csv with 15–30 Groww-like reviews over ~8–12 weeks; several must mention the same fee/charge confusion (grounded, not a one-off).
Add config/sources.json with 4–6 official-looking source URLs.
No LLM, no UI, no MCP writes.
```

---

## Phase 1 — CSV ingest

**Goal:** Turn a CSV path or upload into a list of `Review`. Empty text dropped. Missing `review_id` → row index.

**Build**

- `src/intelligence/ingest.py`: `load_reviews(path | file-like) -> list[Review]`
- `POST /api/reviews/preview` (optional but useful): returns count + first 5 rows
- Tests: empty rows skipped; id synthesis; UTF-8

**Do not** cluster or call LLM.

**Done when**

- Loading `data/reviews.csv` returns ≥15 reviews
- Each review has `id` and non-empty `text`

### Cursor prompt — Phase 1

```text
Phase 1 only.
Implement CSV ingest per doc/architecture.md stage 1 and §6.1.
Function: load_reviews → list[Review].
Drop empty text. Synthesize review_id from row index if missing.
Add a small pytest. Wire a minimal preview endpoint if it helps.
Do not cluster, generate, or write MCP.
```

---

## Phase 2 — Review intelligence

**Goal:** ≤5 themes, top 3, 3 verified quotes, 1 fee issue or `null`. Quotes must be substrings of cited reviews.

**Build**

- `src/intelligence/cluster.py` (or `analyze.py`): LLM JSON call
- Prompt: cluster, rank, extract 3 verbatim quotes with `review_id`, at most one `fee_issue` with `evidence_review_id`. If none, `null`.
- `src/intelligence/verify.py`: quote ⊆ review text (case-insensitive, whitespace-normalized). Drop/replace invalid quotes. If fee evidence fails, set `fee_issue = null` — **never invent**.
- If CSV is large, send a sample (e.g. all 1–2★ + sample of rest) but keep ids stable.
- `OPENAI_*` from env. If key missing, raise a clear error (no silent fake themes in this phase — a **fixture JSON** for tests is OK).
- Tests with a mocked LLM response that includes a bad quote (must be stripped) and a valid fee evidence (must keep).

**Do not** write pulse/explainer or MCP.

**Done when**

- `analyze_reviews(reviews) -> IntelligenceResult`
- `len(themes) ≤ 5`, `len(top_themes) == 3` (or fewer if too little data)
- 3 quotes each pass substring check **or** fewer after verification
- Fee either grounded or `null`

### Cursor prompt — Phase 2

```text
Phase 2 only.
Implement review intelligence (architecture §5.3, stages 1–2).
LLM structured JSON: max 5 themes, top 3, 3 quotes with review_id, optional single fee_issue with evidence_review_id.
Server-side verify quotes are substrings of the cited review; never invent a fee.
Add pytest with a mocked LLM. No pulse, explainer, UI, or MCP.
```

---

## Phase 3 — Pulse, explainer, constraint checks

**Goal:** Two artifacts with hard limits. Explainer uses **only** `fee_issue` + allowlisted URLs.

**Build**

- `src/generate/pulse.py`: ≤250 words; sections: top themes, 3 quotes, key observation, 3 action ideas. Return `WeeklyPulse`.
- `src/generate/explainer.py`: if `fee_issue` is null, return `None`. Else ≤6 facts-only bullets; pick **2** URLs from `config/sources.json` only; `last_checked` set by caller (today), not the model.
- `src/generate/validate.py`: word count, theme count, bullet count, source allowlist. Pulse: 1 automatic regenerate if >250 words, then fail.
- Export helper: write `output/weekly-pulse.md` when asked (orchestrator can call this in Phase 4).

**Done when**

- Pulse word_count ≤ 250 after validate
- Explainer bullets ≤ 6 and both links ∈ allowlist
- Null fee → no explainer, no hallucinated fee

### Cursor prompt — Phase 3

```text
Phase 3 only.
Implement pulse writer, fee explainer, and validators (architecture §5.4, stages 3–5).
Pulse ≤250 words with required sections. Explainer ≤6 bullets, facts-only, 2 links from config/sources.json only, last_checked from orchestrator date.
If fee_issue is null, skip explainer.
One auto-regenerate if pulse too long, then error.
Pytest with mocked LLM. Do not build orchestrator UI or MCP yet; you may add thin functions the orchestrator will call.
```

---

## Phase 4 — Orchestrator and run state

**Goal:** One `start_run` executes stages 1–6 (through preview). Persist run JSON. **No MCP writes.**

**Build**

- `src/orchestrator.py`:
  - `start_run(csv_path) -> Run`
  - status: `ingesting` → `ready_for_approval` | `failed`
  - attach intelligence, pulse, explainer, `mcp_payload`
  - save `output/runs/{run_id}.json` and `output/weekly-pulse.md`
- Payload fields exactly as architecture §5.6; if no fee, `identified_fee_issue` / bullets / links = `"none"` or empty lists (pick one, document it, be consistent)
- API:
  - `POST /api/runs` (multipart CSV or `{ "use_sample": true }`)
  - `GET /api/runs/{run_id}`
- In-memory current run + disk snapshot

**Do not** implement Approve yet (stub endpoint returning 409 is OK).

**Done when**

- Sample CSV → `ready_for_approval` with payload previewable via GET
- LLM failure → `failed`, CSV still loadable, client can retry
- `output/notes.md` and `output/email-draft.md` **unchanged** after a run

### Cursor prompt — Phase 4

```text
Phase 4 only.
Implement the orchestrator (architecture §5.2, stages 1–6).
start_run loads CSV, intelligence, pulse, explainer, validates, builds mcp_payload, persists output/runs/{id}.json.
Status ready_for_approval or failed. No MCP adapter calls.
POST /api/runs and GET /api/runs/{id}.
Do not implement approve/reject writes yet.
```

---

## Phase 5 — Approval gate and file MCP

**Goal:** Side effects only after Approve. Reject is a no-op. Email adapter cannot send.

**Build**

- `src/mcp/notes.py`: `append_notes(payload) -> { ok, location }` append a dated block to `output/notes.md`
- `src/mcp/email_draft.py`: write `output/email-draft.md` with subject `Weekly Product Pulse + Customer Clarification — {date or fee name}` and body = pulse + explainer snippet. **No send function. No SMTP. No Gmail.**
- `src/mcp/gate.py`: only if `status == ready_for_approval` and decision is APPROVE; lock; call notes then email; append `tool_logs`; set `mcp_committed_at`; status `approved`. Reject → `rejected`, no file writes.
- Idempotent: second approve does not double-append (same `run_id`)
- Partial failure: log which tool failed; allow retry of failed tool only
- API: `POST /api/runs/{id}/approve`, `POST /api/runs/{id}/reject`

**Done when**

- Approve creates/updates notes + draft; GET run shows logs
- Reject leaves those files untouched (test with a copy or mtime)
- Approve before `ready_for_approval` → 409
- Double approve → no duplicate block

### Cursor prompt — Phase 5

```text
Phase 5 only.
Implement approval-gated MCP file adapters (architecture §5.5–5.6, stages 7–8).
append_notes → output/notes.md; create_email_draft → output/email-draft.md; never send email.
Gate: Approve only from ready_for_approval; Reject is a no-op on files; idempotent by run_id.
POST /api/runs/{id}/approve and /reject. Tool logs on the Run.
Pytest the gate (temp output dir). No live Notion/Gmail. No UI yet unless a tiny curl example in comments.
```

---

## Phase 6 — Three-step wizard UI

**Goal:** Operator can demo in ≤3 minutes without curl.

**Build** (`src/ui/` + `GET /`)

1. **Load** — “Use sample CSV” and optional file upload; Run; loading/error state  
2. **Insights** — ≤5 themes, top 3 highlighted, 3 quotes, fee card or empty state, pulse + word count, explainer + bullet count, MCP JSON preview  
3. **Approve** — copy that Approve will append notes and create an email **draft** (not send); Reject; then tool log locations  

Wire only to existing APIs. UI must not call the LLM or write files itself.

**Done when**

- Full happy path in the browser  
- Constraint failure / LLM error visible  
- Reject path visible (no new notes block)

**Verify in the browser** (user rule): Load → Run → inspect fee vs a quote → Approve → open `output/notes.md` and `output/email-draft.md`. Repeat with Reject on a new run.

### Cursor prompt — Phase 6

```text
Phase 6 only.
Build the 3-step wizard UI (architecture §5.1 and §8 demo path).
Steps: Load CSV / sample → Insights (themes, quotes, fee, pulse, explainer, payload) → Approve/Reject with tool logs.
Serve at GET /. Call existing FastAPI routes only.
Show word/bullet counts and fee empty state.
Do not add auth, extra pages, or live Gmail/Notion.
Verify the happy path in the browser if tools allow; otherwise document exact click path.
```

---

## Phase 7 — README, sources, demo polish

**Goal:** Class deliverables. Classmate can rerun.

**Build**

- `README.md`: how to run (`venv`, `.env`, `uvicorn`), where MCP approval happens (UI step 3 + gate), **which fee the sample CSV is designed to surface** (actual run may vary with the model — say “expected signal”)
- Confirm `config/sources.json` has 4–6 real official URLs relevant to the likely fee
- `.env.example` with `OPENAI_API_KEY=`, `OPENAI_MODEL=`
- Ignore `output/*` except `.gitkeep`; optionally commit one **example** pulse in `doc/examples/` if useful — do not commit secrets
- Smoke: health, run, reject, approve

**Done when**

- README covers run, approval, fee, sources  
- Demo path in architecture §9 works cold from clone + API key  

### Cursor prompt — Phase 7

```text
Phase 7 only.
Write README.md and polish for a class demo (PRD deliverables).
Include: how to run, where MCP approval happens, fee issue expected from the sample reviews, source list.
Do not add new product features. Fix only gaps that block the demo path in architecture §9.
```

---

## Guardrails for every phase

Cursor must **not**:

- Send email or add a `send()` API  
- Call MCP adapters except through the gate  
- Invent quotes or fees when verification fails  
- Use URLs outside `config/sources.json` for the explainer  
- Add login, scraping, cron, or a database  
- Implement live Gmail/Notion before a human asks (post–Phase 7)

---

## Suggested Cursor session plan

| Session | Phases | Approx. outcome |
| --- | --- | --- |
| 1 | 0–1 | App + CSV |
| 2 | 2–3 | Insights + artifacts (API/tests) |
| 3 | 4–5 | Full pipeline + gate |
| 4 | 6–7 | UI + README, demo |

If the LLM key is missing in early sessions, keep pytest mocks; wire the real client in Phase 2/3 behind env.

---

## Quick test commands (after the matching phase)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest
uvicorn src.main:app --reload
```

- Phase 4: `POST /api/runs` with `{ "use_sample": true }`  
- Phase 5: `POST /api/runs/{id}/reject` then a new run + `/approve`  
- Phase 6: open `http://127.0.0.1:8000/`
