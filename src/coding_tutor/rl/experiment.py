"""Compare teaching policies in the simulator.

A single policy is shared across a stream of simulated students (as the live bandit would be
shared across real students). Confusion ids come from the real decision tables.

    python -m coding_tutor.rl.experiment                       # defaults
    python -m coding_tutor.rl.experiment --students 2000 --seeds 5

Shows the loop works in simulation. It cannot show the policy helps real students.
"""

from __future__ import annotations

import argparse
import statistics
import time
from collections.abc import Callable
from typing import NamedTuple

from coding_tutor.engine.rules import load_tables
from coding_tutor.rl import policies
from coding_tutor.rl import simulator as sim
from coding_tutor.rl.policies import Agent
from coding_tutor.rl.simulator import ACTIONS, Env, Student, miss_level

MakeAgent = Callable[[Env, int], Agent]


class StudentRun(NamedTuple):
    """What happened while one student practiced."""

    rewards: list[int]
    mastery_gain: float
    best_hits: int
    n_teach: int


def confusion_ids() -> list[str]:
    """Return every confusion as `<table>:<confusion>` from the decision tables."""
    return [f"{t['id']}:{c}" for t in load_tables().values() for c in t["confusions"]]


def teach_after_miss(env: Env, agent: Agent, s: Student, c: str) -> tuple[int, bool]:
    """Teach after a miss, then ask a NEW question with the same confusion and update the policy.

    Returns:
        (reward, whether the policy picked the hidden best action).
    """
    ctx = (c, miss_level(s.misses[c]))
    a = agent.act(ctx)
    best = a == sim.best_action(env, s, c)
    sim.teach(env, s, c, a)
    r = int(sim.answer(env, s, c))
    agent.update(ctx, a, r, None if r else (c, miss_level(s.misses[c])))
    return r, best


def run_student(env: Env, agent: Agent, questions: int) -> StudentRun:
    """Run one new student through `questions` questions (the reward question counts as one)."""
    s = sim.new_student(env)
    agent.start_student(s)
    start = sim.mastery(s)
    rewards, best_hits, q = [], 0, 0
    while q < questions:
        c = sim.pick_confusion(env, s)
        q += 1
        if sim.answer(env, s, c):
            continue
        r, best = teach_after_miss(env, agent, s, c)
        q += 1
        rewards.append(r)
        best_hits += best
    return StudentRun(rewards, sim.mastery(s) - start, best_hits, len(rewards))


def learning_curve(per_student: list[list[int]], per_window: int) -> list[float]:
    """Return the mean reward of each full window of `per_window` students (a partial last window is dropped)."""
    curve = []
    for start in range(0, len(per_student) - per_window + 1, per_window):
        window = [r for rewards in per_student[start : start + per_window] for r in rewards]
        curve.append(sum(window) / max(1, len(window)))
    return curve


def run(make_agent: MakeAgent, seed: int, students: int, questions: int, windows: int) -> dict:
    """Run one policy over a stream of students.

    Returns:
        Dict with `reward`, `late_reward` (last quarter of the curve), `mastery_gain`,
        `best_action_rate` and `curve`.
    """
    env = sim.make_env(confusion_ids(), seed=seed)
    agent = make_agent(env, seed)
    runs = [run_student(env, agent, questions) for _ in range(students)]
    rewards = [r for sr in runs for r in sr.rewards]
    curve = learning_curve([sr.rewards for sr in runs], max(1, students // windows))
    n_teach = sum(sr.n_teach for sr in runs)
    return {
        "reward": sum(rewards) / max(1, len(rewards)),
        "late_reward": statistics.mean(curve[-max(1, len(curve) // 4) :]) if curve else 0.0,
        "mastery_gain": statistics.mean(sr.mastery_gain for sr in runs),
        "best_action_rate": sum(sr.best_hits for sr in runs) / max(1, n_teach),
        "curve": curve,
    }


def _fixed_factory(action: str) -> MakeAgent:
    """Return a factory for a fixed-action policy."""
    return lambda _env, _seed: policies.fixed(action)


POLICIES: dict[str, MakeAgent] = {
    "oracle": lambda env, _seed: policies.oracle(env),
    "thompson": lambda _env, seed: policies.thompson(seed=seed),
    "eps_greedy": lambda _env, seed: policies.eps_greedy(seed=seed),
    "q_learning": lambda _env, seed: policies.q_learning(seed=seed),
    "random": lambda _env, seed: policies.random_agent(seed=seed),
    **{f"always_{a}": _fixed_factory(a) for a in ("rule_refresh", "walkthrough")},
}


def spark(values: list[float], lo: float = 0.3, hi: float = 0.9) -> str:
    """Return a one-line bar chart of values between `lo` and `hi` (clamped)."""
    bars = "▁▂▃▄▅▆▇█"
    return "".join(bars[min(len(bars) - 1, max(0, int((v - lo) / (hi - lo) * (len(bars) - 1))))] for v in values)


def summarize_seeds(results: list[dict]) -> dict:
    """Average each metric (and the curve, pointwise) across seeds."""
    keys = ("reward", "late_reward", "mastery_gain", "best_action_rate")
    out = {k: statistics.mean(r[k] for r in results) for k in keys}
    out["curve"] = [statistics.mean(c) for c in zip(*(r["curve"] for r in results), strict=True)]
    return out


def format_row(name: str, m: dict) -> str:
    """Return one results-table row."""
    return (
        f"{name:22} {m['reward']:7.3f} {m['late_reward']:7.3f} {m['mastery_gain']:9.3f} "
        f"{m['best_action_rate']:9.1%}  {spark(m['curve'])}"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    ap = argparse.ArgumentParser(description="Compare teaching policies in the simulator.")
    ap.add_argument("--students", type=int, default=1500)
    ap.add_argument("--questions", type=int, default=40)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--windows", type=int, default=15)
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run every policy and print a comparison table."""
    args = parse_args(argv)
    n_conf = len(confusion_ids())
    print(f"{n_conf} confusions x 3 miss levels = {n_conf * 3} contexts, {len(ACTIONS)} actions")
    print(f"{args.students} students x {args.questions} questions, {args.seeds} seeds\n")
    print(
        f"{'policy':22} {'reward':>7} {'late':>7} {'mastery+':>9} {'best-act':>9}  learning curve (reward per window)"
    )
    t0 = time.time()
    for name, make in POLICIES.items():
        results = [run(make, seed, args.students, args.questions, args.windows) for seed in range(args.seeds)]
        print(format_row(name, summarize_seeds(results)))
    print(
        f"\n({time.time() - t0:.1f}s)  reward = correct on the next NEW question with the same confusion; "
        "late = last quarter of students; oracle knows the hidden best action."
    )


if __name__ == "__main__":
    main()
