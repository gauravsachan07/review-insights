from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)


def test_index_serves_wizard() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    body = response.text
    for marker in ("step-1", "step-2", "step-3", "btn-approve", "btn-reject", "/static/app.js"):
        assert marker in body


def test_static_assets_served() -> None:
    response = client.get("/static/app.js")
    assert response.status_code == 200
    assert "startRun" in response.text


def test_ui_only_calls_existing_api_routes() -> None:
    js = client.get("/static/app.js").text
    assert "/api/runs" in js
    assert "/api/reviews" not in js
    assert "openai" not in js.lower()
    assert "fetch(\"http" not in js
