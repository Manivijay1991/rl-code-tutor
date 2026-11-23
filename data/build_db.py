"""Build data/codes.sqlite from the raw CMS downloads (run data/fetch_cms.py first).

Tables:
  icd10cm(code PRIMARY KEY, billable, short_desc, long_desc)   -- codes stored without the dot
  hcc_map(icd, model, hcc, valid_py)                          -- model: CMS-HCC-V28, RxHCC-V08, ESRD-V24
  meta(key, value)

    python data/build_db.py
"""

from __future__ import annotations

import csv
import io
import sqlite3
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
DB = HERE / "codes.sqlite"

ICD_ZIP = RAW / "icd10cm_fy2027" / "codes.zip"
ICD_MEMBER = "Code Descriptions/icd10cm_order_2027.txt"
HCC_ZIP = RAW / "hcc_map_py2026" / "map.zip"
HCC_MEMBER = "2026 Final ICD-10-CM Mappings.csv"

# CSV column header -> (model name, column holding "valid for payment year" Yes/No)
HCC_COLUMNS = {
    "CMS-HCC Model Category V28": ("CMS-HCC-V28", "CMS-HCC Model Category V28 for 2026 Payment Year"),
    "RxHCC Model Category V08": ("RxHCC-V08", "RxHCC Model Category V08 for 2026 Payment Year"),
    "CMS-HCC ESRD Model Category V24": ("ESRD-V24", "CMS-HCC ESRD Model Category V24 for 2026 Payment Year"),
}


def parse_order_file(text: str):
    """Fixed-width CMS order file: order(5) code(7) billable(1) short(60) long."""
    for line in text.splitlines():
        if len(line) < 16:
            continue
        code = line[6:13].strip()
        billable = line[14] == "1"
        short = line[16:76].strip()
        long_ = line[77:].strip() or short
        yield code, billable, short, long_


def parse_hcc_csv(text: str):
    rows = list(csv.reader(io.StringIO(text)))
    header_idx = next(i for i, r in enumerate(rows) if r and r[0].replace("\n", " ").strip() == "Diagnosis Code")
    header = [c.replace("\n", " ").strip() for c in rows[header_idx]]
    col = {name: i for i, name in enumerate(header)}
    for r in rows[header_idx + 1:]:
        if not r or not r[0].strip() or " " in r[0].strip():
            continue  # blank lines and the trailing "Output:/Source:" notes
        icd = r[0].strip()
        for src, (model, valid_col) in HCC_COLUMNS.items():
            hcc = r[col[src]].strip()
            if hcc:
                yield icd, model, hcc, r[col[valid_col]].strip() == "Yes"


def build(db_path: Path = DB) -> None:
    for p in (ICD_ZIP, HCC_ZIP):
        if not p.exists():
            raise SystemExit(f"missing {p}; run: python data/fetch_cms.py")
    icd_text = zipfile.ZipFile(ICD_ZIP).read(ICD_MEMBER).decode("latin-1")
    hcc_text = zipfile.ZipFile(HCC_ZIP).read(HCC_MEMBER).decode("latin-1")

    tmp = db_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(
        """
        CREATE TABLE icd10cm(code TEXT PRIMARY KEY, billable INTEGER, short_desc TEXT, long_desc TEXT);
        CREATE TABLE hcc_map(icd TEXT, model TEXT, hcc TEXT, valid_py INTEGER,
                             PRIMARY KEY(icd, model, hcc));
        CREATE INDEX hcc_map_icd ON hcc_map(icd);
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
        """
    )
    con.executemany("INSERT INTO icd10cm VALUES (?,?,?,?)", parse_order_file(icd_text))
    con.executemany("INSERT OR IGNORE INTO hcc_map VALUES (?,?,?,?)", parse_hcc_csv(hcc_text))
    con.executemany(
        "INSERT INTO meta VALUES (?,?)",
        [("icd10cm", "FY2027 (CMS order file)"), ("hcc_map", "PY2026 midyear final ICD-10 mappings")],
    )
    con.commit()
    n_icd = con.execute("SELECT COUNT(*) FROM icd10cm").fetchone()[0]
    n_bill = con.execute("SELECT COUNT(*) FROM icd10cm WHERE billable=1").fetchone()[0]
    n_v28 = con.execute("SELECT COUNT(DISTINCT icd) FROM hcc_map WHERE model='CMS-HCC-V28'").fetchone()[0]
    con.close()
    db_path.unlink(missing_ok=True)
    tmp.rename(db_path)
    print(f"built {db_path.name}: {n_icd:,} ICD-10-CM entries ({n_bill:,} billable), {n_v28:,} codes mapped to V28 HCCs")


if __name__ == "__main__":
    build()
    sys.exit(0)
