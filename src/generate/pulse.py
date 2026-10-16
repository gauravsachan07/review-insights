"""Weekly pulse writer (architecture §5.4, stage 3).

Generates a <=250 word Markdown pulse with required sections. On constraint
failure the writer regenerates once, then raises.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

from pydantic import BaseModel

from src.generate.validate import PULSE_MAX_WORDS, validate_pulse, word_count
from src.intelligence.llm import chat_json
from src.models import IntelligenceResult, WeeklyPulse

ChatFn = Callable[..., dict[str, Any]]

DEFAULT_EXPORT_PATH = Path("output/weekly-pulse.md")


class PulseConstraintError(RuntimeError):
    pass


class _LlmPulse(BaseModel):
    markdown: str


SYSTEM_PROMPT = (
    "You are a product analyst writing a concise weekly pulse from customer "
    "reviews. Output Markdown with EXACTLY these section headings: "
    "## Top themes, ## Customer quotes, ## Key observation, ## Action ideas. "
    "Under Customer quotes include the provided quotes verbatim with their "
    "review ids. Under Action ideas give exactly 3 concrete ideas. "
    "The whole pulse MUST be 250 words or fewer. Do not invent quotes, fees, "
    "or URLs; use only the provided material."
)


def _schema() -> dict[str, Any]:
    schema = _LlmPulse.model_json_schema()
    schema["additionalProperties"] = False
    return schema


def _build_messages(
    intelligence: IntelligenceResult, feedback: Optional[str] = None
) -> list[dict[str, str]]:
    themes = ", ".join(intelligence.top_themes) or "none"
    quotes = "\n".join(f"- [{q.review_id}] {q.text}" for q in intelligence.quotes)
    fee = intelligence.fee_issue
    fee_line = (
        f"{fee.name}: {fee.why_confused}" if fee is not None else "none detected"
    )

    user = (
        f"Top themes: {themes}\n\n"
        f"Quotes:\n{quotes or '- none'}\n\n"
        f"Fee issue: {fee_line}"
    )
    if feedback:
        user += f"\n\nNote: the previous draft failed validation — {feedback}."

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _ask(call: ChatFn, intelligence: IntelligenceResult, feedback: Optional[str]) -> WeeklyPulse:
    raw = call(
        _build_messages(intelligence, feedback),
        _schema(),
        schema_name="weekly_pulse",
    )
    markdown = _LlmPulse.model_validate(raw).markdown
    return WeeklyPulse(markdown=markdown, word_count=word_count(markdown))


def write_pulse(
    intelligence: IntelligenceResult,
    *,
    chat_fn: Optional[ChatFn] = None,
    max_words: int = PULSE_MAX_WORDS,
) -> WeeklyPulse:
    call = chat_fn or chat_json

    pulse = _ask(call, intelligence, feedback=None)
    errors = validate_pulse(pulse, max_words)
    if not errors:
        return pulse

    pulse = _ask(call, intelligence, feedback="; ".join(errors))
    errors = validate_pulse(pulse, max_words)
    if errors:
        raise PulseConstraintError(
            "Pulse failed validation after one regenerate: " + "; ".join(errors)
        )
    return pulse


def export_pulse(pulse: WeeklyPulse, path: Path | str = DEFAULT_EXPORT_PATH) -> Path:
    """Write the pulse Markdown to disk. Returns the path written."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(pulse.markdown, encoding="utf-8")
    return target
