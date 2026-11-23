"""Serve the static web UI on localhost (standard library only).

    python -m coding_tutor.ui.serve            # http://127.0.0.1:8765
    python -m coding_tutor.ui.serve --port 9000 --no-browser

Run `python -m coding_tutor.ui.export` first so web/data/bundle.json exists.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import sys
import webbrowser
from pathlib import Path

from coding_tutor.paths import BUNDLE_PATH, WEB_DIR

HOST = "127.0.0.1"


def make_server(directory: Path = WEB_DIR, port: int = 8765) -> http.server.ThreadingHTTPServer:
    """Return an HTTP server for `directory`, bound to localhost only."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    return http.server.ThreadingHTTPServer((HOST, port), handler)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    ap = argparse.ArgumentParser(description="Serve the Coding Tutor web UI locally.", allow_abbrev=False)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Serve web/ until interrupted."""
    args = parse_args(argv)
    if not BUNDLE_PATH.exists():
        print(f"{BUNDLE_PATH} is missing; run: python -m coding_tutor.ui.export", file=sys.stderr)
        return 1
    server = make_server(WEB_DIR, args.port)
    url = f"http://{HOST}:{args.port}/"
    print(f"Coding Tutor at {url}  (Ctrl+C to stop)")
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
