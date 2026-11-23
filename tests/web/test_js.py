"""Run the web UI's JavaScript tests (tests/web/*.test.mjs, Node's built-in runner) inside pytest."""

import shutil
import subprocess
from pathlib import Path

import pytest

from coding_tutor.paths import REPO_ROOT

NODE = shutil.which("node")
JS_TESTS = sorted(Path(__file__).parent.glob("*.test.mjs"))


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_web_js_suite():
    assert JS_TESTS, "no JS tests found"
    result = subprocess.run(
        [NODE, "--test", *map(str, JS_TESTS)], cwd=REPO_ROOT, capture_output=True, text=True, timeout=120, check=False
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
