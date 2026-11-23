import threading
import urllib.request

import pytest

from coding_tutor.ui import serve


def test_serves_files_on_localhost_only(tmp_path):
    (tmp_path / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
    server = serve.make_server(tmp_path, port=0)
    host, port = server.server_address[:2]
    assert host == "127.0.0.1"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=5) as resp:
            assert resp.read() == b"<h1>ok</h1>"
    finally:
        server.shutdown()
        server.server_close()


def test_main_requires_bundle(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(serve, "BUNDLE_PATH", tmp_path / "missing.json")
    assert serve.main(["--no-browser"]) == 1
    assert "coding_tutor.ui.export" in capsys.readouterr().err


def test_parse_args():
    args = serve.parse_args(["--port", "9000", "--no-browser"])
    assert (args.port, args.no_browser) == (9000, True)
    with pytest.raises(SystemExit):
        serve.parse_args(["--po", "1"])  # no abbreviations
