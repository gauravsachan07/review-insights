import pytest

from src.generate.explainer import allowed_urls, load_sources, write_explainer
from src.generate.pulse import PulseConstraintError, export_pulse, write_pulse
from src.generate.validate import validate_explainer, validate_pulse, word_count
from src.models import FeeIssue, IntelligenceResult, Quote

SHORT_PULSE = (
    "## Top themes\nExit load confusion, app usability\n"
    "## Customer quotes\n\"exit load nobody explained\" (R2)\n"
    "## Key observation\nUsers want fee clarity before they redeem.\n"
    "## Action ideas\n1. Show fees upfront\n2. Add a FAQ\n3. Warn before redeem"
)

LONG_PULSE = (
    "## Top themes\n" + ("word " * 300) + "\n"
    "## Customer quotes\nquote\n## Key observation\nobs\n## Action ideas\naction"
)

INTEL = IntelligenceResult(
    themes=[],
    top_themes=["Exit load confusion", "App usability", "Support"],
    quotes=[Quote(text="exit load nobody explained", review_id="R2")],
    fee_issue=None,
)

FEE = FeeIssue(
    name="Exit load",
    why_confused="Charged on early redemption without warning",
    evidence_quote="exit load nobody explained",
    evidence_review_id="R2",
)


def test_pulse_regenerates_once_when_too_long() -> None:
    calls: list[dict] = []

    def chat_fn(messages, schema, **kwargs):
        calls.append(kwargs)
        return {"markdown": LONG_PULSE if len(calls) == 1 else SHORT_PULSE}

    pulse = write_pulse(INTEL, chat_fn=chat_fn)
    assert len(calls) == 2
    assert pulse.word_count <= 250
    assert validate_pulse(pulse) == []


def test_pulse_fails_after_second_long_draft() -> None:
    def chat_fn(messages, schema, **kwargs):
        return {"markdown": LONG_PULSE}

    with pytest.raises(PulseConstraintError):
        write_pulse(INTEL, chat_fn=chat_fn)


def test_export_pulse_writes_file(tmp_path) -> None:
    pulse = write_pulse(INTEL, chat_fn=lambda *a, **k: {"markdown": SHORT_PULSE})
    target = export_pulse(pulse, tmp_path / "weekly-pulse.md")
    assert target.read_text(encoding="utf-8") == pulse.markdown


def test_explainer_null_fee_returns_none() -> None:
    sources = load_sources()
    assert write_explainer(None, sources, chat_fn=lambda *a, **k: {}) is None


def test_explainer_filters_hallucinated_urls_and_clamps_bullets() -> None:
    sources = load_sources()
    allow = allowed_urls(sources)
    many_bullets = [f"fact {i}" for i in range(10)]

    def chat_fn(messages, schema, **kwargs):
        return {
            "bullets": many_bullets,
            "source_links": ["https://evil.example.com/fee", allow[0]],
        }

    explainer = write_explainer(FEE, sources, chat_fn=chat_fn)
    assert explainer is not None
    assert len(explainer.bullets) == 6
    assert "https://evil.example.com/fee" not in explainer.source_links
    assert len(explainer.source_links) == 2
    assert set(explainer.source_links) <= set(allow)
    assert validate_explainer(explainer, allow) == []


def test_explainer_last_checked_from_caller() -> None:
    from datetime import date

    sources = load_sources()
    explainer = write_explainer(
        FEE,
        sources,
        chat_fn=lambda *a, **k: {"bullets": ["x"], "source_links": []},
        today=date(2026, 10, 15),
    )
    assert explainer is not None
    assert explainer.last_checked == date(2026, 10, 15)


def test_word_count_helper() -> None:
    assert word_count("one two three") == 3
