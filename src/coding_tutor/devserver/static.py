"""Minimal WSGI static-file app (standard library only) for local development.

Serves files under one directory, `index.html` for `/`, GET and HEAD only, and refuses any path
that resolves outside the directory.
"""

from __future__ import annotations

import mimetypes
from collections.abc import Callable, Iterable
from pathlib import Path
from urllib.parse import unquote

Environ = dict
StartResponse = Callable[[str, list[tuple[str, str]]], object]
WSGIApp = Callable[[Environ, StartResponse], Iterable[bytes]]

TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
}


def content_type(path: Path) -> str:
    """Return the Content-Type for a file name."""
    return TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def resolve(root: Path, url_path: str) -> Path | None:
    """Map a URL path to a file under `root`, or None when missing or outside `root`."""
    rel = unquote(url_path).lstrip("/") or "index.html"
    target = (root / rel).resolve()
    if not target.is_relative_to(root.resolve()):
        return None
    if target.is_dir():
        target = target / "index.html"
    return target if target.is_file() else None


def _text(start_response: StartResponse, status: str, text: str) -> list[bytes]:
    """Send a short plain-text response."""
    body = text.encode()
    start_response(status, [("Content-Type", "text/plain; charset=utf-8"), ("Content-Length", str(len(body)))])
    return [body]


def static_app(root: Path) -> WSGIApp:
    """Return a WSGI app serving the files under `root` (no caching, for development)."""

    def app(environ: Environ, start_response: StartResponse) -> Iterable[bytes]:
        method = environ.get("REQUEST_METHOD", "GET")
        if method not in ("GET", "HEAD"):
            return _text(start_response, "405 Method Not Allowed", "method not allowed")
        target = resolve(root, environ.get("PATH_INFO", "/"))
        if target is None:
            return _text(start_response, "404 Not Found", "not found")
        data = target.read_bytes()
        start_response(
            "200 OK",
            [
                ("Content-Type", content_type(target)),
                ("Content-Length", str(len(data))),
                ("Cache-Control", "no-cache"),
                ("X-Content-Type-Options", "nosniff"),
            ],
        )
        return [b""] if method == "HEAD" else [data]

    return app
