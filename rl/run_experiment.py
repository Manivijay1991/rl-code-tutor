"""Compare teaching policies in the simulator.

A single agent is shared across a stream of simulated students (as the live bandit would be
shared across real students). Confusion ids come from the real decision tables.

    python -m rl.run_experiment                       # defaults
    python -m rl.run_experiment --students 2000 --seeds 5

Shows the loop works in simulation. It cannot show the agent helps real students.
"""

from __future__ import annotations

import argparse
import statistics
import time

from engine.rules_engine import load_tables
from rl import agents
from rl import env as sim
from rl.env import ACTIONS, bucket


def confusion_ids() -> list[str]:
    return [f"{t['id']}:{c}" for t in load_tables().values() for c in t["confusions"]]


def run(make_agent, seed: int, students: int, questions: int, windows: int) -> dict:
    env = sim.make_env(confusion_ids(), seed=seed)
    agent = make_agent(env, seed)
    per_window = max(1, students // windows)
    rewards, curve, mastery_gain, best_hits, n_teach = [], [], [], 0, 0
    w_r = []
    for i in range(students):
        s = sim.new_student(env)
        agent.start_student(s)
        start = sim.mastery(s)
        q = 0
        while q < questions:
            c = sim.pick_confusion(env, s)
            q += 1
            if sim.answer(env, s, c):
                continue
            ctx = (c, bucket(s.misses[c]))
            a = agent.act(ctx)
            best_hits += a == sim.best_action(env, s, c)
            n_teach += 1
            sim.teach(env, s, c, a)
            # reward: NEW question with the same confusion (never the immediate retry of the same item)
            q += 1
            r = int(sim.answer(env, s, c))
            next_ctx = None if r else (c, bucket(s.misses[c]))
            agent.update(ctx, a, r, next_ctx)
            rewards.append(r)
            w_r.append(r)
        mastery_gain.append(sim.mastery(s) - start)
        if (i + 1) % per_window == 0:
            curve.append(sum(w_r) / max(1, len(w_r)))
            w_r = []
    return {
        "reward": sum(rewards) / max(1, len(rewards)),
        "late_reward": statistics.mean(curve[-max(1, len(curve) // 4):]) if curve else 0.0,
        "mastery_gain": statistics.mean(mastery_gain),
        "best_action_rate": best_hits / max(1, n_teach),
        "curve": curve,
    }


POLICIES = {
    "oracle": lambda env, seed: agents.oracle(env),
    "thompson": lambda env, seed: agents.thompson(seed=seed),
    "eps_greedy": lambda env, seed: agents.eps_greedy(seed=seed),
    "q_learning": lambda env, seed: agents.q_learning(seed=seed),
    "random": lambda env, seed: agents.random_agent(seed=seed),
    **{f"always_{a}": (lambda a: lambda env, seed: agents.fixed(a))(a) for a in ("rule_refresh", "walkthrough")},
}


def spark(values: list[float]) -> str:
    bars = "▁▂▃▄▅▆▇█"
    lo, hi = 0.3, 0.9
    return "".join(bars[min(len(bars) - 1, max(0, int((v - lo) / (hi - lo) * (len(bars) - 1))))] for v in values)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=1500)
    ap.add_argument("--questions", type=int, default=40)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--windows", type=int, default=15)
    args = ap.parse_args()

    n_conf = len(confusion_ids())
    print(f"{n_conf} confusions x 3 miss buckets = {n_conf * 3} contexts, {len(ACTIONS)} actions")
    print(f"{args.students} students x {args.questions} questions, {args.seeds} seeds\n")
    print(f"{'policy':22} {'reward':>7} {'late':>7} {'mastery+':>9} {'best-act':>9}  learning curve (reward per window)")
    t0 = time.time()
    for name, make in POLICIES.items():
        res = [run(make, seed, args.students, args.questions, args.windows) for seed in range(args.seeds)]
        curve = [statistics.mean(c) for c in zip(*(r["curve"] for r in res))]

        def mean(k: str) -> float:
            return statistics.mean(r[k] for r in res)

        print(f"{name:22} {mean('reward'):7.3f} {mean('late_reward'):7.3f} {mean('mastery_gain'):9.3f} "
              f"{mean('best_action_rate'):9.1%}  {spark(curve)}")
    print(f"\n({time.time() - t0:.1f}s)  reward = correct on the next NEW question with the same confusion; "
          "late = last quarter of students; oracle knows the hidden best action.")


if __name__ == "__main__":
    main()
