"""Client for OpenAI-compatible chat completions returning JSON.

Works with OpenAI, local servers (Ollama, LM Studio, llama.cpp) and free
gateways (Groq, OpenRouter, Gemini-compatible endpoints) by falling back
through response formats when a server rejects ``json_schema``.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _settings() -> tuple[str, str, str, str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    base_url = os.getenv("OPENAI_BASE_URL", "").strip() or DEFAULT_BASE_URL
    model = os.getenv("OPENAI_MODEL", "").strip() or DEFAULT_MODEL

    if not api_key:
        local_hosts = ("localhost", "127.0.0.1", "0.0.0.0")
        if any(host in base_url for host in local_hosts):
            api_key = "not-needed"  # local servers ignore the bearer token
        else:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to your .env file to run review "
                "intelligence (a mocked client can be injected for tests)."
            )
    return api_key, base_url, model, base_url.rstrip("/") + "/chat/completions"


def _schema_messages(
    messages: list[dict[str, str]], schema: dict[str, Any]
) -> list[dict[str, str]]:
    spec = (
        "Return ONLY a JSON object (no prose, no code fences) matching this "
        "JSON schema exactly:\n" + json.dumps(schema, indent=2)
    )
    return messages + [{"role": "system", "content": spec}]


def _payloads(
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    schema_name: str,
    model: str,
) -> list[dict[str, Any]]:
    with_schema = _schema_messages(messages, schema)
    return [
        {
            "model": model,
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": False},
            },
        },
        {"model": model, "messages": with_schema, "response_format": {"type": "json_object"}},
        {"model": model, "messages": with_schema},
    ]


def _api_error(response: httpx.Response) -> tuple[str, str]:
    """Return (code, message) extracted from an error response body."""
    try:
        error = response.json().get("error") or {}
        if isinstance(error, dict):
            return str(error.get("code") or ""), str(error.get("message") or response.text)
    except ValueError:
        pass
    return "", response.text


def _parse(content: Any) -> dict[str, Any]:
    if isinstance(content, list):  # some servers return content parts
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str):
        raise RuntimeError(f"LLM returned an unexpected content type: {type(content)!r}")

    text = content.strip()
    match = _FENCE.search(text)
    if match:
        text = match.group(1)
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LLM returned unparseable JSON: {exc}") from exc


def chat_json(
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    *,
    schema_name: str = "result",
    timeout: float = 90.0,
) -> dict[str, Any]:
    """Call an OpenAI-compatible chat API and return the parsed JSON object.

    Tries ``json_schema``, then ``json_object`` with the schema in the prompt,
    then a plain call with the schema in the prompt — so local/open-source
    servers work too. Raises RuntimeError with a clear message on failure.
    """
    api_key, base_url, model, url = _settings()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    last_error = "unknown error"

    for index, payload in enumerate(_payloads(messages, schema, schema_name, model)):
        try:
            response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
        except httpx.HTTPError as exc:
            raise RuntimeError(
                f"LLM request to {base_url} failed: {exc}. "
                "Is the server running (e.g. `ollama serve`)?"
            ) from exc

        if response.is_success:
            try:
                return _parse(response.json()["choices"][0]["message"]["content"])
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(f"LLM returned an unexpected payload: {exc}") from exc

        code, message = _api_error(response)
        last_error = f"HTTP {response.status_code}: {message}"
        if "quota" in message.lower() or "credit" in message.lower():
            raise RuntimeError(
                f"LLM API account error: {message} "
                "Switch to a free endpoint (see README) or add credits."
            )
        if response.status_code not in {400, 404, 415, 422}:
            raise RuntimeError(f"LLM request failed: {last_error}")

    raise RuntimeError(
        f"LLM rejected all response formats — last error: {last_error}"
    )
