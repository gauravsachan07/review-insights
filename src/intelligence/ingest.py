from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import IO, Union

from src.models import Review

CsvSource = Union[str, Path, IO[str]]


def _parse_rating(raw: str | None) -> int | None:
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _parse_date(raw: str | None):
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    from datetime import datetime

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def load_reviews(path: CsvSource) -> list[Review]:
    """Load reviews from a CSV path or file-like object.

    Drops rows with empty text. Synthesizes a review_id from the row index
    (1-based) when the column is missing or blank.
    """
    if isinstance(path, (str, Path)):
        with open(path, "r", encoding="utf-8-sig", newline="") as fh:
            return _load(fh)

    handle = path
    if isinstance(handle, io.TextIOBase) or hasattr(handle, "read"):
        content = handle.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")
        return _load(io.StringIO(content))

    raise TypeError(f"Unsupported CSV source: {type(path)!r}")


def _load(stream: IO[str]) -> list[Review]:
    reader = csv.DictReader(stream)
    if reader.fieldnames is None:
        return []

    reviews: list[Review] = []
    for row_number, row in enumerate(reader, start=1):
        text = (row.get("text") or "").strip()
        if not text:
            continue

        review_id = (row.get("review_id") or "").strip()
        if not review_id:
            review_id = str(row_number)

        reviews.append(
            Review(
                id=review_id,
                text=text,
                rating=_parse_rating(row.get("rating")),
                date=_parse_date(row.get("date")),
                source=(row.get("source") or "").strip() or None,
            )
        )
    return reviews
