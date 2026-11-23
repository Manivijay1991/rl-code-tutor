"""Simulated students for testing the teaching loop (not evidence that it helps real students).

Hidden from the agent:
  * each confusion has a hidden "kind" (rule / documentation / specificity), drawn per seed,
    which decides which teaching actions work best for it;
  * each student has a per-confusion skill and a learner profile that shifts action effects;
  * after 3+ misses, scaffolded actions (walkthrough, easier_case) work better.

Loop per question (mirrors CLAUDE.md):
  pick confusion (simple rule: weakest observed first) -> student answers ->
  if wrong: agent picks action for context (confusion, miss bucket) -> student learns ->
  NEW question with the same confusion -> reward = 1 if correct.

Env and Student are plain records; every step is a function. `answer` and `teach` update the
student's dicts in place (the simulator's state), and the env's rng advances.
"""

from __future__ import annotations

import random
from typing import NamedTuple

ACTIONS = ("rule_refresh", "contrast_pair", "find_meat", "guiding_question", "walkthrough", "easier_case")
KINDS = ("rule", "documentation", "specificity")
PROFILES = ("reader", "example_learner", "detail_seeker")

# Base learning gain per (kind, action). Values in [0, 1]: fraction of the remaining gap closed.
BASE_GAIN = {
    "rule":          {"rule_refresh": .30, "contrast_pair": .22, "find_meat": .05, "guiding_question": .18, "walkthrough": .20, "easier_case": .10},
    "documentation": {"rule_refresh": .08, "contrast_pair": .12, "find_meat": .32, "guiding_question": .22, "walkthrough": .18, "easier_case": .10},
    "specificity":   {"rule_refresh": .12, "contrast_pair": .32, "find_meat": .10, "guiding_question": .15, "walkthrough": .18, "easier_case": .12},
}
PROFILE_BONUS = {
    "reader":          {"rule_refresh": .06},
    "example_learner": {"walkthrough": .06, "easier_case": .04},
    "detail_seeker":   {"find_meat": .05, "guiding_question": .05},
}
STUCK_BONUS = {"walkthrough": .15, "easier_case": .15}  # when missed 3+ times
PRACTICE_GAIN = 0.02  # small gain from just seeing a question


class Env(NamedTuple):
    confusions: list[str]
    rng: random.Random
    kind: dict[str, str]  # hidden: confusion -> kind


class Student(NamedTuple):
    skill: dict[str, float]
    profile: str
    misses: dict[str, int]
    seen: dict[str, int]
    right: dict[str, int]


def bucket(misses: int) -> int:
    return 1 if misses <= 1 else 2 if misses == 2 else 3


def make_env(confusions: list[str], seed: int = 0) -> Env:
    rng = random.Random(seed)
    return Env(list(confusions), rng, {c: rng.choice(KINDS) for c in confusions})


def new_student(env: Env) -> Student:
    skill = {c: env.rng.uniform(0.15, 0.6) for c in env.confusions}
    return Student(skill, env.rng.choice(PROFILES), {}, {}, {})


def mastery(s: Student) -> float:
    return sum(s.skill.values()) / len(s.skill)


# ---- hidden dynamics ----
def gain(env: Env, s: Student, confusion: str, action: str) -> float:
    g = BASE_GAIN[env.kind[confusion]][action] + PROFILE_BONUS[s.profile].get(action, 0.0)
    if bucket(s.misses.get(confusion, 0)) == 3:
        g += STUCK_BONUS.get(action, 0.0)
    return min(g, 0.9)


def best_action(env: Env, s: Student, confusion: str) -> str:
    return max(ACTIONS, key=lambda a: gain(env, s, confusion, a))


# ---- episode steps ----
def pick_confusion(env: Env, s: Student) -> str:
    """Simple selector: weakest observed accuracy first, unseen first; random tie-break."""
    def score(c: str) -> tuple[float, float]:
        n = s.seen.get(c, 0)
        return (-1.0 if n == 0 else s.right.get(c, 0) / n, env.rng.random())
    return min(env.confusions, key=score)


def answer(env: Env, s: Student, c: str) -> bool:
    ok = env.rng.random() < s.skill[c]
    s.seen[c] = s.seen.get(c, 0) + 1
    s.right[c] = s.right.get(c, 0) + ok
    s.skill[c] += PRACTICE_GAIN * (1 - s.skill[c])
    if not ok:
        s.misses[c] = s.misses.get(c, 0) + 1
    return ok


def teach(env: Env, s: Student, c: str, action: str) -> None:
    s.skill[c] += gain(env, s, c, action) * (1 - s.skill[c])
