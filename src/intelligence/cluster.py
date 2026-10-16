"""Review intelligence: cluster reviews into themes, rank, quote, detect one fee issue.

Architecture §5.3 / stages 1-2. LLM-assisted clustering with server-side
verification; no embeddings required.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from src.intelligence.llm import chat_json
from src.intelligence.verify import verify_fee_issue, verify_quotes
from src.models import FeeIssue, IntelligenceResult, Quote, Review, Theme

ChatFn = Callable[..., dict[str, Any]]

MAX_THEMES = 5
MAX_TOP_THEMES = 3
MAX_QUOTES = 3
MAX_REVIEWS_SENT = 60


class _LlmTheme(BaseModel):
    name: str
    summary: str = ""
    review_count: int = 0
    review_ids: list[str] = Field(default_factory=list)


class _LlmQuote(BaseModel):
    text: str
    review_id: str


class _LlmFee(BaseModel):
    name: str
    why_confused: str
    evidence_quote: str
    evidence_review_id: str


class _LlmAnalysis(BaseModel):
    themes: list[_LlmTheme] = Field(default_factory=list)
    top_themes: list[str] = Field(default_factory=list)
    quotes: list[_LlmQuote] = Field(default_factory=list)
    fee_issue: Optional[_LlmFee] = None


SYSTEM_PROMPT = (
    "You analyze app-store reviews for a retail investing app (Groww). "
    "Return JSON matching the provided schema. Rules: "
    "at most 5 themes, ranked; top_themes lists the names of the 3 most "
    "important themes (fewer only if the data is too thin); exactly 3 quotes "
    "that are VERBATIM substrings copied from the cited review text (no edits, "
    "no stitched phrases); identify at most ONE recurring fee or charge "
    "confusion as fee_issue with evidence_quote copied verbatim from the cited "
    "review. If no such recurring fee confusion exists, set fee_issue to null. "
    "Never invent quotes, fees, or URLs."
)


def _schema() -> dict[str, Any]:
    schema = _LlmAnalysis.model_json_schema()
    schema["additionalProperties"] = False
    return schema


def select_reviews(reviews: list[Review], limit: int = MAX_REVIEWS_SENT) -> list[Review]:
    """Keep all low-rated reviews plus an even sample of the rest, ids intact."""
    if len(reviews) <= limit:
        return list(reviews)

    low = [r for r in reviews if r.rating is not None and r.rating <= 2]
    rest = [r for r in reviews if r not in low]

    remaining = max(limit - len(low), 0)
    if remaining and rest:
        step = len(rest) / remaining
        sampled = [rest[int(i * step)] for i in range(remaining)]
    else:
        sampled = []

    chosen = {r.id for r in low} | {r.id for r in sampled}
    return [r for r in reviews if r.id in chosen]


def _format_reviews(reviews: list[Review]) -> str:
    lines = []
    for r in reviews:
        rating = "" if r.rating is None else f" | rating={r.rating}"
        lines.append(f"[{r.id}]{rating} {r.text}")
    return "\n".join(lines)


def _build_messages(reviews: list[Review]) -> list[dict[str, str]]:
    user = (
        "Reviews (format: [review_id] | rating=N <text>):\n\n"
        f"{_format_reviews(reviews)}"
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def analyze_reviews(
    reviews: list[Review], *, chat_fn: Optional[ChatFn] = None
) -> IntelligenceResult:
    """Cluster, rank, quote, and detect a single fee issue for a set of reviews.

    ``chat_fn`` may be injected for tests; by default it calls the configured
    OpenAI-compatible endpoint.
    """
    if not reviews:
        return IntelligenceResult()

    call = chat_fn or chat_json
    sample = select_reviews(reviews)
    raw = call(_build_messages(sample), _schema(), schema_name="review_intelligence")
    analysis = _LlmAnalysis.model_validate(raw)

    themes = [
        Theme(
            name=t.name,
            summary=t.summary,
            review_count=t.review_count,
            review_ids=t.review_ids,
        )
        for t in analysis.themes[:MAX_THEMES]
    ]

    quotes = verify_quotes(
        [Quote(text=q.text, review_id=q.review_id) for q in analysis.quotes[:MAX_QUOTES]],
        reviews,
        limit=MAX_QUOTES,
    )

    fee_issue = None
    if analysis.fee_issue is not None:
        fee_issue = verify_fee_issue(
            FeeIssue(
                name=analysis.fee_issue.name,
                why_confused=analysis.fee_issue.why_confused,
                evidence_quote=analysis.fee_issue.evidence_quote,
                evidence_review_id=analysis.fee_issue.evidence_review_id,
            ),
            reviews,
        )

    return IntelligenceResult(
        themes=themes,
        top_themes=analysis.top_themes[:MAX_TOP_THEMES],
        quotes=quotes,
        fee_issue=fee_issue,
    )
