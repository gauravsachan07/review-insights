import json

import httpx
import pytest

from src.intelligence import llm


def _response(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status_code=status, json=body)


def test_falls_back_when_json_schema_rejected(monkeypatch) -> None:
    calls: list[dict] = []
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    messages = [{"role": "user", "content": "hi"}]

    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        calls.append(json)
        if "response_format" in json and json["response_format"]["type"] == "json_schema":
            return _response(400, {"error": {"message": "json_schema not supported"}})
        content = "```json\n{\"x\": 1}\n```"
        return _response(200, {"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = llm.chat_json(messages, schema, schema_name="t")
    assert result == {"x": 1}
    assert len(calls) == 2
    assert "schema" in json.dumps(calls[1]["messages"])


def test_all_formats_rejected_raises(monkeypatch) -> None:
    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        return _response(400, {"error": {"message": "nope"}})

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="rejected all response formats|nope"):
        llm.chat_json([{"role": "user", "content": "hi"}], {"type": "object"})


def test_quota_error_is_explicit(monkeypatch) -> None:
    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        return _response(
            429,
            {"error": {"code": "insufficient_quota", "message": "no credits remaining"}},
        )

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    with pytest.raises(RuntimeError, match="account error"):
        llm.chat_json([{"role": "user", "content": "hi"}], {"type": "object"})


def test_missing_key_without_local_base_raises(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        llm.chat_json([{"role": "user", "content": "hi"}], {"type": "object"})


def test_parses_bare_json_wrapped_in_prose(monkeypatch) -> None:
    def fake_post(url, headers=None, json=None, timeout=None):  # noqa: A002
        content = "Here you go: {\"x\": 2} hope that helps"
        return _response(200, {"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert llm.chat_json([{"role": "user", "content": "hi"}], {"type": "object"}) == {"x": 2}
