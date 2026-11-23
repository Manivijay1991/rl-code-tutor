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
1. `decision_tables/*.json` — rules as slots (deciding details) → correct codes, with confusions tagged per wrong answer.
2. `engine/rules_engine.py` — resolves answers and checks every slot combination is covered.
3. Scenario generator (TODO) — picks slots, engine computes answer, local LLM via Ollama writes the note, a check confirms deciding details are present, output saved as JSON.
4. `rl/` — simulator (`env.py`), policies (`agents.py`), experiment (`run_experiment.py`).
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
- Python 3.12, standard library first; Windows host (PowerShell), Ollama available locally on GPU.
- Tests use **pytest** (dev-only dependency, in `.venv`): `.\.venv\Scripts\python.exe -m pytest`.
- Keep everything runnable offline; no API keys in a public page.
- Verify codes against the current fiscal-year CMS files before trusting them.

## Next tasks
1. Scenario generator using Ollama's local API.
2. Decision tables for CRC: MEAT/documentation support, acceptable sources, status codes, HCC mapping (V28).
3. Static UI from the mockup (coach mode first).
4. Later: AWS backend (API Gateway + Lambda + DynamoDB) for logging and the live bandit.