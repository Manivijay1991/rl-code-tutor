"""Teaching-action policies. Context = (confusion, miss bucket 1/2/3+).

An agent is a record of functions sharing a `state` dict:
  act(ctx) -> action
  update(ctx, action, reward, next_ctx) -> None
  start_student(student) -> None        (only the oracle uses it)

thompson() is the one the product uses. q_learning() exists only for simulator experiments.
"""

from __future__ import annotations

import random
from typing import Callable, NamedTuple

from rl.env import ACTIONS, Env, Student, best_action

Ctx = tuple  # (confusion, bucket)


def _no_update(ctx: Ctx, action: str, reward: int, next_ctx: Ctx | None = None) -> None:
    pass


def _no_student(student: Student) -> None:
    pass


class Agent(NamedTuple):
    name: str
    act: Callable[[Ctx], str]
    update: Callable[..., None] = _no_update
    start_student: Callable[[Student], None] = _no_student
    state: dict | None = None


def random_agent(seed: int = 0) -> Agent:
    rng = random.Random(seed)
    return Agent("random", lambda ctx: rng.choice(ACTIONS))


def fixed(action: str) -> Agent:
    return Agent(f"always_{action}", lambda ctx: action)


# ---- Thompson sampling (Beta-Bernoulli per (context, action)) ----
def _beta(ab: dict, ctx: Ctx, a: str, prior: tuple[float, float]) -> list[float]:
    return ab.setdefault((ctx, a), list(prior))


def posterior_means(state: dict, ctx: Ctx) -> dict[str, float]:
    means = {}
    for a in ACTIONS:
        alpha, beta = _beta(state["ab"], ctx, a, state["prior"])
        means[a] = alpha / (alpha + beta)
    return means


def thompson(seed: int = 0, prior: tuple[float, float] = (1.0, 1.0)) -> Agent:
    rng = random.Random(seed)
    state = {"ab": {}, "prior": prior}

    def act(ctx: Ctx) -> str:
        return max(ACTIONS, key=lambda a: rng.betavariate(*_beta(state["ab"], ctx, a, prior)))

    def update(ctx: Ctx, action: str, reward: int, next_ctx: Ctx | None = None) -> None:
        _beta(state["ab"], ctx, action, prior)[0 if reward else 1] += 1

    return Agent("thompson", act, update, state=state)


# ---- epsilon-greedy ----
def eps_greedy(eps: float = 0.1, seed: int = 0) -> Agent:
    rng = random.Random(seed)
    state = {"n": {}, "s": {}}

    def act(ctx: Ctx) -> str:
        if rng.random() < eps:
            return rng.choice(ACTIONS)
        return max(ACTIONS, key=lambda a: (state["s"].get((ctx, a), 0) + 1) / (state["n"].get((ctx, a), 0) + 2))

    def update(ctx: Ctx, action: str, reward: int, next_ctx: Ctx | None = None) -> None:
        k = (ctx, action)
        state["n"][k] = state["n"].get(k, 0) + 1
        state["s"][k] = state["s"].get(k, 0) + reward

    return Agent("eps_greedy", act, update, state=state)


# ---- Q-learning (simulator experiments only, per CLAUDE.md) ----
def q_learning(alpha: float = 0.1, gamma: float = 0.5, eps: float = 0.1, seed: int = 0) -> Agent:
    """Tabular Q-learning; next state = same confusion one bucket higher when the retry is missed."""
    rng = random.Random(seed)
    q: dict[tuple, float] = {}

    def act(ctx: Ctx) -> str:
        if rng.random() < eps:
            return rng.choice(ACTIONS)
        return max(ACTIONS, key=lambda a: q.get((ctx, a), 0.5))

    def update(ctx: Ctx, action: str, reward: int, next_ctx: Ctx | None = None) -> None:
        future = max(q.get((next_ctx, a), 0.5) for a in ACTIONS) if next_ctx else 0.0
        old = q.get((ctx, action), 0.5)
        q[(ctx, action)] = old + alpha * (reward + gamma * future - old)

    return Agent("q_learning", act, update, state={"q": q})


# ---- oracle (upper bound for regret; not a real policy) ----
def oracle(env: Env) -> Agent:
    """Knows the simulator's hidden best action for the current student."""
    current: dict[str, Student] = {}

    def act(ctx: Ctx) -> str:
        return best_action(env, current["student"], ctx[0])

    def start_student(student: Student) -> None:
        current["student"] = student

    return Agent("oracle", act, start_student=start_student, state=current)
