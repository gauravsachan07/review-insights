"""Fee explainer writer (architecture §5.4, stage 4).

Consumes ONLY the fee issue from review intelligence plus the official URL
allowlist in config/sources.json. If there is no fee issue, there is no
explainer. The model may choose 2 links but can never introduce new URLs.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from src.generate.validate import (
    EXPLAINER_MAX_BULLETS,
    EXPLAINER_REQUIRED_LINKS,
)
from src.intelligence.llm import chat_json
from src.models import FeeExplainer, FeeIssue

ChatFn = Callable[..., dict[str, Any]]

SOURCES_PATH = Path(__file__).resolve().parents[2] / "config" / "sources.json"


class _LlmExplainer(BaseModel):
    bullets: list[str] = Field(default_factory=list)
    source_links: list[str] = Field(default_factory=list)


SYSTEM_PROMPT = (
    "You explain a single fee or charge to retail investors in plain, "
    "facts-only language. Output at most 6 short bullets and choose exactly 2 "
    "URLs from the provided allowlist that best support the explanation. "
    "Use ONLY the URLs given; never invent links. Do not give investment advice."
)


def load_sources(path: Path | str = SOURCES_PATH) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def allowed_urls(sources: list[dict[str, str]]) -> list[str]:
    return [s["url"] for s in sources]


def _schema() -> dict[str, Any]:
    schema = _LlmExplainer.model_json_schema()
    schema["additionalProperties"] = False
    return schema


def _build_messages(
    fee_issue: FeeIssue, sources: list[dict[str, str]]
) -> list[dict[str, str]]:
    catalog = "\n".join(f"- {s['label']}: {s['url']}" for s in sources)
    user = (
        f"Fee: {fee_issue.name}\n"
        f"Why customers are confused: {fee_issue.why_confused}\n"
        f"Customer evidence: {fee_issue.evidence_quote} "
        f"(review {fee_issue.evidence_review_id})\n\n"
        f"Allowed source URLs:\n{catalog}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _sanitize_links(links: list[str], allowed: list[str]) -> list[str]:
    valid = [link for link in links if link in allowed]
    deduped: list[str] = []
    for link in valid:
        if link not in deduped:
            deduped.append(link)
    deduped = deduped[:EXPLAINER_REQUIRED_LINKS]

    for link in allowed:
        if len(deduped) >= EXPLAINER_REQUIRED_LINKS:
            break
        if link not in deduped:
            deduped.append(link)
    return deduped


def write_explainer(
    fee_issue: Optional[FeeIssue],
    sources: list[dict[str, str]],
    *,
    chat_fn: Optional[ChatFn] = None,
    today: Optional[date] = None,
) -> Optional[FeeExplainer]:
    """Return a FeeExplainer, or None when there is no fee issue."""
    if fee_issue is None:
        return None

    call = chat_fn or chat_json
    raw = call(_build_messages(fee_issue, sources), _schema(), schema_name="fee_explainer")
    parsed = _LlmExplainer.model_validate(raw)

    bullets = [b.strip() for b in parsed.bullets if b and b.strip()]
    bullets = bullets[:EXPLAINER_MAX_BULLETS]
    links = _sanitize_links(parsed.source_links, allowed_urls(sources))

    return FeeExplainer(
        bullets=bullets,
        source_links=links,
        last_checked=today or date.today(),
    )
