"""The Vercel deployment files: api/index.py builds the API from the environment; vercel.json serves web/ with
the same security headers as the dev server, immutable topic files and a fresh manifest."""

import importlib.util
import json

import pytest

from coding_tutor.devserver.static import SECURITY_HEADERS
from coding_tutor.live.stores.redis import StoreError
from coding_tutor.paths import REPO_ROOT

ENV = {"KV_REST_API_URL": "https://example.upstash.io", "KV_REST_API_TOKEN": "test-token"}


def load_index(monkeypatch, env):
    for k in ("KV_REST_API_URL", "KV_REST_API_TOKEN", "UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    spec = importlib.util.spec_from_file_location("vercel_index", REPO_ROOT / "api" / "index.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_index_builds_a_wsgi_app_from_the_environment(monkeypatch):
    module = load_index(monkeypatch, ENV)
    assert callable(module.app)
    assert callable(module.build_app({**ENV, "CODING_TUTOR_ALLOWED_ORIGINS": "https://a.org, https://b.org"}))


def test_index_refuses_to_start_without_the_store(monkeypatch):
    with pytest.raises(StoreError, match="KV_REST_API_URL"):
        load_index(monkeypatch, {})


def test_index_answers_options_without_touching_the_store(monkeypatch):
    module = load_index(monkeypatch, ENV)
    out = {}
    body = module.app({"REQUEST_METHOD": "OPTIONS", "PATH_INFO": "/api/v1/events"}, lambda s, h: out.update(status=s))
    assert out["status"].startswith(("204", "200")) and isinstance(b"".join(body), bytes)


@pytest.fixture(scope="module")
def vercel():
    return json.loads((REPO_ROOT / "vercel.json").read_text(encoding="utf-8"))


def headers_for(vercel, source):
    return {h["key"]: h["value"] for rule in vercel["headers"] if rule["source"] == source for h in rule["headers"]}


def test_vercel_serves_web_and_routes_the_api(vercel):
    assert vercel["outputDirectory"] == "web"
    assert {"source": "/api/(.*)", "destination": "/api/index"} in vercel["rewrites"]
    assert "content/topics" in vercel["functions"]["api/index.py"]["includeFiles"]


def test_vercel_security_headers_match_the_dev_server(vercel):
    assert headers_for(vercel, "/(.*)") == dict(SECURITY_HEADERS)


def test_vercel_caching_matches_the_delivery_design(vercel):
    assert "immutable" in headers_for(vercel, "/data/topics/(.*)")["Cache-Control"]
    assert headers_for(vercel, "/data/manifest.json")["Cache-Control"] == "no-cache"
    assert headers_for(vercel, "/config.json")["Cache-Control"] == "no-cache"
