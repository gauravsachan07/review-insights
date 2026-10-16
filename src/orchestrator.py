"""Pipeline orchestrator (architecture §5.2, stages 1-6).

Runs ingest -> review intelligence -> pulse -> explainer -> constraint checks ->
preview, then persists a run snapshot. It never writes MCP files; that only
happens through the approval gate (Phase 5).

MCP payload convention when there is no fee issue: ``identified_fee_issue`` is
the string ``"none"`` and ``explanation_bullets`` / ``source_links`` are empty
lists.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from src.generate.explainer import load_sources, write_explainer
from src.generate.pulse import export_pulse, write_pulse
from src.generate.validate import validate_explainer
from src.intelligence.cluster import analyze_reviews
from src.intelligence.ingest import load_reviews
from src.models import IntelligenceResult, McpPayload, Run, RunStatus, WeeklyPulse

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
RUNS_DIR = OUTPUT_DIR / "runs"
SAMPLE_CSV = ROOT / "data" / "reviews.csv"

ChatFn = Callable[..., dict[str, Any]]

_current_run: Optional[Run] = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_payload(
    intelligence: IntelligenceResult,
    pulse: WeeklyPulse,
    explainer: Optional[Any],
    run_date: date,
) -> McpPayload:
    fee = intelligence.fee_issue
    if fee is None or explainer is None:
        return McpPayload(
            date=run_date,
            top_themes=list(intelligence.top_themes),
            weekly_pulse=pulse.markdown,
            identified_fee_issue="none",
            explanation_bullets=[],
            source_links=[],
        )
    return McpPayload(
        date=run_date,
        top_themes=list(intelligence.top_themes),
        weekly_pulse=pulse.markdown,
        identified_fee_issue=fee.name,
        explanation_bullets=list(explainer.bullets),
        source_links=list(explainer.source_links),
    )


def persist(run: Run) -> Path:
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    target = RUNS_DIR / f"{run.id}.json"
    target.write_text(run.model_dump_json(indent=2), encoding="utf-8")
    return target


def current_run() -> Optional[Run]:
    return _current_run


def save_run(run: Run) -> Path:
    """Persist a run (used by the approval gate) and refresh the in-memory run."""
    global _current_run

    if _current_run is None or _current_run.id == run.id:
        _current_run = run
    return persist(run)


def get_run(run_id: str) -> Optional[Run]:
    if _current_run is not None and _current_run.id == run_id:
        return _current_run
    target = RUNS_DIR / f"{run_id}.json"
    if target.exists():
        return Run.model_validate_json(target.read_text(encoding="utf-8"))
    return None


def start_run(
    csv_path: Path | str = SAMPLE_CSV,
    *,
    chat_fn: Optional[ChatFn] = None,
    today: Optional[date] = None,
) -> Run:
    """Execute stages 1-6 and return the resulting Run (ready or failed)."""
    global _current_run

    run_date = today or date.today()
    run = Run(id=uuid.uuid4().hex[:12], status=RunStatus.INGESTING)
    _current_run = run
    persist(run)

    try:
        reviews = load_reviews(csv_path)
        if not reviews:
            raise ValueError("No reviews found in the CSV input.")

        intelligence = analyze_reviews(reviews, chat_fn=chat_fn)
        pulse = write_pulse(intelligence, chat_fn=chat_fn)

        sources = load_sources()
        explainer = write_explainer(
            intelligence.fee_issue, sources, chat_fn=chat_fn, today=run_date
        )
        if explainer is not None:
            errors = validate_explainer(
                explainer, [s["url"] for s in sources]
            )
            if errors:
                raise ValueError("Explainer failed validation: " + "; ".join(errors))

        payload = build_payload(intelligence, pulse, explainer, run_date)

        run.intelligence = intelligence
        run.pulse = pulse
        run.explainer = explainer
        run.payload = payload
        run.status = RunStatus.READY_FOR_APPROVAL

        export_pulse(pulse, OUTPUT_DIR / "weekly-pulse.md")
    except Exception as exc:  # noqa: BLE001 - surfaced as run error for retry
        run.status = RunStatus.FAILED
        run.error = str(exc)

    persist(run)
    return run
