"""Simulated students for testing the teaching loop (not evidence that it helps real students).

Hidden from the policy:
  * each confusion has a hidden "kind" (rule / documentation / specificity), drawn per seed,
    which decides which teaching actions work best for it;
  * each student has a per-confusion skill and a learner profile that shifts action effects;
  * after 3+ misses, scaffolded actions (walkthrough, easier_case) work better.

Loop per question (mirrors CLAUDE.md):
  pick confusion (simple rule: weakest observed first) -> student answers ->
  if wrong: policy picks action for context (confusion, miss level) -> student learns ->
  NEW question with the same confusion -> reward = 1 if correct.

Env and Student are plain records; every step is a function. `answer` and `teach` update the
student's dicts in place (the simulator's state, for speed), and the env's rng advances.
"""

from __future__ import annotations

import random
from typing import NamedTuple

ACTIONS = ("rule_refresh", "contrast_pair", "find_meat", "guiding_question", "walkthrough", "easier_case")
KINDS = ("rule", "documentation", "specificity")
PROFILES = ("reader", "example_learner", "detail_seeker")

# Base learning gain per (kind, action). Values in [0, 1]: fraction of the remaining gap closed.
BASE_GAIN = {
    "rule": {
        "rule_refresh": 0.30, "contrast_pair": 0.22, "find_meat": 0.05,
        "guiding_question": 0.18, "walkthrough": 0.20, "easier_case": 0.10,
    },
    "documentation": {
        "rule_refresh": 0.08, "contrast_pair": 0.12, "find_meat": 0.32,
        "guiding_question": 0.22, "walkthrough": 0.18, "easier_case": 0.10,
    },
    "specificity": {
        "rule_refresh": 0.12, "contrast_pair": 0.32, "find_meat": 0.10,
        "guiding_question": 0.15, "walkthrough": 0.18, "easier_case": 0.12,
    },
}  # fmt: skip
PROFILE_BONUS = {
    "reader": {"rule_refresh": 0.06},
    "example_learner": {"walkthrough": 0.06, "easier_case": 0.04},
    "detail_seeker": {"find_meat": 0.05, "guiding_question": 0.05},
}
STUCK_BONUS = {"walkthrough": 0.15, "easier_case": 0.15}  # when missed 3+ times
PRACTICE_GAIN = 0.02  # small gain from just seeing a question
MAX_GAIN = 0.9


class Env(NamedTuple):
    """Simulator settings shared by every student of one run."""

    confusions: list[str]
    rng: random.Random
    kind: dict[str, str]  # hidden: confusion -> kind


class Student(NamedTuple):
    """One simulated student. The dicts are updated in place as the student practices."""

    skill: dict[str, float]
    profile: str
    misses: dict[str, int]
    seen: dict[str, int]
    right: dict[str, int]


def miss_level(misses: int) -> int:
    """Return the miss level used in the policy context: 1, 2 or 3 (3+)."""
    return 1 if misses <= 1 else 2 if misses == 2 else 3


def make_env(confusions: list[str], seed: int = 0) -> Env:
    """Create a simulator with a hidden kind per confusion, drawn from `seed`."""
    rng = random.Random(seed)
    return Env(list(confusions), rng, {c: rng.choice(KINDS) for c in confusions})


def new_student(env: Env) -> Student:
    """Draw a new student: skill 0.15-0.6 per confusion and a random learner profile."""
    skill = {c: env.rng.uniform(0.15, 0.6) for c in env.confusions}
    return Student(skill, env.rng.choice(PROFILES), {}, {}, {})


def mastery(s: Student) -> float:
    """Return the student's mean skill across confusions."""
    return sum(s.skill.values()) / len(s.skill)


# ---- hidden dynamics ----
def gain(env: Env, s: Student, confusion: str, action: str) -> float:
    """Return the fraction of the remaining skill gap that `action` closes (capped at MAX_GAIN)."""
    g = BASE_GAIN[env.kind[confusion]][action] + PROFILE_BONUS[s.profile].get(action, 0.0)
    if miss_level(s.misses.get(confusion, 0)) == 3:
        g += STUCK_BONUS.get(action, 0.0)
    return min(g, MAX_GAIN)


def best_action(env: Env, s: Student, confusion: str) -> str:
    """Return the hidden best action for this student and confusion (oracle only)."""
    return max(ACTIONS, key=lambda a: gain(env, s, confusion, a))


# ---- episode steps ----
def pick_confusion(env: Env, s: Student) -> str:
    """Pick the next confusion: unseen first, then weakest observed accuracy; random tie-break."""

    def score(c: str) -> tuple[float, float]:
        n = s.seen.get(c, 0)
        return (-1.0 if n == 0 else s.right.get(c, 0) / n, env.rng.random())

    return min(env.confusions, key=score)


def _record(s: Student, c: str, ok: bool) -> None:
    """Update the student's seen/right/miss counters (in place)."""
    s.seen[c] = s.seen.get(c, 0) + 1
    s.right[c] = s.right.get(c, 0) + ok
    if not ok:
        s.misses[c] = s.misses.get(c, 0) + 1


def _close_gap(s: Student, c: str, fraction: float) -> None:
    """Move the student's skill toward 1 by `fraction` of the remaining gap (in place)."""
    s.skill[c] += fraction * (1 - s.skill[c])


def answer(env: Env, s: Student, c: str) -> bool:
    """Simulate one answer: correct with probability = skill. Updates the student in place."""
    ok = env.rng.random() < s.skill[c]
    _record(s, c, ok)
    _close_gap(s, c, PRACTICE_GAIN)
    return ok


def teach(env: Env, s: Student, c: str, action: str) -> None:
    """Apply a teaching action to the student (in place)."""
    _close_gap(s, c, gain(env, s, c, action))
