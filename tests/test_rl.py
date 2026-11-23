from rl.agents import posterior_means, thompson
from rl.env import ACTIONS, bucket
from rl.run_experiment import POLICIES, run


def test_bucket():
    assert [bucket(n) for n in (1, 2, 3, 7)] == [1, 2, 3, 3]


def test_thompson_update_shifts_posterior():
    a = thompson(seed=0)
    ctx = ("t:c", 1)
    for _ in range(20):
        a.update(ctx, "contrast_pair", 1)
        a.update(ctx, "rule_refresh", 0)
    means = posterior_means(a.state, ctx)
    assert means["contrast_pair"] > 0.9 > 0.1 > means["rule_refresh"]
    picks = [a.act(ctx) for _ in range(200)]
    assert picks.count("contrast_pair") > 150
    assert set(picks) <= set(ACTIONS)


def test_thompson_beats_random_in_simulation():
    kw = dict(students=600, questions=40, windows=5)
    ts = sum(run(POLICIES["thompson"], s, **kw)["reward"] for s in range(2))
    rnd = sum(run(POLICIES["random"], s, **kw)["reward"] for s in range(2))
    assert ts > rnd
