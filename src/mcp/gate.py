"""Approval gate (architecture §5.5, stages 7-8).

The only path to the MCP file adapters. Approve runs from
``ready_for_approval``; every other state is rejected. Idempotent by run: a
second approve does not re-run tools that already succeeded. Reject never
writes files.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from src.mcp import email_draft, notes
from src.models import Run, RunStatus, ToolLog

TOOL_NOTES = "append_notes"
TOOL_EMAIL = "create_email_draft"


class GateError(RuntimeError):
    """Raised when a run cannot be approved/rejected in its current state."""


def _planned(output_dir: Path) -> list[tuple[str, Callable, Path]]:
    return [
        (TOOL_NOTES, notes.append_notes, output_dir / "notes.md"),
        (TOOL_EMAIL, email_draft.create_email_draft, output_dir / "email-draft.md"),
    ]


def _succeeded(run: Run) -> set[str]:
    return {log.tool for log in run.logs if log.ok}


def approve(run: Run, *, output_dir: Optional[Path | str] = None) -> Run:
    """Commit the run through the MCP adapters, idempotently."""
    if run.status == RunStatus.APPROVED:
        return run
    if run.status != RunStatus.READY_FOR_APPROVAL:
        raise GateError(
            f"Cannot approve a run in status '{run.status.value}'; "
            "expected 'ready_for_approval'."
        )
    if run.payload is None:
        raise GateError("Run has no MCP payload to commit.")

    out = Path(output_dir) if output_dir is not None else notes.OUTPUT_DIR
    planned = _planned(out)

    for tool, adapter, path in planned:
        if tool in _succeeded(run):
            continue
        try:
            result = adapter(run.payload, path)
            run.logs.append(
                ToolLog(tool=tool, ok=True, location=result.get("location"))
            )
        except Exception as exc:  # noqa: BLE001 - logged for partial-failure retry
            run.logs.append(ToolLog(tool=tool, ok=False, error=str(exc)))

    if all(tool in _succeeded(run) for tool, _, _ in planned):
        run.status = RunStatus.APPROVED
        run.mcp_committed_at = datetime.now(timezone.utc)

    return run


def reject(run: Run) -> Run:
    """No side effects. Mark the run rejected (idempotent)."""
    if run.status in (RunStatus.REJECTED, RunStatus.APPROVED):
        return run
    if run.status != RunStatus.READY_FOR_APPROVAL:
        raise GateError(
            f"Cannot reject a run in status '{run.status.value}'; "
            "expected 'ready_for_approval'."
        )
    run.status = RunStatus.REJECTED
    return run
