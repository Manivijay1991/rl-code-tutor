"""Download the free CMS code files this project uses into data/raw/.

All sources are US government publications (CMS / NCHS) that are free to use.
Raw downloads are not committed; run this script to recreate them.

    python data/fetch_cms.py
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

RAW = Path(__file__).resolve().parent / "raw"

# Pin versions here. Bump them deliberately and re-run the tests afterwards.
SOURCES = {
    # ICD-10-CM FY2027 (effective 2026-10-01): code list with billable flag.
    "icd10cm_fy2027/codes.zip": "https://www.cms.gov/files/zip/2027-code-descriptions-tabular-order.zip",
    # CMS-HCC / RxHCC / ESRD ICD-10 mappings, payment year 2026 midyear final.
    "hcc_map_py2026/map.zip": "https://www.cms.gov/files/zip/2026-midyear-final-icd-10-mappings.zip",
}


def fetch(rel: str, url: str, force: bool = False) -> Path:
    dest = RAW / rel
    if dest.exists() and not force:
        print(f"exists  {rel}")
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "coding-tutor-fetch/0.1"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    dest.write_bytes(data)
    print(f"fetched {rel}  {len(data):,} bytes  sha256={hashlib.sha256(data).hexdigest()[:16]}")
    return dest


def main(argv: list[str]) -> int:
    force = "--force" in argv
    for rel, url in SOURCES.items():
        fetch(rel, url, force)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
