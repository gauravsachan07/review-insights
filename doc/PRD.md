# PRD: Review Insights (Groww)

**Product:** Review Insights  
**Audience:** Class demo (Product + Support workflow simulation)  
**Source:** `doc/ProblemStatement.txt`  
**Status:** Draft for prototype  
**Last updated:** 2026-10-15

---

## 1. Problem

Product and Support teams receive raw app-store reviews but do not have a fast, repeatable way to:

1. Cluster recent feedback into a small set of themes.
2. Spot one recurring **fee/charge misunderstanding**.
3. Turn that signal into an **internal weekly pulse** and a **customer-safe explanation**.
4. Log and share the output in internal tools **only after a human approves**.

This demo simulates that workflow for **Groww** using a public reviews CSV (last 8–12 weeks).

---

## 2. Goal (demo)

Build a working prototype that takes a reviews CSV and produces:

| Output | Purpose |
| --- | --- |
| Theme clusters (max 5) + top 3 themes | Review intelligence |
| 3 real user quotes | Evidence |
| 1 fee/charge confusion | Insight → communication link |
| Weekly product pulse (≤250 words) | Internal Product note |
| Fee explainer (≤6 bullets, 2 official links, “Last checked:”) | Reusable Support snippet |
| Approval-gated MCP actions | Append to notes/doc + create email draft (no auto-send) |

**Success for class:** a ≤3-minute demo of insight → pulse → explainer → **approve** → doc append + email draft.

---

## 3. Users and jobs

| Persona | Job to be done |
| --- | --- |
| **Product manager** | See what users are talking about this week and get 3 action ideas. |
| **Support / comms** | Get a facts-only explanation of the fee users keep misunderstanding. |
| **Demo operator (student)** | Run the pipeline, inspect outputs, approve MCP writes. |

No login, roles, or multi-tenant product is required for the demo.

---

## 4. In scope / out of scope

### In scope

- One Groww reviews CSV as the only input.
- Clustering into **at most 5 themes**; surface **top 3**.
- Extract **3 real quotes** from the CSV (verbatim or lightly trimmed, not invented).
- Identify **one** recurring fee/charge confusion that is **grounded in the reviews** (not a canned scenario).
- Generate the weekly pulse and fee explainer to the assignment constraints.
- A **visible human approval step** before any write.
- After approval: append a structured record to a notes/doc, and create an **email draft** (not send).
- README covering run steps, where approval happens, which fee was identified, and a source list.

### Out of scope (demo)

- Live Play Store / App Store scraping.
- Auto-sending email.
- Multi-week scheduling / cron.
- Auth, billing, production MCP credentials beyond a demo path.
- More than one fee explainer per run.
- Full Support ticketing or CRM.
- Guaranteeing perfect clustering quality; “good enough + explainable” is the bar.

---

## 5. User flow (happy path)

1. Operator loads the reviews CSV (last 8–12 weeks).
2. System runs **Review Intelligence**:
   - clusters themes (≤5)
   - ranks top 3
   - pulls 3 quotes
   - flags 1 fee/charge confusion with supporting review evidence
3. System generates **Weekly Product Pulse** (≤250 words).
4. System generates **Fee Explainer** tied to that confusion (≤6 bullets, 2 official URLs, last-checked date).
5. UI shows both artifacts + proposed MCP payload.
6. Operator **approves** (or rejects / edits).
7. On approve:
   - append structured JSON-like record to Notes/Doc
   - create email draft with pulse + explainer snippet
8. Operator can copy/export pulse (MD) and screenshot draft + notes for deliverables.

**Reject path:** no document append, no draft created. Operator can regenerate or stop.

---

## 6. Functional requirements

### 6.1 Review intelligence

| ID | Requirement |
| --- | --- |
| RI-1 | Accept one public reviews CSV covering ~8–12 weeks. |
| RI-2 | Cluster reviews into **max 5** themes with short labels and (optional) volume/share. |
| RI-3 | Identify **top 3** themes by volume and/or severity signal. |
| RI-4 | Extract **3 real user quotes** attributable to reviews in the CSV. |
| RI-5 | Highlight **1 recurring fee/charge confusion** with at least one review evidence snippet. |
| RI-6 | If no fee confusion is found, show an explicit empty state (do not invent a fee). |

### 6.2 Weekly product pulse (internal)

| ID | Requirement |
| --- | --- |
| WP-1 | Generate a structured weekly note **≤250 words**. |
| WP-2 | Include: summary of top themes, the 3 quotes, one key observation, **3 action ideas**. |
| WP-3 | Tone: internal, concise, PM-readable. Export as Markdown. |

### 6.3 Fee explainer (customer-facing snippet)

| ID | Requirement |
| --- | --- |
| FE-1 | Explainer must address the **same** fee issue found in RI-5. |
| FE-2 | **≤6** bullet points; **neutral, facts-only** (no marketing, no legal overclaim). |
| FE-3 | Include **2 official source links** (Groww / regulator / help-center style). |
| FE-4 | Include line: `Last checked: YYYY-MM-DD`. |

### 6.4 MCP + approval gating

| ID | Requirement |
| --- | --- |
| MCP-1 | Show a clear **Approve / Reject** step **before** any side effect. |
| MCP-2 | On approve, append one record: `date`, `top_themes`, `weekly_pulse`, `identified_fee_issue`, `explanation_bullets`, `source_links`. |
| MCP-3 | On approve, create an **email draft** (no send): subject `Weekly Product Pulse + Customer Clarification — {date or fee name}`; body = pulse + fee snippet. |
| MCP-4 | Implementation may be Zapier/Make, LLM tool calling, or a **simulated** MCP (button + local/doc write) as long as gating is visible. |
| MCP-5 | Log success/failure of each tool call in the UI. |

---

## 7. Data

**Primary input:** `reviews.csv` (sample shipped with the repo).

Suggested columns (adapt if the sample differs): review text, rating, date, source (Play/App Store), optional review id.

**Derived objects (in-memory / run output):**

```text
themes[≤5] { name, summary, review_count }
top_themes[3]
quotes[3] { text, date?, rating? }
fee_issue { name, why_confused, evidence_quote }
weekly_pulse { markdown, word_count }
fee_explainer { bullets[≤6], source_links[2], last_checked }
mcp_payload { date, top_themes, weekly_pulse, identified_fee_issue, explanation_bullets, source_links }
```

---

## 8. UX (minimum for demo)

Single-page or 3-step wizard:

1. **Upload / load CSV** → run analysis  
2. **Insights + Pulse + Explainer** (read-only cards, word/bullet counts shown)  
3. **Approve MCP** → confirmation that notes were appended and draft was created  

Show word count on the pulse and bullet count on the explainer. Fail the generate step visually if constraints are exceeded (and retry).

---

## 9. Non-functional (class demo)

- **Time:** pipeline should finish in seconds-to-low-minutes on the sample CSV.  
- **Honesty:** quotes and fee issue must be traceable to the CSV.  
- **Safety:** never send email; never write tools without approval.  
- **Reproducibility:** README + sample CSV so a classmate can rerun.  
- **Stack:** any practical stack (Python/JS + LLM). Prefer a simple local UI over a production app.

---

## 10. Example (illustrative, not the required fee)

Reviews mention unexpected **exit load** → theme *Pricing confusion* → fee issue *exit load misunderstanding* → pulse + exit-load explainer → **approve** → notes append + Gmail/Notion (or simulated) draft.

The **actual** fee in the demo must come from **this** CSV’s themes, not this example.

---

## 11. Deliverables checklist

- [ ] Working prototype (link) **or** ≤3-min demo video  
- [ ] Weekly product pulse (MD / PDF / Doc)  
- [ ] Notes/Doc snippet showing the appended entry  
- [ ] Email draft screenshot or text  
- [ ] Reviews CSV sample  
- [ ] Source list (4–6 URLs)  
- [ ] README: how to run, where MCP approval happens, which fee was identified  

---

## 12. Skills this prototype must demonstrate

Insight extraction, theme clustering, insight → communication, controlled summarization, structured explanation, workflow orchestration, MCP tool calling with **approval gating**.

---

## 13. Open decisions (keep small)

| Decision | Default for demo |
| --- | --- |
| Clustering method | LLM-assisted clustering on sample CSV (no ML infra) |
| MCP backends | Simulated approval + local/Notion-like doc + draft file **or** real Gmail/Docs if time |
| UI | Local web app or notebook + simple approval button |
| Model | Any available LLM with structured output |
