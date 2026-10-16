import pytest

from src.intelligence.cluster import analyze_reviews
from src.models import Review

REVIEWS = [
    Review(id="R1", text="App is smooth and fast", rating=5),
    Review(
        id="R2",
        text="I redeemed my mutual fund early and got hit with an exit load nobody explained",
        rating=1,
    ),
    Review(
        id="R3",
        text="Exit load confusion: the app never showed the charge before redeem",
        rating=2,
    ),
]


def _fixture_response() -> dict:
    return {
        "themes": [
            {"name": "Exit load confusion", "summary": "Charges surprise users", "review_count": 2, "review_ids": ["R2", "R3"]},
            {"name": "App usability", "summary": "Smooth experience", "review_count": 1, "review_ids": ["R1"]},
            {"name": "T1", "summary": "", "review_count": 0, "review_ids": []},
            {"name": "T2", "summary": "", "review_count": 0, "review_ids": []},
            {"name": "T3", "summary": "", "review_count": 0, "review_ids": []},
            {"name": "T4-should-be-dropped", "summary": "", "review_count": 0, "review_ids": []},
        ],
        "top_themes": ["Exit load confusion", "App usability", "T1", "T2-extra"],
        "quotes": [
            {"text": "I redeemed my mutual fund early and got hit with an exit load nobody explained", "review_id": "R2"},
            {"text": "THIS QUOTE IS INVENTED AND DOES NOT EXIST", "review_id": "R1"},
            {"text": "the app never showed the charge before redeem", "review_id": "R3"},
        ],
        "fee_issue": {
            "name": "Exit load",
            "why_confused": "Users learn about the charge only after redeeming",
            "evidence_quote": "got hit with an exit load nobody explained",
            "evidence_review_id": "R2",
        },
    }


def _mock_chat(messages, schema, **kwargs):
    return _fixture_response()


def test_analyze_drops_bad_quote_and_keeps_grounded_fee() -> None:
    result = analyze_reviews(REVIEWS, chat_fn=_mock_chat)

    assert len(result.themes) <= 5
    assert result.themes[-1].name != "T4-should-be-dropped"
    assert len(result.top_themes) == 3

    assert len(result.quotes) == 2
    assert all(q.text for q in result.quotes)
    review_texts = {r.id: r.text for r in REVIEWS}
    for q in result.quotes:
        assert q.text in review_texts[q.review_id]

    assert result.fee_issue is not None
    assert result.fee_issue.name == "Exit load"
    assert result.fee_issue.evidence_review_id == "R2"


def test_fee_dropped_when_evidence_not_grounded() -> None:
    response = _fixture_response()
    response["fee_issue"]["evidence_quote"] = "a fee that was never mentioned"
    result = analyze_reviews(REVIEWS, chat_fn=lambda *a, **k: response)
    assert result.fee_issue is None


def test_fee_null_stays_null() -> None:
    response = _fixture_response()
    response["fee_issue"] = None
    result = analyze_reviews(REVIEWS, chat_fn=lambda *a, **k: response)
    assert result.fee_issue is None


def test_empty_reviews_returns_empty_result() -> None:
    result = analyze_reviews([], chat_fn=_mock_chat)
    assert result.themes == [] and result.quotes == [] and result.fee_issue is None


def test_missing_api_key_raises(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        analyze_reviews(REVIEWS)
