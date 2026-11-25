"""Serve the web UI on localhost (standard library only).

    python -m coding_tutor.devserver.serve                 # UI + live bandit API at /api (SQLite), like Vercel
    python -m coding_tutor.devserver.serve --no-api        # static UI only (the page then runs offline)
    python -m coding_tutor.devserver.serve --port 9000 --no-browser

By default the UI and the API share one origin, exactly as on Vercel: the API answers under /api/v1/...,
and /config.json is answered with {"api": "/api"}. `--with-api` is still accepted (it is the default).
Run `coding-tutor-export-ui` first so web/data/manifest.json exists.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
import sys
import webbrowser
import wsgiref.simple_server
from collections.abc import Iterable
from pathlib import Path

from coding_tutor.devserver.static import Environ, StartResponse, WSGIApp, static_app
from coding_tutor.engine.rules import load_tables
from coding_tutor.live.app import PREFIX, make_app
from coding_tutor.live.policy import known_confusions
from coding_tutor.live.server import request_handler
from coding_tutor.live.stores import sqlite as storage
from coding_tutor.paths import API_DB_PATH, MANIFEST_PATH, WEB_DIR

HOST = "127.0.0.1"

ThreadingWSGIServer = type(
    "ThreadingWSGIServer", (socketserver.ThreadingMixIn, wsgiref.simple_server.WSGIServer), {"daemon_threads": True}
)


def make_server(directory: Path = WEB_DIR, port: int = 8765) -> http.server.ThreadingHTTPServer:
    """Return a static-only HTTP server for `directory`, bound to localhost only."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    return http.server.ThreadingHTTPServer((HOST, port), handler)


def dev_app(web_dir: Path, api: WSGIApp) -> WSGIApp:
    """Return one WSGI app: `/api/...` -> the bandit API, `/config.json` -> same-origin API, else static files."""
    files = static_app(web_dir)
    config = json.dumps({"api": PREFIX}).encode()

    def app(environ: Environ, start_response: StartResponse) -> Iterable[bytes]:
        path = environ.get("PATH_INFO", "/")
        if path == PREFIX or path.startswith(PREFIX + "/"):
            return api(environ, start_response)
        if path == "/config.json":
            start_response("200 OK", [("Content-Type", "application/json"), ("Content-Length", str(len(config)))])
            return [config]
        return files(environ, start_response)

    return app


def make_dev_server(
    directory: Path = WEB_DIR, port: int = 8765, db: Path = API_DB_PATH, log: bool = False
) -> wsgiref.simple_server.WSGIServer:
    """Return a localhost server for the UI plus the live bandit API on SQLite at `db`.

    Args:
        directory: Folder served as the UI.
        port: Port on 127.0.0.1 (0 = any free port).
        db: SQLite file for the API.
        log: Print each request (time, path, status; never the client's address).
    """
    api = make_app(storage.connect(db), known_confusions(load_tables()), allowed_origins=())
    return wsgiref.simple_server.make_server(
        HOST, port, dev_app(directory, api), server_class=ThreadingWSGIServer, handler_class=request_handler(log)
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    ap = argparse.ArgumentParser(description="Serve the Coding Tutor web UI locally.", allow_abbrev=False)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    ap.add_argument("--no-api", dest="with_api", action="store_false", help="static UI only, without the live API")
    ap.add_argument("--with-api", dest="with_api", action="store_true", help="run the live API at /api (the default)")
    ap.add_argument("--db", type=Path, default=API_DB_PATH, help="SQLite file for the API")
    ap.add_argument("--log", action="store_true", help="print each request (time, path, status; never the IP)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Serve web/ (and optionally the API) until interrupted."""
    args = parse_args(argv)
    if not MANIFEST_PATH.exists():
        print(f"{MANIFEST_PATH} is missing; run: coding-tutor-export-ui", file=sys.stderr)
        return 1
    server = (
        make_dev_server(WEB_DIR, args.port, args.db, args.log) if args.with_api else make_server(WEB_DIR, args.port)
    )
    url = f"http://{HOST}:{args.port}/"
    extra = f"; live bandit API at {url}api/v1/policy (db: {args.db})" if args.with_api else ""
    print(f"Coding Tutor at {url}{extra}  (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
