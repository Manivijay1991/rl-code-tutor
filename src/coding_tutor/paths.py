"""File locations used across the package.

Content (decision tables and scenarios, CC BY-SA) lives in `content/` at the repository root, and the
JSON Schemas shared by Python and JavaScript in `schemas/`. Downloaded CMS files and local databases go
in `data/` (not committed). Override with environment variables when running elsewhere:

    CODING_TUTOR_CONTENT     folder holding tables/ and scenarios/
    CODING_TUTOR_DATA        folder for CMS downloads and SQLite databases
    CODING_TUTOR_SCENARIOS   where generated scenarios are written and read

When the package is installed outside the repository (e.g. a serverless function), the content folder
falls back to `./content` under the working directory.
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent.parent


def _content_dir() -> Path:
    """Return the content folder: env override, the repository's, or ./content."""
    if os.environ.get("CODING_TUTOR_CONTENT"):
        return Path(os.environ["CODING_TUTOR_CONTENT"])
    repo = REPO_ROOT / "content"
    return repo if repo.is_dir() else Path.cwd() / "content"


CONTENT_DIR = _content_dir()
TABLES_DIR = CONTENT_DIR / "tables"
SCENARIOS_DIR = Path(os.environ.get("CODING_TUTOR_SCENARIOS", CONTENT_DIR / "scenarios"))
SCHEMAS_DIR = REPO_ROOT / "schemas"

DATA_DIR = Path(os.environ.get("CODING_TUTOR_DATA", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "codes.sqlite"
API_DB_PATH = DATA_DIR / "api.sqlite"

WEB_DIR = REPO_ROOT / "web"
BUNDLE_PATH = WEB_DIR / "data" / "bundle.json"
