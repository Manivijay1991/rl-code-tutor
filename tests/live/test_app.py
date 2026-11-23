import io
import json
import threading
import urllib.request
import wsgiref.simple_server

import pytest

from coding_tutor.live import server
from coding_tutor.live.app import api_path, make_app, make_rate_limiter
from coding_tutor.live.policy import known_confusions
from coding_tutor.live.stores import Store
from coding_tutor.live.stores import sqlite as storage

CONFUSIONS = frozenset({"dm:missed_with_link"})
EVENT = {"confusion": "dm:missed_with_link", "bucket": 1, "action": "contrast_pair", "reward": 1}
ORIGIN = "http://127.0.0.1:8765"


@pytest.fixture
def con():
    return storage.connect(":memory:")


def call(app, method="GET", path="/v1/health", body=None, content_type="application/json", origin=None, ip="10.0.0.1"):
    raw = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else b""
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_TYPE": content_type,
        "CONTENT_LENGTH": str(len(raw)),
        "wsgi.input": io.BytesIO(raw),
        "REMOTE_ADDR": ip,
    }
    if origin:
        environ["HTTP_ORIGIN"] = origin
    out = {}

    def start_response(status, headers):
        out["status"], out["headers"] = status, dict(headers)

    data = b"".join(app(environ, start_response))
    return out["status"], out["headers"], json.loads(data) if data else None


def test_health(con):
    assert call(make_app(con, CONFUSIONS))[0] == "200 OK"


def test_post_then_policy(con):
    app = make_app(con, CONFUSIONS, day=lambda: "2026-11-23")
    status, _, body = call(app, "POST", "/v1/events", {"events": [EVENT, {**EVENT, "reward": 0}], "client": "web/0.1"})
    assert (status, body) == ("202 Accepted", {"accepted": 2})
    status, headers, body = call(app, "GET", "/v1/policy")
    assert status == "200 OK" and "max-age" in headers["Cache-Control"]
    assert body == {"version": 1, "events": 2, "arms": {"dm:missed_with_link|1|contrast_pair": [1, 1]}}


@pytest.mark.parametrize(
    ("kwargs", "status"),
    [
        ({"body": {"events": [{**EVENT, "action": "nap"}]}}, "400 Bad Request"),
        ({"body": b"{not json"}, "400 Bad Request"),
        ({"body": b""}, "400 Bad Request"),
        ({"body": {"events": [EVENT]}, "content_type": "text/plain"}, "415 Unsupported Media Type"),
        ({"body": b"x" * (64 * 1024 + 1)}, "413 Payload Too Large"),
    ],
    ids=["bad_event", "bad_json", "empty", "content_type", "too_large"],
)
def test_post_rejects(con, kwargs, status):
    got, _, body = call(make_app(con, CONFUSIONS), "POST", "/v1/events", **kwargs)
    assert got == status and body["error"]
    assert storage.total_events(con) == 0


def test_routes_and_methods(con):
    app = make_app(con, CONFUSIONS)
    assert call(app, "GET", "/nope")[0] == "404 Not Found"
    status, headers, _ = call(app, "GET", "/v1/events")
    assert status == "405 Method Not Allowed" and headers["Allow"] == "POST"
    assert call(app, "GET", "/v1/policy/")[0] == "200 OK"  # trailing slash


@pytest.mark.parametrize(
    ("raw", "path"),
    [("/api/v1/policy", "/v1/policy"), ("/api", "/"), ("/api/", "/"), ("/v1/policy/", "/v1/policy"),
     ("/apix/v1", "/apix/v1"), ("/", "/")],
)  # fmt: skip
def test_api_path(raw, path):
    assert api_path(raw) == path


def test_same_origin_prefix_routes(con):
    app = make_app(con, CONFUSIONS)
    assert call(app, "POST", "/api/v1/events", {"events": [EVENT]})[0] == "202 Accepted"
    assert call(app, "GET", "/api/v1/policy")[2]["events"] == 1


def test_custom_store_is_used():
    calls = []
    store = Store(
        record=lambda events, day, client="": calls.append((list(events), day, client)) or 1,
        arm_rows=lambda: [("dm:missed_with_link", 1, "walkthrough", 5, 2)],
        total_events=lambda: 7,
    )
    app = make_app(None, CONFUSIONS, store=store, day=lambda: "d")
    assert call(app, "POST", "/v1/events", {"events": [EVENT], "client": "t"})[0] == "202 Accepted"
    assert calls[0][1:] == ("d", "t")
    assert call(app, "GET", "/v1/policy")[2]["arms"] == {"dm:missed_with_link|1|walkthrough": [5, 2]}


def test_make_app_needs_storage():
    with pytest.raises(ValueError, match="connection or a store"):
        make_app(None, CONFUSIONS)


def test_cors_only_for_allowed_origins(con):
    app = make_app(con, CONFUSIONS, allowed_origins=[ORIGIN])
    status, headers, _ = call(app, "OPTIONS", "/v1/events", origin=ORIGIN)
    assert status == "204 No Content" and headers["Access-Control-Allow-Origin"] == ORIGIN
    assert "Access-Control-Allow-Origin" not in call(app, "GET", "/v1/policy", origin="https://evil.example")[1]
    any_app = make_app(con, CONFUSIONS, allowed_origins=["*"])
    assert call(any_app, "GET", "/v1/policy", origin="https://x.org")[1]["Access-Control-Allow-Origin"] == "*"


def test_rate_limit_per_client(con):
    clock = [0.0]
    app = make_app(con, CONFUSIONS, limiter=make_rate_limiter(capacity=3, per_second=1, clock=lambda: clock[0]))
    post = lambda ip: call(app, "POST", "/v1/events", {"events": [EVENT, EVENT]}, ip=ip)[0]  # noqa: E731
    assert post("a") == "202 Accepted"
    assert post("a") == "429 Too Many Requests"  # 1 token left, batch costs 2
    assert post("b") == "202 Accepted"  # other client unaffected
    clock[0] += 5
    assert post("a") == "202 Accepted"  # refilled
    assert storage.total_events(con) == 6


def test_rate_limiter_unit():
    t = [0.0]
    allow = make_rate_limiter(capacity=2, per_second=0.5, clock=lambda: t[0])
    assert allow("k", 2) and not allow("k", 1)
    t[0] += 2
    assert allow("k", 1) and not allow("k", 1)
    assert not allow("k", 3)


def test_server_runs_end_to_end(tmp_path, tables):
    con = storage.connect(tmp_path / "api.sqlite")
    app = make_app(con, known_confusions(tables), [ORIGIN])
    httpd = wsgiref.simple_server.make_server("127.0.0.1", 0, app, handler_class=server.QuietHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    port = httpd.server_address[1]
    try:
        body = json.dumps({"events": [{**EVENT, "confusion": "diabetes_complications:missed_with_link"}]}).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/v1/events", body, {"Content-Type": "application/json", "Origin": ORIGIN}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 202 and resp.headers["Access-Control-Allow-Origin"] == ORIGIN
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/policy", timeout=5) as resp:
            assert json.loads(resp.read())["events"] == 1
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_server_parse_args(tmp_path):
    args = server.parse_args(["--port", "9001", "--db", str(tmp_path / "x.sqlite"), "--allow-origin", "https://a.org"])
    assert (args.port, args.allow_origin) == (9001, ["https://a.org"])
    with pytest.raises(SystemExit):
        server.parse_args(["--allow", "x"])  # no abbreviations
