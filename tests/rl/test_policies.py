import pytest

from coding_tutor.rl import policies
from coding_tutor.rl import simulator as sim
from coding_tutor.rl.policies import posterior_means, thompson
from coding_tutor.rl.simulator import ACTIONS

CTX = ("t:c", 1)


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


def test_thompson_prior_means():
    assert set(posterior_means(thompson(prior=(1.0, 3.0)).state, CTX).values()) == {0.25}


def test_thompson_contexts_are_independent():
    a = thompson(seed=0)
    for _ in range(10):
        a.update(CTX, "walkthrough", 1)
    assert posterior_means(a.state, ("t:c", 2))["walkthrough"] == 0.5


@pytest.mark.parametrize(
    "make",
    [policies.random_agent, policies.thompson, policies.eps_greedy, policies.q_learning],
    ids=lambda f: f.__name__,
)
def test_policies_are_deterministic_and_valid(make):
    a, b = make(seed=3), make(seed=3)
    picks_a = [a.act(CTX) for _ in range(30)]
    assert picks_a == [b.act(CTX) for _ in range(30)]
    assert set(picks_a) <= set(ACTIONS)


def test_fixed():
    a = policies.fixed("walkthrough")
    assert a.name == "always_walkthrough" and a.act(CTX) == "walkthrough"
    a.update(CTX, "walkthrough", 1, None)  # no-op


def test_fixed_rejects_unknown_action():
    with pytest.raises(ValueError, match="unknown action"):
        policies.fixed("nap")


def test_eps_greedy_exploits_when_eps_zero():
    a = policies.eps_greedy(eps=0.0)
    for _ in range(5):
        a.update(CTX, "find_meat", 1)
    assert {a.act(CTX) for _ in range(20)} == {"find_meat"}


def test_q_learning_update():
    a = policies.q_learning(alpha=0.5, gamma=0.5, eps=0.0)
    a.update(CTX, "walkthrough", 1, None)
    assert a.state["q"][(CTX, "walkthrough")] == pytest.approx(0.5 + 0.5 * (1 - 0.5))
    a.update(CTX, "find_meat", 0, ("t:c", 2))  # future = 0.5 (default) for the unseen next context
    assert a.state["q"][(CTX, "find_meat")] == pytest.approx(0.5 + 0.5 * (0 + 0.5 * 0.5 - 0.5))
    assert a.act(CTX) == "walkthrough"


def test_oracle_picks_hidden_best_action():
    env = sim.make_env(["t:c"], seed=0)
    s = sim.new_student(env)
    a = policies.oracle(env)
    a.start_student(s)
    assert a.act(CTX) == sim.best_action(env, s, "t:c")


def test_oracle_needs_a_student():
    with pytest.raises(KeyError):
        policies.oracle(sim.make_env(["t:c"], 0)).act(CTX)
