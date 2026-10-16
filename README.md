# Review Insights

A class-demo prototype that turns a CSV of app-store reviews into grounded
product insights and two communication artifacts, then writes them **only after
a human approves**.

One CSV in → clustered themes, verbatim quotes, and at most one fee/charge
confusion detected → a weekly pulse and a facts-only fee explainer → a preview
of the MCP payload → **Approve** (writes notes + email draft) or **Reject**
(no side effects).

- No login, no scraping, no database, no email sending.
- Quotes are verified to be substrings of the CSV rows they cite.
- The explainer uses only URLs from `config/sources.json`.

See `doc/architecture.md` (design) and `doc/PRD.md` (requirements).

---

## Requirements

- Python 3.11+
- An OpenAI-compatible API key (for review intelligence and the writers)

## Setup

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file (gitignored) from `.env.example`:

```ini
OPENAI_API_KEY=sk-...
# Optional — for an OpenAI-compatible gateway:
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_MODEL=gpt-4o-mini
```

If `OPENAI_API_KEY` is missing, a run fails cleanly with a clear error and the
CSV stays loadable so you can fix the key and click **Run** again.

### Free / local model options (no credits needed)

The LLM client only needs an OpenAI-compatible endpoint, so any of these work.
Set **all three** values in `.env` (replace the existing lines — don't
duplicate keys like `OPENAI_MODEL=OPENAI_MODEL=...`).

**A. Ollama — local, fully offline, free**

```bash
# install from https://ollama.com/download, then:
ollama pull qwen2.5:7b
```

```ini
OPENAI_API_KEY=
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=qwen2.5:7b
```

(Ollama must be running: it starts with the installer / `ollama serve`.
`ollama list` shows valid model names. The API key is optional for local
servers.)

**B. Groq — free tier, hosted open models (Llama)**

Get a free key at <https://console.groq.com>, then:

```ini
OPENAI_API_KEY=gsk_...
OPENAI_BASE_URL=https://api.groq.com/openai/v1
OPENAI_MODEL=llama-3.3-70b-versatile
```

**C. OpenRouter — free open-model tier**

Key: <https://openrouter.ai/keys>, then:

```ini
OPENAI_API_KEY=sk-or-...
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=meta-llama/llama-3.3-70b-instruct:free
```

The client automatically falls back from `json_schema` → `json_object` → plain
JSON-with-schema-in-prompt, so servers that only partially support structured
outputs still work.

## Run

```bash
uvicorn src.main:app --reload
```

Open <http://127.0.0.1:8000/>. Health check: `GET /health` → `{"ok": true}`.

## Demo path (~3 minutes)

1. **Load** → keep “Use sample CSV” (or upload your own
   `review_id,text,rating,date,source`) → **Run analysis**.
2. **Insights** → review the ≤5 themes (top 3 highlighted), the 3 verified
   quotes, the fee card, the weekly pulse (word count) and the fee explainer
   (bullet count), plus the MCP payload JSON preview.
3. **Continue to approval** → read the notice → **Approve** or **Reject**.
4. On **Approve**, the **Written files** card shows **View** / **Download** links
   for `output/notes.md` (appended, dated block) and `output/email-draft.md`
   (a draft — never sent). Tool-log locations appear in the UI.
5. Optional: start a **new run** and **Reject** to prove no files are written.

## Where the MCP approval happens

- UI: **Step 3 — Approve** (`src/ui/`). The copy states the side effects before
  the click.
- Gate: `src/mcp/gate.py`. Adapters are reachable *only* from here, and only
  when `status == ready_for_approval`. Reject is a no-op on files. The gate is
  idempotent per `run_id`, and a failed adapter is retried without repeating the
  successful one.

MCP adapters (file-backed demo defaults):

| Adapter | Writes | Live option (not built) |
| --- | --- | --- |
| `append_notes` | appends a dated block to `output/notes.md` | Notion / Google Doc |
| `create_email_draft` | `output/email-draft.md` (subject + body) | Gmail `drafts.create` |

There is deliberately **no `send()`** anywhere in the codebase.

## Expected fee signal in the sample data

The sample `data/reviews.csv` (21 synthetic Groww-style reviews over ~10 weeks)
is designed to surface **one** recurring fee confusion: **exit load on early
redemption of a mutual fund** (about 6 reviews, e.g. R002, R004, R006, R009,
R012, R019). This is the *expected signal* — the actual output depends on the
model, and the pipeline may legitimately return `fee_issue: null` if it cannot
ground the fee in a quote. It never invents one.

## Source list (explainer allowlist)

`config/sources.json` (real, verified URLs; the model picks 2):

1. Groww — What is Exit Load in Mutual Funds — <https://groww.in/p/exit-load-in-mutual-funds>
2. Groww — Mutual Funds — <https://groww.in/mutual-funds>
3. Groww Help — <https://groww.in/help>
4. AMFI — <https://www.amfiindia.com/>
5. SEBI — <https://www.sebi.gov.in/>
6. SEBI — Investor Education — <https://investor.sebi.gov.in/>

## Project structure

```text
review-insights/
  doc/                      architecture, PRD, implementation guide, examples
  data/reviews.csv          sample input
  config/sources.json       official URL allowlist
  src/
    ui/                     single-page wizard (index.html, app.js)
    intelligence/           ingest, cluster, verify, llm client
    generate/               pulse, explainer, validators
    mcp/                    gate, notes, email_draft (file adapters)
    models.py               Pydantic v2 in-run objects
    orchestrator.py         start_run (stages 1-6), run persistence
    main.py                 FastAPI app + routes
  output/                   runs/, notes.md, email-draft.md (gitignored)
  tests/                    pytest suite
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/` | 3-step wizard |
| GET | `/health` | `{"ok": true}` |
| POST | `/api/reviews/preview` | count + first 5 rows |
| POST | `/api/runs` | start a run (multipart `file` or `{"use_sample": true}`) |
| GET | `/api/runs/{id}` | run snapshot (status, artifacts, logs) |
| POST | `/api/runs/{id}/approve` | gate: writes notes + email draft |
| POST | `/api/runs/{id}/reject` | gate: no file writes |
| GET | `/api/runs/{id}/artifacts/notes` | view `notes.md` (after approval) |
| GET | `/api/runs/{id}/artifacts/email-draft?download=true` | view / download `email-draft.md` |

Only the two known artifacts are served, and only once the matching MCP tool
logged success for that run — there is no arbitrary file access.

Sample-run smoke test:

```bash
curl -X POST http://127.0.0.1:8000/api/runs \
  -H "Content-Type: application/json" -d '{"use_sample": true}'
```

## Safety rules (enforced in code)

- Quotes must be substrings of the cited review, or they are dropped.
- A fee issue whose evidence does not verify becomes `null` — never invented.
- The explainer may only use URLs from `config/sources.json`.
- Pulse strict limit is 250 words (one automatic regenerate, then fail).
- MCP adapters run only through the approval gate.
- Reject writes nothing; a second approve does not duplicate the notes block.

## Deploy (Render, free tier)

The repo ships a `Dockerfile` (single container, no database). Render's **Free**
compute plan ($0, no credit card) runs it with these caveats: it spins down
after 15 min idle (first request cold-starts ~1 min), and free services **cannot
attach a persistent disk**, so `output/` lives only while the instance runs —
download approved files during your session.

Steps:

1. Push the repo to GitHub (see below), then sign up at <https://render.com>.
2. **New → Web Service** → connect the repo. Render detects the `Dockerfile`.
3. Choose the **Free** compute plan.
4. **Environment** (from `console.groq.com` for a $0 LLM bill):

   | Key | Value |
   | --- | --- |
   | `OPENAI_API_KEY` | `gsk_...` |
   | `OPENAI_BASE_URL` | `https://api.groq.com/openai/v1` |
   | `OPENAI_MODEL` | `llama-3.3-70b-versatile` |

5. Deploy → open the URL → health check `GET /health`. Set the dashboard
   **health check path** to `/health` (optional).

The container listens on `0.0.0.0:$PORT` (Render sets `PORT`, default 10000).
Do **not** add a payment method — Render suspends free services instead of
billing if you exceed the included bandwidth (5 GB/month).

Run tests before pushing:

```bash
pytest
```

Covers ingest, verification (bad quote stripped, grounded fee kept), pulse
regeneration, explainer URL allowlisting, orchestrator failure/retry, the
approval gate (idempotency, reject no-op, partial-failure retry), and the UI
routes.

## Out of scope

Live Gmail/Notion adapters, auth, scraping, cron, databases, and multi-fee
explainers are intentionally excluded from this demo.
