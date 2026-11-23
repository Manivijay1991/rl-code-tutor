"""Build data/codes.sqlite from the raw CMS downloads (run data/fetch_cms.py first).

Tables:
  icd10cm(code PRIMARY KEY, billable, short_desc, long_desc)   -- codes stored without the dot
  hcc_map(icd, model, hcc, valid_py)                          -- model: CMS-HCC-V28, RxHCC-V08, ESRD-V24
  hcc_coeff(model, segment, var, coeff, label)                -- V28 relative factors, e.g. CNA / HCC37 / 0.166
  hcc_label(model, hcc, label)
  hcc_hier(model, hcc, drops)                                 -- if `hcc` is present, `drops` is set to 0
  meta(key, value)

    python data/build_db.py
"""

from __future__ import annotations

import csv
import io
import re
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
SOFTWARE_ZIP = RAW / "model_software_py2026" / "software.zip"
V28_PACKAGE = "CMS-HCC software V2826.115.T1.zip"  # nested zip inside SOFTWARE_ZIP
V28_COEFF_MEMBER = "C2824T2N.csv"
V28_HIER_MEMBER = "V28115H1.TXT"
V28 = "CMS-HCC-V28"

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


def parse_coefficients(text: str):
    """C2824T2N.csv rows `CNA_HCC37,0.166, Diabetes with Chronic Complications` -> (segment, var, coeff, label)."""
    for line in text.splitlines()[1:]:
        parts = line.split(",", 2)
        if len(parts) < 2 or "_" not in parts[0]:
            continue
        segment, var = parts[0].strip().split("_", 1)
        yield segment, var, float(parts[1]), (parts[2].strip() if len(parts) > 2 else "")


def parse_hierarchy(text: str):
    """SAS `%SET0(CC=37, HIER=%STR(38 ));` -> (hcc, dropped hcc) pairs."""
    for cc, hier in re.findall(r"%SET0\(\s*CC=(\d+)\s*,\s*HIER=%STR\(([^)]*)\)", text):
        for drop in re.findall(r"\d+", hier):
            yield cc, drop


def hcc_labels(coeffs: list[tuple[str, str, float, str]]) -> dict[str, str]:
    """HCC number -> label, from any segment's HCC rows (labels are the same across segments)."""
    labels: dict[str, str] = {}
    for _, var, _, label in coeffs:
        m = re.fullmatch(r"HCC(\d+)", var)
        if m and label:
            labels.setdefault(m.group(1), label)
    return labels


def read_v28_software() -> tuple[str, str]:
    package = zipfile.ZipFile(io.BytesIO(zipfile.ZipFile(SOFTWARE_ZIP).read(V28_PACKAGE)))
    return package.read(V28_COEFF_MEMBER).decode("latin-1"), package.read(V28_HIER_MEMBER).decode("latin-1")


def build(db_path: Path = DB) -> None:
    for p in (ICD_ZIP, HCC_ZIP, SOFTWARE_ZIP):
        if not p.exists():
            raise SystemExit(f"missing {p}; run: python data/fetch_cms.py")
    icd_text = zipfile.ZipFile(ICD_ZIP).read(ICD_MEMBER).decode("latin-1")
    hcc_text = zipfile.ZipFile(HCC_ZIP).read(HCC_MEMBER).decode("latin-1")
    coeff_text, hier_text = read_v28_software()
    coeffs = list(parse_coefficients(coeff_text))

    tmp = db_path.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(
        """
        CREATE TABLE icd10cm(code TEXT PRIMARY KEY, billable INTEGER, short_desc TEXT, long_desc TEXT);
        CREATE TABLE hcc_map(icd TEXT, model TEXT, hcc TEXT, valid_py INTEGER,
                             PRIMARY KEY(icd, model, hcc));
        CREATE INDEX hcc_map_icd ON hcc_map(icd);
        CREATE TABLE hcc_coeff(model TEXT, segment TEXT, var TEXT, coeff REAL, label TEXT,
                               PRIMARY KEY(model, segment, var));
        CREATE TABLE hcc_label(model TEXT, hcc TEXT, label TEXT, PRIMARY KEY(model, hcc));
        CREATE TABLE hcc_hier(model TEXT, hcc TEXT, drops TEXT, PRIMARY KEY(model, hcc, drops));
        CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
        """
    )
    con.executemany("INSERT INTO icd10cm VALUES (?,?,?,?)", parse_order_file(icd_text))
    con.executemany("INSERT OR IGNORE INTO hcc_map VALUES (?,?,?,?)", parse_hcc_csv(hcc_text))
    con.executemany("INSERT INTO hcc_coeff VALUES (?,?,?,?,?)", ((V28, *c) for c in coeffs))
    con.executemany("INSERT INTO hcc_label VALUES (?,?,?)", ((V28, h, l) for h, l in hcc_labels(coeffs).items()))
    con.executemany("INSERT OR IGNORE INTO hcc_hier VALUES (?,?,?)", ((V28, *p) for p in parse_hierarchy(hier_text)))
    con.executemany(
        "INSERT INTO meta VALUES (?,?)",
        [
            ("icd10cm", "FY2027 (CMS order file)"),
            ("hcc_map", "PY2026 midyear final ICD-10 mappings"),
            ("hcc_model", f"PY2026 midyear final model software {V28_PACKAGE} ({V28_COEFF_MEMBER}, {V28_HIER_MEMBER})"),
        ],
    )
    con.commit()
    count = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    n_icd = count("SELECT COUNT(*) FROM icd10cm")
    n_bill = count("SELECT COUNT(*) FROM icd10cm WHERE billable=1")
    n_v28 = count("SELECT COUNT(DISTINCT icd) FROM hcc_map WHERE model='CMS-HCC-V28'")
    n_coeff = count("SELECT COUNT(*) FROM hcc_coeff")
    n_hier = count("SELECT COUNT(*) FROM hcc_hier")
    con.close()
    db_path.unlink(missing_ok=True)
    tmp.rename(db_path)
    print(f"built {db_path.name}: {n_icd:,} ICD-10-CM entries ({n_bill:,} billable), "
          f"{n_v28:,} codes mapped to V28 HCCs, {n_coeff:,} V28 coefficients, {n_hier} hierarchy drops")


if __name__ == "__main__":
    build()
    sys.exit(0)
