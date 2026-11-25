"""File locations used across the package.

Content (CC BY-SA) lives in `content/` at the repository root: one folder per topic under `topics/`
(see `coding_tutor.catalog`, the only module that knows that layout), plus `hcc_groups.json` and
`references.json`. JSON Schemas shared by Python and JavaScript are in `schemas/`. Downloaded CMS files
and local databases go in `data/` (not committed). Override with environment variables when running elsewhere:

    CODING_TUTOR_CONTENT     folder holding topics/, hcc_groups.json and references.json
    CODING_TUTOR_DATA        folder for CMS downloads and SQLite databases

When the package is installed outside the repository (e.g. a serverless function), the content and
schema folders fall back to `./content` and `./schemas` under the working directory.
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent.parent


def repo_or_cwd(name: str, repo_root: Path = REPO_ROOT, cwd: Path | None = None) -> Path:
    """Return `<repo_root>/<name>` when it is a folder, else `<cwd>/<name>` (an installed package)."""
    repo = repo_root / name
    return repo if repo.is_dir() else (cwd or Path.cwd()) / name


def _content_dir() -> Path:
    """Return the content folder: env override, the repository's, or ./content."""
    if os.environ.get("CODING_TUTOR_CONTENT"):
        return Path(os.environ["CODING_TUTOR_CONTENT"])
    return repo_or_cwd("content")


CONTENT_DIR = _content_dir()
TOPICS_DIR = CONTENT_DIR / "topics"
HCC_GROUPS_PATH = CONTENT_DIR / "hcc_groups.json"
REFERENCES_PATH = CONTENT_DIR / "references.json"
SCHEMAS_DIR = repo_or_cwd("schemas")

DATA_DIR = Path(os.environ.get("CODING_TUTOR_DATA", REPO_ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
DB_PATH = DATA_DIR / "codes.sqlite"
API_DB_PATH = DATA_DIR / "api.sqlite"

WEB_DIR = REPO_ROOT / "web"
WEB_DATA_DIR = WEB_DIR / "data"
MANIFEST_PATH = WEB_DATA_DIR / "manifest.json"
