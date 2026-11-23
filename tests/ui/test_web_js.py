"""Run the web UI's JavaScript tests (Node's built-in runner) as part of the pytest suite."""

import shutil
import subprocess

import pytest

from coding_tutor.paths import WEB_DIR

NODE = shutil.which("node")


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_web_js_suite():
    result = subprocess.run(
        [NODE, "--test", "test/*.test.mjs"], cwd=WEB_DIR, capture_output=True, text=True, timeout=120, check=False
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
