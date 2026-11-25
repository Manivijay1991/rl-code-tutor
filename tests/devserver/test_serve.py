import json
import threading
import urllib.request

import pytest

from coding_tutor.devserver import serve


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


def test_main_requires_the_exported_manifest(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(serve, "MANIFEST_PATH", tmp_path / "missing.json")
    assert serve.main(["--no-browser"]) == 1
    assert "coding-tutor-export-ui" in capsys.readouterr().err


def test_dev_server_serves_ui_config_and_api(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<h1>ui</h1>", encoding="utf-8")
    (web / "config.json").write_text('{"api": null}', encoding="utf-8")
    server = serve.make_dev_server(web, port=0, db=tmp_path / "api.sqlite")
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(f"{base}/", timeout=5) as resp:
            assert resp.read() == b"<h1>ui</h1>"
        with urllib.request.urlopen(f"{base}/config.json", timeout=5) as resp:
            assert json.loads(resp.read()) == {"api": "/api"}  # overrides the file on disk
        event = {
            "confusion": "diabetes_complications:missed_with_link",
            "miss_level": 1,
            "action": "walkthrough",
            "reward": 1,
        }
        req = urllib.request.Request(
            f"{base}/api/v1/events", json.dumps({"events": [event]}).encode(), {"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 202
        with urllib.request.urlopen(f"{base}/api/v1/policy", timeout=5) as resp:
            assert json.loads(resp.read())["events"] == 1
    finally:
        server.shutdown()
        server.server_close()
    assert json.loads((web / "config.json").read_text(encoding="utf-8")) == {"api": None}


def test_parse_args():
    args = serve.parse_args(["--port", "9000", "--no-browser"])
    assert (args.port, args.no_browser, args.with_api) == (9000, True, True)  # the API is on by default
    assert serve.parse_args(["--with-api"]).with_api is True
    assert serve.parse_args(["--no-api"]).with_api is False
    with pytest.raises(SystemExit):
        serve.parse_args(["--po", "1"])  # no abbreviations
