# CRC Coding Tutor: project context for Claude Code

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
Repository layout (one meaning per name):
```
content/         CC BY-SA, reviewed by certified coders: tables/*.json, scenarios/<table>/<id>.json
schemas/         JSON Schemas = the contract between Python and JS: table, scenario, bundle, event
src/coding_tutor/  Apache-2.0 package (paths in paths.py; schema.py = stdlib validator for schemas/)
web/             static app = the deploy root: index.html (home) + practice.html (assessment), css/, js/, fonts/ (Inter, OFL), config.json, data/bundle.json [built]
tests/           ALL tests: Python mirrors src/coding_tutor/, tests/web/ mirrors web/js/
data/            local only (gitignored): CMS downloads, codes.sqlite, api.sqlite
```
Pipeline inside `src/coding_tutor/`:
0. `cms/` — `fetch.py`, `build_db.py`: download CMS files, build `data/codes.sqlite`.
1. `content/tables/*.json` — rules as slots (deciding details) → correct codes, with confusions tagged per wrong answer; shape in `schemas/table.schema.json`. Slot `label`/`labels` are student-facing wording used by hints.
2. `engine/` — `rules.py` resolves answers and checks every slot combination is covered; `codes.py` code lookups; `hcc.py` V28 hierarchy and weights (feedback only).
3. `llm/` — LLM clients: `config.py` (LLMConfig: provider, model, URL, API key; `config_from_env`), `transport.py` (injectable HTTP), `providers.py` (`ollama`, `openai_compatible`, `make_llm`). An LLM is any `(system, user, seed) -> str` function. API keys only via parameters or env vars, never CLI values, logs or files.
   `generator/scenarios.py` — picks slots, engine computes answer, the injected LLM (default: local Ollama) writes the note, a check confirms deciding details are present (and answer-changing phrases absent), output saved to `content/scenarios/<table>/<id>.json`. Note-writing hints live in the tables: `describe`, `exclusive`, `note_forbid`, `note_rules`, `question`.
4. `rl/` — simulator (`simulator.py`), policies (`policies.py`), experiment (`experiment.py`).
5. `bundle/export.py` — rebuilds every scenario's answer, distractors (trap, lean, deciding slots, pivot, risk-score gap) and evidence spans from the engine into `web/data/bundle.json`; refuses to write if it does not match `schemas/bundle.schema.json`. Re-run after any table or scenario change.
   `web/js/` — static ES modules, no build, no dependencies, no LLM: `bandit.js` (Thompson), `progress.js` (pure updates, delayed reward, spaced-review gaps), `selector.js` (pending reward → due review → unseen → weakest; `queuePreview` lists the upcoming traps in that order), `hints.js` (ladders per action; `scrub` keeps correct codes out of hints), `note.js` (sentences/evidence), `api.js` (live bandit client), `common.js` (prefs, theme, dates, shared by both pages), `home.js` (home page: hero, animated walkthrough, and a passive directional flow diagram of how the next case is chosen, with the pick-order strip), `app.js` (assessment page controller). Pages: `index.html` → `practice.html?topic=<id>` (`#progress` opens the progress drawer). Animations respect prefers-reduced-motion; layouts are checked from 320px to 1920px. Coach mode done; exam mode (sections, flag for review, countdown timer) TODO.
6. `live/` — live bandit service (optional; `web/config.json` `api`: null = offline, "/api" = same origin, or a URL). Browser still chooses actions with Thompson sampling over its own counts + shared counts from `GET /v1/policy` (capped at `SHARED_CAP`=20 pseudo-trials). Settled rewards go to `POST /v1/events` as exactly `{confusion, bucket, action, reward}` (`schemas/event.schema.json`; `policy.py` rejects any other field). `app.py` stdlib WSGI `make_app` (injected `Store`, confusions, CORS allowlist, rate limiter, clock; paths accept an `/api` prefix); `stores/` backends build a `Store` (record, arm_rows, total_events): `stores/sqlite.py` now (arm totals + append-only event log, no identifiers, day granularity), Redis for Vercel TODO. `server.py` = standalone API.
7. `devserver/` — `coding-tutor-serve [--with-api]`: static files (`static.py`) plus, optionally, the live API under `/api` on one origin, answering `/config.json` as `{"api": "/api"}` (the file on disk is untouched).

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

## Accessibility (web, WCAG 2.2 AA)
- Text colours must pass `tests/web/contrast.test.mjs` (4.5:1) in both themes; adjust tokens in `web/css/app.css`, never one-off colours.
- Everything usable by keyboard: answer choices are a radio group (roving tabindex, arrow keys); note sentences become focusable buttons while marking/finding; dialogs and the drawer trap focus and return it on close.
- Single-key shortcuts can be switched off (Keyboard shortcuts dialog, `prefs.shortcuts`).
- Anything that auto-advances has a visible Pause button and stops under prefers-reduced-motion.
- Jargon gets a glossary tooltip via `term()` in `common.js`; hidden tooltips use `display: none` so they never widen the page.
- Check 320–1920px for horizontal overflow before shipping UI changes.

## Testing
- All tests live in one root, `tests/`, mirroring the source layout for both languages:
  `src/coding_tutor/engine/x.py` -> `tests/engine/test_x.py`; `web/js/x.js` -> `tests/web/x.test.mjs`.
  Never put tests inside `web/` (it is the deploy root).
- Shared fixtures go in `tests/conftest.py`; use `parametrize` instead of copied test bodies.
- `pyproject.toml` puts `src/` on the pytest import path (`import coding_tutor...`); don't add sys.path hacks.
- Every new function: normal case, edge cases, invalid input.
- Every decision-table rule needs a case in `EXPECTED` (tests/engine/test_rules.py);
  the suite fails if a rule has none.
- Fixed random seeds in all RL and simulation tests; mark long runs `@pytest.mark.slow`.
- Commands (PowerShell):
  - `.\.venv\Scripts\python.exe -m ruff check .` and `.\.venv\Scripts\python.exe -m ruff format --check .`
  - `.\.venv\Scripts\python.exe -m pytest` (quick run: add `-m "not slow"`); this also runs the web JS tests via Node when installed (`tests/web/*.test.mjs`, Node's built-in runner, no npm packages). Direct JS run: `node --test "tests/web/*.test.mjs"`
  - After changing tables or scenarios: `coding-tutor-export-ui` to refresh `web/data/bundle.json`.
- Before calling a task done: ruff clean and all tests passing; report both results.
- Refactors must not change behavior: existing tests stay green without editing them,
  unless I approve a test change.

## Next tasks
1. Exam mode in the web UI (sections, flag for review, countdown timer); real-student testing of coach mode.
2. Decision tables for CRC: acceptable sources, status codes; more MEAT conditions.
3. Certified-coder review of tables and generated scenarios.
4. Deploy the live bandit API: pick a host (Vercel Python functions + Postgres, or AWS Lambda + DynamoDB), add `live/stores/redis.py` building the same `Store`, an `api/index.py` Vercel entry, set the CORS origin and `web/config.json`. Then offline evaluation in `rl/` from the event log.