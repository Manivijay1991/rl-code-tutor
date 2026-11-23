import io
from pathlib import Path

import pytest

from coding_tutor.devserver.static import content_type, resolve, static_app


@pytest.fixture
def site(tmp_path):
    (tmp_path / "index.html").write_text("<h1>home</h1>", encoding="utf-8")
    (tmp_path / "js").mkdir()
    (tmp_path / "js" / "app.js").write_text("export {};", encoding="utf-8")
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "index.html").write_text("data", encoding="utf-8")
    (tmp_path.parent / "secret.txt").write_text("secret", encoding="utf-8")
    return tmp_path


def get(app, path, method="GET"):
    out = {}

    def start_response(status, headers):
        out["status"], out["headers"] = status, dict(headers)

    body = b"".join(app({"REQUEST_METHOD": method, "PATH_INFO": path, "wsgi.input": io.BytesIO()}, start_response))
    return out["status"], out["headers"], body


@pytest.mark.parametrize(
    ("name", "ctype"),
    [("a.js", "text/javascript"), ("a.mjs", "text/javascript"), ("a.json", "application/json"),
     ("a.css", "text/css"), ("a.png", "image/png"), ("a.unknownext", "application/octet-stream")],
)  # fmt: skip
def test_content_type(name, ctype):
    assert content_type(Path(name)).startswith(ctype)


def test_resolve(site):
    assert resolve(site, "/") == (site / "index.html").resolve()
    assert resolve(site, "/data/") == (site / "data" / "index.html").resolve()
    assert resolve(site, "/js/app%2Ejs") == (site / "js" / "app.js").resolve()
    assert resolve(site, "/missing.js") is None


@pytest.mark.parametrize("path", ["/../secret.txt", "/js/../../secret.txt", "/%2e%2e/secret.txt"])
def test_resolve_blocks_traversal(site, path):
    assert resolve(site, path) is None


def test_static_app_serves_files(site):
    status, headers, body = get(static_app(site), "/js/app.js")
    assert status == "200 OK" and body == b"export {};"
    assert headers["Content-Type"].startswith("text/javascript") and headers["Cache-Control"] == "no-cache"


def test_static_app_head_404_405(site):
    app = static_app(site)
    status, headers, body = get(app, "/", "HEAD")
    assert status == "200 OK" and body == b"" and headers["Content-Length"] == str(len("<h1>home</h1>"))
    assert get(app, "/nope")[0] == "404 Not Found"
    assert get(app, "/../secret.txt")[0] == "404 Not Found"
    assert get(app, "/", "POST")[0] == "405 Method Not Allowed"
