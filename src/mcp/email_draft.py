"""File-backed email DRAFT adapter (architecture §5.6).

Writes output/email-draft.md with a subject line and a body (weekly pulse +
fee snippet). There is intentionally **no send function**, no SMTP, and no
Gmail integration anywhere in this module.
"""

from __future__ import annotations

from pathlib import Path

from src.models import McpPayload

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"
DEFAULT_DRAFT_PATH = OUTPUT_DIR / "email-draft.md"


def _subject(payload: McpPayload) -> str:
    label = (
        payload.identified_fee_issue
        if payload.identified_fee_issue and payload.identified_fee_issue != "none"
        else payload.date.isoformat()
    )
    return f"Weekly Product Pulse + Customer Clarification — {label}"


def create_email_draft(
    payload: McpPayload, path: Path | str = DEFAULT_DRAFT_PATH
) -> dict:
    """Write the email draft file. Returns {ok, location}. Never sends."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    bullets = "\n".join(f"- {b}" for b in payload.explanation_bullets)
    links = "\n".join(f"- {u}" for u in payload.source_links)
    body_parts = [payload.weekly_pulse.strip()]
    if payload.identified_fee_issue and payload.identified_fee_issue != "none":
        snippet = f"### Fee clarification: {payload.identified_fee_issue}"
        if bullets:
            snippet += f"\n\n{bullets}"
        if links:
            snippet += f"\n\nSources:\n{links}"
        body_parts.append(snippet)

    content = (
        f"Subject: {_subject(payload)}\n\n"
        "> DRAFT — not sent. Review before sending.\n\n"
        + "\n\n".join(body_parts)
        + "\n"
    )
    target.write_text(content, encoding="utf-8")
    return {"ok": True, "location": str(target)}
