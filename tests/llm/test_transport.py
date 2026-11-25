import io
import json
import urllib.error

import pytest

from coding_tutor.llm import transport
from coding_tutor.llm.transport import LLMError, http_post_json


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_posts_json_with_headers(monkeypatch):
    sent = {}

    def fake_urlopen(req, timeout):
        sent.update(url=req.full_url, body=json.loads(req.data), headers=dict(req.header_items()), timeout=timeout)
        return FakeResponse(b'{"ok": true}')

    monkeypatch.setattr(transport.urllib.request, "urlopen", fake_urlopen)
    assert http_post_json("http://x/api", {"a": 1}, {"Authorization": "Bearer k"}, 5) == {"ok": True}
    assert sent["url"] == "http://x/api" and sent["body"] == {"a": 1} and sent["timeout"] == 5
    assert sent["headers"]["Content-type"] == "application/json"
    assert sent["headers"]["Authorization"] == "Bearer k"


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (urllib.error.HTTPError("http://x", 401, "Unauthorized", {}, None), "HTTP 401"),
        (urllib.error.URLError("connection refused"), "not reachable"),
    ],
    ids=["http_error", "unreachable"],
)
def test_errors_never_include_the_key(monkeypatch, error, message):
    def fake_urlopen(req, timeout):
        raise error

    monkeypatch.setattr(transport.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(LLMError, match=message) as exc:
        http_post_json("http://x", {}, {"Authorization": "Bearer sk-secret"}, 1)
    assert "sk-secret" not in str(exc.value)
    assert exc.value.__cause__ is None


@pytest.mark.parametrize(
    ("body", "detail"),
    [
        (b'{"error":"model \'gemma4:e4b\' not found"}', "model 'gemma4:e4b' not found"),  # Ollama
        (b'{"error":{"message":"Invalid API key","type":"auth"}}', "Invalid API key"),  # OpenAI-compatible
        (b"Service   Unavailable\n", "Service Unavailable"),
    ],
    ids=["ollama", "openai", "text"],
)
def test_http_error_includes_server_detail(monkeypatch, body, detail):
    def fake_urlopen(req, timeout):
        raise urllib.error.HTTPError("http://x", 404, "Not Found", {}, io.BytesIO(body))

    monkeypatch.setattr(transport.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(LLMError) as exc:
        http_post_json("http://x", {}, {"Authorization": "Bearer sk-secret"}, 1)
    assert str(exc.value) == f"http://x returned HTTP 404: {detail}"
    assert "sk-secret" not in str(exc.value)


def test_non_json_reply(monkeypatch):
    monkeypatch.setattr(transport.urllib.request, "urlopen", lambda req, timeout: FakeResponse(b"<html>"))
    with pytest.raises(LLMError, match="non-JSON"):
        http_post_json("http://x", {}, {}, 1)
