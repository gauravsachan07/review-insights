"""File-backed notes adapter (architecture §5.6).

Appends a dated Markdown block to output/notes.md. This is a side-effecting
tool and must only be reached through the approval gate.
"""

from __future__ import annotations

from pathlib import Path

from src.models import McpPayload

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"
DEFAULT_NOTES_PATH = OUTPUT_DIR / "notes.md"


def _block(payload: McpPayload) -> str:
    themes = "; ".join(payload.top_themes) or "none"
    bullets = "\n".join(f"  - {b}" for b in payload.explanation_bullets) or "  - none"
    links = "\n".join(f"  - {u}" for u in payload.source_links) or "  - none"
    return (
        f"\n## Review Insights — {payload.date.isoformat()}\n\n"
        f"- **Top themes:** {themes}\n"
        f"- **Identified fee issue:** {payload.identified_fee_issue}\n"
        f"- **Explanation bullets:**\n{bullets}\n"
        f"- **Sources:**\n{links}\n"
        f"- **Weekly pulse:**\n\n{payload.weekly_pulse}\n\n---\n"
    )


def append_notes(
    payload: McpPayload, path: Path | str = DEFAULT_NOTES_PATH
) -> dict:
    """Append the payload as a dated block. Returns {ok, location}."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as fh:
        if target.stat().st_size == 0:
            fh.write("# Review Insights — Notes\n")
        fh.write(_block(payload))
    return {"ok": True, "location": str(target)}
