# Coding Tutor: project context for Claude Code

## What this is
A free, open-source practice tool for medical coding certification candidates, built mainly as a learning project in LLM + reinforcement learning. Primary audience: AAPC **CRC** (risk adjustment) candidates; **CIC** (inpatient) is the likely second target. Both exams use only free code sets.

## Decisions already made
- **Free content only.** Use ICD-10-CM + Official Guidelines, ICD-10-PCS, HCPCS Level II (not D codes) and its modifiers, CMS-HCC (V28), MS-DRG, POS codes.
- **Never include:** CPT codes/descriptors/guidelines or CPT modifiers (24, 25, 26, 50, 51, 57, 59, 76, 78, 79) — AMA licensed; CDT; NUBC/UB-04 codes; NCCI edit tables; AAPC/AHIMA/any third-party questions.
- **Non-commercial:** no ads, sponsorships, donations or paid tiers. Licenses: Apache-2.0 (code), CC BY-SA 4.0 (tables, scenarios, explanations).
- **Disclaimer:** not affiliated with or endorsed by AAPC, AHIMA, AMA or CMS.
- **Answers come from the rules engine, never the LLM.** The LLM only writes the clinical note and wording from slot values.
- **All decision tables are drafts** until a certified coder reviews them.
- **Coach mode never gives the answer directly.** Feedback guides the student to pick it themselves: up to 3 escalating hints with a re-pick after each; no hint names the correct code. The answer is shown only if the student asks after the hints run out. Getting it right on these re-picks is not the bandit reward (reward stays: next NEW question with the same confusion).

## Architecture
Installable package `coding_tutor` in a src layout (`src/coding_tutor/`); paths live in `coding_tutor/paths.py`.
Downloaded CMS files and `codes.sqlite` go in `data/` (gitignored); generated scenarios in `scenarios/`.
0. `cms/fetch.py`, `cms/build_db.py` — download the CMS files and build `data/codes.sqlite`.
1. `decision_tables/*.json` (package data) — rules as slots (deciding details) → correct codes, with confusions tagged per wrong answer.
2. `engine/rules.py` — resolves answers and checks every slot combination is covered; `engine/codes.py` code lookups; `engine/hcc.py` V28 hierarchy and weights (feedback only).
3. `llm/` — LLM clients: `config.py` (LLMConfig: provider, model, URL, API key; `config_from_env`), `transport.py` (injectable HTTP), `providers.py` (`ollama`, `openai_compatible`, `make_llm`). An LLM is any `(system, user, seed) -> str` function. API keys only via parameters or env vars, never CLI values, logs or files.
   `generator/scenarios.py` — picks slots, engine computes answer, the injected LLM (default: local Ollama) writes the note, a check confirms deciding details are present (and answer-changing phrases absent), output saved to `scenarios/<table>/<id>.json`. Note-writing hints live in the tables: `describe`, `exclusive`, `note_forbid`, `note_rules`, `question`.
4. `rl/` — simulator (`simulator.py`), policies (`policies.py`), experiment (`experiment.py`).
5. UI (TODO) — coach mode (hints, feedback, summary) and exam mode (sections, flag for review, countdown timer).

## RL design
- **Use a contextual Thompson-sampling bandit only** to choose *how to teach* after a wrong answer. Context = (confusion, miss count bucketed 1/2/3+).
- **Actions:** rule_refresh, contrast_pair, find_meat, guiding_question, walkthrough, easier_case.
- **Reward:** correct on a NEW question with the same confusion (never the immediate retry).
- **What to practice next:** simple rules (weakest confusion first + spaced review), not Q-learning.
- Q-learning is for learning experiments in the simulator only.
- Track each student's lean: overcoding vs undercoding.
- Simulation shows the loop works; it cannot prove the agent helps real students.

## Conventions
- Python 3.13, standard library first; Windows host (PowerShell), Ollama available locally on GPU.
- Tests use **pytest** (dev-only dependency, in `.venv`): `.\.venv\Scripts\python.exe -m pytest`.
- Keep everything runnable offline; no API keys in a public page.
- Verify codes against the current fiscal-year CMS files before trusting them.

## Coding standards
- Follow @docs/python-style.md (PEP 8, DRY, SOLID, type hints, Google-style docstrings).
- Functional style: plain functions over plain data (dicts, NamedTuples); no behavior classes.
  Apply SOLID through functions: each function has a single responsibility.
- Python 3.13; lint and format with `ruff` (rules in pyproject.toml).
- Standard library first; ask before adding a dependency.
- Inject dependencies (random.Random, policies, storage, LLM client) as parameters;
  policies implement one shared interface (`coding_tutor.rl.policies.Agent`): name, act(ctx), update(ctx, action, reward, next_ctx),
  where ctx = (confusion, miss bucket 1/2/3).
- No secrets, API keys, student identifiers or patient data in code, tests, fixtures or logs.

## Testing
- `pytest`; tests live in `tests/`, mirroring the source layout
  (`src/coding_tutor/engine/x.py` -> `tests/engine/test_x.py`, `src/coding_tutor/rl/x.py` -> `tests/rl/test_x.py`).
- Shared fixtures go in `tests/conftest.py`; use `parametrize` instead of copied test bodies.
- `pyproject.toml` puts `src/` on the pytest import path (`import coding_tutor...`); don't add sys.path hacks.
- Every new function: normal case, edge cases, invalid input.
- Every decision-table rule needs a case in `EXPECTED` (tests/engine/test_rules.py);
  the suite fails if a rule has none.
- Fixed random seeds in all RL and simulation tests; mark long runs `@pytest.mark.slow`.
- Commands (PowerShell):
  - `.\.venv\Scripts\python.exe -m ruff check .` and `.\.venv\Scripts\python.exe -m ruff format --check .`
  - `.\.venv\Scripts\python.exe -m pytest` (quick run: add `-m "not slow"`)
- Before calling a task done: ruff clean and all tests passing; report both results.
- Refactors must not change behavior: existing tests stay green without editing them,
  unless I approve a test change.

## Next tasks
1. Static UI from the mockup (coach mode first), reading `scenarios/*.json`. HCC weights appear only in feedback (`risk_score_gap`), never in grading.
2. Decision tables for CRC: acceptable sources, status codes; more MEAT conditions.
3. Certified-coder review of tables and generated scenarios.
4. Later: AWS backend (API Gateway + Lambda + DynamoDB) for logging and the live bandit.