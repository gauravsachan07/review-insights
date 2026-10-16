from datetime import date

from fastapi.testclient import TestClient

from src import orchestrator
from src.generate.explainer import load_sources
from src.main import app
from src.models import RunStatus

SHORT_PULSE = (
    "## Top themes\nExit load confusion\n"
    "## Customer quotes\n\"got cut something called exit load\" (R002)\n"
    "## Key observation\nFees surprise users at redemption.\n"
    "## Action ideas\n1. Show fees upfront\n2. Add FAQ\n3. Warn before redeem"
)

ANALYSIS_WITH_FEE = {
    "themes": [
        {
            "name": "Exit load confusion",
            "summary": "Charged without warning",
            "review_count": 6,
            "review_ids": ["R002"],
        },
        {"name": "App usability", "summary": "Smooth", "review_count": 5, "review_ids": ["R001"]},
        {"name": "Support", "summary": "Fast", "review_count": 2, "review_ids": ["R008"]},
    ],
    "top_themes": ["Exit load confusion", "App usability", "Support"],
    "quotes": [
        {
            "text": "Why is exit load not shown at the time of purchase?",
            "review_id": "R002",
        },
        {
            "text": "I redeemed my SIP early and saw an exit load deduction in the statement.",
            "review_id": "R004",
        },
        {
            "text": "Exit load confusion cost me money.",
            "review_id": "R009",
        },
    ],
    "fee_issue": {
        "name": "Exit load",
        "why_confused": "Users are charged on early redemption without warning",
        "evidence_quote": "got cut something called exit load",
        "evidence_review_id": "R002",
    },
}


def fake_chat(messages, schema, **kwargs):
    name = kwargs.get("schema_name")
    if name == "review_intelligence":
        return ANALYSIS_WITH_FEE
    if name == "weekly_pulse":
        return {"markdown": SHORT_PULSE}
    if name == "fee_explainer":
        return {
            "bullets": ["Exit load applies on early redemption", "It is deducted from proceeds"],
            "source_links": [load_sources()[0]["url"]],
        }
    raise AssertionError(f"unexpected schema_name: {name}")


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(orchestrator, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(orchestrator, "RUNS_DIR", tmp_path / "runs")


def test_start_run_success(monkeypatch, tmp_path) -> None:
    _isolate(monkeypatch, tmp_path)
    run = orchestrator.start_run(chat_fn=fake_chat, today=date(2026, 10, 15))

    assert run.status == RunStatus.READY_FOR_APPROVAL
    assert run.error is None
    assert run.payload is not None
    assert run.payload.date == date(2026, 10, 15)
    assert run.payload.identified_fee_issue == "Exit load"
    assert run.payload.weekly_pulse
    assert len(run.payload.source_links) == 2

    assert (tmp_path / "runs" / f"{run.id}.json").exists()
    assert (tmp_path / "weekly-pulse.md").exists()

    assert not (tmp_path / "notes.md").exists()
    assert not (tmp_path / "email-draft.md").exists()

    assert orchestrator.get_run(run.id).status == RunStatus.READY_FOR_APPROVAL


def test_start_run_failure_then_retry(monkeypatch, tmp_path) -> None:
    _isolate(monkeypatch, tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("LLM timeout")

    failed = orchestrator.start_run(chat_fn=boom)
    assert failed.status == RunStatus.FAILED
    assert "LLM timeout" in (failed.error or "")
    assert (tmp_path / "runs" / f"{failed.id}.json").exists()

    from src.intelligence.ingest import load_reviews

    assert len(load_reviews(orchestrator.SAMPLE_CSV)) >= 15

    retried = orchestrator.start_run(chat_fn=fake_chat)
    assert retried.status == RunStatus.READY_FOR_APPROVAL


def test_payload_none_convention_when_no_fee(monkeypatch, tmp_path) -> None:
    _isolate(monkeypatch, tmp_path)

    def no_fee_chat(messages, schema, **kwargs):
        if kwargs.get("schema_name") == "review_intelligence":
            return {**ANALYSIS_WITH_FEE, "fee_issue": None}
        return fake_chat(messages, schema, **kwargs)

    run = orchestrator.start_run(chat_fn=no_fee_chat)
    assert run.status == RunStatus.READY_FOR_APPROVAL
    assert run.explainer is None
    assert run.payload is not None
    assert run.payload.identified_fee_issue == "none"
    assert run.payload.explanation_bullets == []
    assert run.payload.source_links == []


def test_api_run_endpoints(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(orchestrator, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(orchestrator, "RUNS_DIR", tmp_path / "runs")

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    failed = orchestrator.start_run(chat_fn=boom)
    sample = orchestrator.start_run(chat_fn=fake_chat)
    monkeypatch.setattr(orchestrator, "start_run", lambda *a, **k: sample)

    client = TestClient(app)
    created = client.post("/api/runs", json={"use_sample": True})
    assert created.status_code == 200
    assert created.json()["status"] == "ready_for_approval"

    fetched = client.get(f"/api/runs/{sample.id}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == sample.id

    assert client.get("/api/runs/does-not-exist").status_code == 404
    assert client.post("/api/runs", json={}).status_code == 400

    assert client.post(f"/api/runs/{failed.id}/approve").status_code == 409
    assert client.post(f"/api/runs/{failed.id}/reject").status_code == 409
