import io

from src.intelligence.ingest import load_reviews

SAMPLE = "data/reviews.csv"

CSV = """review_id,text,rating,date,source
R1,Great app,5,2026-09-01,Google Play
,Missing id but has text,4,2026-09-02,App Store
R3,,5,2026-09-03,Google Play
R4,"Fees, charges, and loads",3,2026-09-04,Google Play
"""


def test_sample_csv_loads() -> None:
    reviews = load_reviews(SAMPLE)
    assert len(reviews) >= 15
    assert all(r.id and r.text for r in reviews)


def test_empty_text_rows_skipped() -> None:
    reviews = load_reviews(io.StringIO(CSV))
    assert len(reviews) == 3
    assert all(r.text.strip() for r in reviews)


def test_id_synthesized_from_row_index() -> None:
    reviews = load_reviews(io.StringIO(CSV))
    assert reviews[1].id == "2"


def test_utf8_and_quoted_fields() -> None:
    utf8 = 'review_id,text\nR1,"Café \u2014 exit load, émoji \U0001f600"\n'
    reviews = load_reviews(io.StringIO(utf8))
    assert reviews[0].text == "Café \u2014 exit load, émoji \U0001f600"

    with open(SAMPLE, encoding="utf-8") as fh:
        assert "exit load" in fh.read()
