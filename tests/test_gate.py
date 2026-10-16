from datetime import date

from fastapi.testclient import TestClient

from src import orchestrator
from src.main import app
from src.mcp import gate, notes
from src.models import McpPayload, Run, RunStatus, WeeklyPulse

PAYLOAD = McpPayload(
    date=date(2026, 10, 15),
    top_themes=["Exit load confusion", "App usability", "Support"],
    weekly_pulse="## Top themes\nExit load\n## Action ideas\n1. 2. 3.",
    identified_fee_issue="Exit load",
    explanation_bullets=["Exit load applies on early redemption"],
    source_links=["https://help.groww.in/", "https://www.sebi.gov.in/"],
)


def make_run(run_id: str = "run1", status: RunStatus = RunStatus.READY_FOR_APPROVAL) -> Run:
    return Run(
        id=run_id,
        status=status,
        payload=PAYLOAD,
        pulse=WeeklyPulse(markdown=PAYLOAD.weekly_pulse, word_count=8),
    )


def test_approve_writes_both_files_and_logs(tmp_path) -> None:
    run = make_run()
    gate.approve(run, output_dir=tmp_path)

    assert run.status == RunStatus.APPROVED
    assert run.mcp_committed_at is not None
    assert [log.tool for log in run.logs] == ["append_notes", "create_email_draft"]
    assert all(log.ok for log in run.logs)

    notes_file = tmp_path / "notes.md"
    draft_file = tmp_path / "email-draft.md"
    assert notes_file.exists()
    assert draft_file.exists()
    assert "Exit load confusion" in notes_file.read_text(encoding="utf-8")
    draft = draft_file.read_text(encoding="utf-8")
    assert draft.startswith("Subject: Weekly Product Pulse + Customer Clarification")
    assert "DRAFT" in draft


def test_double_approve_is_idempotent(tmp_path) -> None:
    run = make_run()
    gate.approve(run, output_dir=tmp_path)
    gate.approve(run, output_dir=tmp_path)

    assert len(run.logs) == 2
    content = (tmp_path / "notes.md").read_text(encoding="utf-8")
    assert content.count("## Review Insights — 2026-10-15") == 1


def test_approve_before_ready_raises(tmp_path) -> None:
    for status in (RunStatus.FAILED, RunStatus.REJECTED, RunStatus.INGESTING):
        try:
            gate.approve(make_run(status=status), output_dir=tmp_path)
        except gate.GateError:
            pass
        else:
            raise AssertionError(f"approve should fail for {status}")


def test_reject_writes_nothing(tmp_path) -> None:
    run = make_run()
    before = (tmp_path / "notes.md").read_text(encoding="utf-8") if (tmp_path / "notes.md").exists() else None
    mtime = (tmp_path / "notes.md").stat().st_mtime if (tmp_path / "notes.md").exists() else None

    gate.reject(run)
    assert run.status == RunStatus.REJECTED

    after_exists = (tmp_path / "notes.md").exists()
    if mtime is None:
        assert not after_exists
    else:
        assert (tmp_path / "notes.md").stat().st_mtime == mtime
        assert (tmp_path / "notes.md").read_text(encoding="utf-8") == before


def test_partial_failure_then_retry(tmp_path, monkeypatch) -> None:
    run = make_run()
    calls = {"n": 0}
    real_email = gate.email_draft.create_email_draft

    def flaky(payload, path):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("disk full")
        return real_email(payload, path)

    monkeypatch.setattr(gate.email_draft, "create_email_draft", flaky)

    gate.approve(run, output_dir=tmp_path)
    assert run.status == RunStatus.READY_FOR_APPROVAL
    failed = [log for log in run.logs if not log.ok]
    assert len(failed) == 1 and failed[0].tool == "create_email_draft"
    assert "disk full" in (failed[0].error or "")
    assert (tmp_path / "notes.md").exists()
    assert not (tmp_path / "email-draft.md").exists()

    gate.approve(run, output_dir=tmp_path)
    assert run.status == RunStatus.APPROVED
    assert (tmp_path / "email-draft.md").exists()
    notes_count = (tmp_path / "notes.md").read_text(encoding="utf-8").count(
        "## Review Insights — 2026-10-15"
    )
    assert notes_count == 1
    assert len([log for log in run.logs if log.ok]) == 2


def _isolate(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(orchestrator, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(orchestrator, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(notes, "OUTPUT_DIR", tmp_path)


def test_api_approve_and_reject(monkeypatch, tmp_path) -> None:
    _isolate(monkeypatch, tmp_path)
    ready = make_run(run_id="ready1")
    orchestrator.save_run(ready)

    client = TestClient(app)

    approved = client.post("/api/runs/ready1/approve")
    assert approved.status_code == 200
    body = approved.json()
    assert body["status"] == "approved"
    assert [log["tool"] for log in body["logs"]] == [
        "append_notes",
        "create_email_draft",
    ]

    fetched = client.get("/api/runs/ready1")
    assert fetched.status_code == 200
    assert len(fetched.json()["logs"]) == 2

    again = client.post("/api/runs/ready1/approve")
    assert again.status_code == 200
    assert len(again.json()["logs"]) == 2
    assert (tmp_path / "notes.md").read_text(encoding="utf-8").count(
        "## Review Insights — 2026-10-15"
    ) == 1

    failed_run = make_run(run_id="failed1", status=RunStatus.FAILED)
    orchestrator.save_run(failed_run)
    assert client.post("/api/runs/failed1/approve").status_code == 409
    assert client.post("/api/runs/missing1/approve").status_code == 404

    rejecting = make_run(run_id="reject1")
    orchestrator.save_run(rejecting)
    notes_before = (
        (tmp_path / "notes.md").read_text(encoding="utf-8")
        if (tmp_path / "notes.md").exists()
        else None
    )
    rejected = client.post("/api/runs/reject1/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    notes_after = (
        (tmp_path / "notes.md").read_text(encoding="utf-8")
        if (tmp_path / "notes.md").exists()
        else None
    )
    assert notes_after == notes_before


def test_api_artifacts_view_and_download(monkeypatch, tmp_path) -> None:
    _isolate(monkeypatch, tmp_path)
    orchestrator.save_run(make_run(run_id="art1"))

    client = TestClient(app)

    blocked = client.get("/api/runs/art1/artifacts/notes")
    assert blocked.status_code == 409

    client.post("/api/runs/art1/approve")

    view = client.get("/api/runs/art1/artifacts/notes")
    assert view.status_code == 200
    assert "Exit load confusion" in view.text
    assert "attachment" not in view.headers.get("content-disposition", "")

    download = client.get("/api/runs/art1/artifacts/email-draft?download=true")
    assert download.status_code == 200
    assert "attachment" in download.headers["content-disposition"]
    assert "DRAFT" in download.text

    assert client.get("/api/runs/art1/artifacts/secrets").status_code == 404
    assert client.get("/api/runs/art1/artifacts/..%2Fnotes.md").status_code == 404
    assert client.get("/api/runs/missing/artifacts/notes").status_code == 404
