"""File locations used across the package.

Decision tables ship inside the package. Downloaded CMS files, the built code database and
generated scenarios live outside it, under the repository root by default; set
`CODING_TUTOR_DATA` / `CODING_TUTOR_SCENARIOS` to put them elsewhere.
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent.parent

TABLES_DIR = PACKAGE_DIR / "decision_tables"
DATA_DIR = Path(os.environ.get("CODING_TUTOR_DATA", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "codes.sqlite"
SCENARIOS_DIR = Path(os.environ.get("CODING_TUTOR_SCENARIOS", REPO_ROOT / "scenarios"))
WEB_DIR = REPO_ROOT / "web"
BUNDLE_PATH = WEB_DIR / "data" / "bundle.json"
