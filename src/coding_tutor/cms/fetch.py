"""Download the free CMS code files this project uses into data/raw/.

All sources are US government publications (CMS / NCHS) that are free to use.
Raw downloads are not committed; run this module to recreate them.

    python -m coding_tutor.cms.fetch            # skip files that already exist
    python -m coding_tutor.cms.fetch --force    # download again
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path

from coding_tutor.paths import RAW_DIR

USER_AGENT = "coding-tutor-fetch/0.1"
Download = Callable[[str], bytes]

# Pin versions here. Bump them deliberately and re-run the tests afterwards.
SOURCES = {
    # ICD-10-CM FY2027 (effective 2026-10-01): code list with billable flag.
    "icd10cm_fy2027/codes.zip": "https://www.cms.gov/files/zip/2027-code-descriptions-tabular-order.zip",
    # CMS-HCC / RxHCC / ESRD ICD-10 mappings, payment year 2026 midyear final.
    "hcc_map_py2026/map.zip": "https://www.cms.gov/files/zip/2026-midyear-final-icd-10-mappings.zip",
    # CMS-HCC model software (SAS), payment year 2026 midyear final: V28 weights + hierarchies.
    "model_software_py2026/software.zip": "https://www.cms.gov/files/zip/2026-midyear-final-model-software.zip",
}


def http_get(url: str, timeout: int = 120) -> bytes:
    """Download a URL and return its body."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch(rel: str, url: str, force: bool = False, raw_dir: Path = RAW_DIR, get: Download = http_get) -> Path:
    """Download one source into `raw_dir/rel` unless it already exists.

    Args:
        rel: Path under `raw_dir`.
        url: Source URL.
        force: Download even if the file exists.
        raw_dir: Destination root.
        get: Downloader (injected for tests).

    Returns:
        The local path.
    """
    dest = Path(raw_dir) / rel
    if dest.exists() and not force:
        print(f"exists  {rel}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = get(url)
    dest.write_bytes(data)
    print(f"fetched {rel}  {len(data):,} bytes  sha256={hashlib.sha256(data).hexdigest()[:16]}")
    return dest


def main(argv: list[str] | None = None) -> int:
    """Download every source; `--force` downloads again."""
    argv = sys.argv[1:] if argv is None else argv
    for rel, url in SOURCES.items():
        fetch(rel, url, force="--force" in argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
