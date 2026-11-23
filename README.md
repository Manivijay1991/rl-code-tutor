# rl-code-tutor

A free, non-commercial practice tool for **CRC (risk adjustment) coding** candidates. A rules engine
decides every answer; a Thompson-sampling bandit chooses *how to teach* after a wrong answer.

> Not affiliated with or endorsed by AAPC, AHIMA, AMA or CMS. All decision tables are **drafts**
> until reviewed by a certified coder. Not for production coding.

## Setup (Windows / PowerShell)

```powershell
python data\fetch_cms.py          # download CMS files into data\raw\ (not committed)
python data\build_db.py           # build data\codes.sqlite
python -m engine.rules_engine     # check every decision table
python -m rl.run_experiment       # compare teaching policies in the simulator

python -m venv .venv; .\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest
```

Resolve a single case:

```powershell
python -m engine.rules_engine diabetes_complications dm_type=type2 complication=ckd_stage4 provider_says_unrelated=no meds=insulin
```

## Code sources (free, public)

| Source | Version | Used for |
|---|---|---|
| CMS ICD-10-CM code descriptions (order file) | FY2027 | code validity, billable flag |
| CMS ICD-10 mappings (CMS-HCC V28, RxHCC V08, ESRD V24) | PY2026 midyear final | ICD → HCC |
| ICD-10-CM Official Guidelines | FY2027 | cited by section in explanations |

No CPT, CDT, NUBC or NCCI content, and no third-party exam questions.

## Decision tables

| Table | Combos | Status |
|---|---|---|
| `diabetes_complications` | 35 | draft |
| `ckd_staging` | 18 | draft |
| `meat_support` | 9 | draft |

`hcc_v28_hierarchy.json` holds hand-entered HCC labels and hierarchies (draft; verify against the CMS model software).

## Licenses

Code: Apache-2.0. Decision tables, scenarios and explanations: CC BY-SA 4.0.
