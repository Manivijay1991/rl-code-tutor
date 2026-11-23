"""Run the live bandit API locally (single process, SQLite).

    python -m coding_tutor.live.server                       # http://127.0.0.1:8780, data/api.sqlite
    python -m coding_tutor.live.server --allow-origin https://tutor.example.org

For production, mount `make_app(...)` from coding_tutor.live.app on a WSGI host and replace the
SQLite storage with a hosted database.
"""

from __future__ import annotations

import argparse
import sys
import wsgiref.simple_server
from pathlib import Path

from coding_tutor.engine.rules import load_tables
from coding_tutor.live.app import make_app
from coding_tutor.live.policy import known_confusions
from coding_tutor.live.stores import sqlite as storage
from coding_tutor.paths import API_DB_PATH

HOST = "127.0.0.1"
DEFAULT_ORIGINS = ("http://127.0.0.1:8765", "http://localhost:8765")

# The default handler logs every request with the client's IP address; this one logs nothing.
QuietHandler = type("QuietHandler", (wsgiref.simple_server.WSGIRequestHandler,), {"log_message": lambda *_: None})


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    ap = argparse.ArgumentParser(description="Run the Coding Tutor live bandit API.", allow_abbrev=False)
    ap.add_argument("--port", type=int, default=8780)
    ap.add_argument("--db", type=Path, default=API_DB_PATH)
    ap.add_argument(
        "--allow-origin", action="append", help="browser origin allowed by CORS (repeatable; default: local UI)"
    )
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Serve the API until interrupted."""
    args = parse_args(argv)
    con = storage.connect(args.db)
    app = make_app(con, known_confusions(load_tables()), args.allow_origin or DEFAULT_ORIGINS)
    server = wsgiref.simple_server.make_server(HOST, args.port, app, handler_class=QuietHandler)
    print(f"Live bandit API at http://{HOST}:{args.port}/v1/policy  (db: {args.db}; Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
