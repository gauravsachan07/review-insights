"""Server-side verification for LLM output.

Quotes must be substrings of the review they cite. A fee issue whose evidence
does not verify is dropped (never invent a fee).
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

from src.models import FeeIssue, Quote, Review

_WHITESPACE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Case-insensitive, whitespace-normalized form for substring checks."""
    return _WHITESPACE.sub(" ", text).strip().casefold()


def is_substring(quote: str, review_text: str) -> bool:
    if not quote or not review_text:
        return False
    return normalize(quote) in normalize(review_text)


def _review_index(reviews: Iterable[Review]) -> dict[str, Review]:
    return {review.id: review for review in reviews}


def verify_quotes(
    quotes: Iterable[Quote], reviews: Iterable[Review], limit: int = 3
) -> list[Quote]:
    index = _review_index(reviews)
    verified: list[Quote] = []
    for quote in quotes:
        review = index.get(quote.review_id)
        if review is None or not is_substring(quote.text, review.text):
            continue
        verified.append(
            Quote(
                text=quote.text,
                review_id=quote.review_id,
                date=review.date,
                rating=review.rating,
            )
        )
        if len(verified) >= limit:
            break
    return verified


def verify_fee_issue(
    fee: Optional[FeeIssue], reviews: Iterable[Review]
) -> Optional[FeeIssue]:
    if fee is None:
        return None
    index = _review_index(reviews)
    review = index.get(fee.evidence_review_id)
    if review is None or not is_substring(fee.evidence_quote, review.text):
        return None
    return fee
