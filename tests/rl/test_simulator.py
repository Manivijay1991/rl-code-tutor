import pytest

from coding_tutor.rl import simulator as sim

CONFUSIONS = ["t:a", "t:b", "t:c"]


@pytest.fixture
def env():
    return sim.make_env(CONFUSIONS, seed=0)


def student(skill, profile="reader", misses=None):
    return sim.Student(dict(skill), profile, dict(misses or {}), {}, {})


@pytest.mark.parametrize(("misses", "b"), [(0, 1), (1, 1), (2, 2), (3, 3), (7, 3)])
def test_miss_level(misses, b):
    assert sim.miss_level(misses) == b


def test_make_env_is_deterministic():
    assert sim.make_env(CONFUSIONS, 5).kind == sim.make_env(CONFUSIONS, 5).kind
    assert set(sim.make_env(CONFUSIONS, 5).kind.values()) <= set(sim.KINDS)


def test_make_env_empty():
    assert sim.make_env([], 0).kind == {}


def test_new_student(env):
    s = sim.new_student(env)
    assert set(s.skill) == set(CONFUSIONS)
    assert all(0.15 <= v <= 0.6 for v in s.skill.values())
    assert s.profile in sim.PROFILES and s.misses == s.seen == s.right == {}


def test_mastery():
    assert sim.mastery(student({"a": 0.2, "b": 0.4})) == pytest.approx(0.3)


def test_mastery_needs_skills():
    with pytest.raises(ZeroDivisionError):
        sim.mastery(student({}))


def test_gain_adds_profile_and_stuck_bonus(env):
    c = CONFUSIONS[0]
    base = sim.BASE_GAIN[env.kind[c]]["walkthrough"]
    assert sim.gain(env, student({c: 0.5}, "example_learner"), c, "walkthrough") == pytest.approx(base + 0.06)
    stuck = student({c: 0.5}, "example_learner", {c: 3})
    assert sim.gain(env, stuck, c, "walkthrough") == pytest.approx(min(base + 0.06 + 0.15, sim.MAX_GAIN))


def test_gain_unknown_action(env):
    with pytest.raises(KeyError):
        sim.gain(env, student({CONFUSIONS[0]: 0.5}), CONFUSIONS[0], "nap")


def test_best_action_maximizes_gain(env):
    s, c = student({CONFUSIONS[0]: 0.5}), CONFUSIONS[0]
    best = sim.best_action(env, s, c)
    assert all(sim.gain(env, s, c, best) >= sim.gain(env, s, c, a) for a in sim.ACTIONS)


def test_pick_confusion_unseen_first_then_weakest(env):
    s = student(dict.fromkeys(CONFUSIONS, 0.5))
    s.seen.update({"t:a": 2, "t:b": 2})
    s.right.update({"t:a": 1, "t:b": 0})
    assert sim.pick_confusion(env, s) == "t:c"
    s.seen["t:c"], s.right["t:c"] = 1, 1
    assert sim.pick_confusion(env, s) == "t:b"


@pytest.mark.parametrize(("skill", "ok"), [(1.0, True), (0.0, False)])
def test_answer_updates_counters(env, skill, ok):
    s = student({"t:a": skill})
    assert sim.answer(env, s, "t:a") is ok
    assert s.seen["t:a"] == 1 and s.right["t:a"] == int(ok)
    assert s.misses.get("t:a", 0) == int(not ok)
    assert s.skill["t:a"] == pytest.approx(skill + sim.PRACTICE_GAIN * (1 - skill))


def test_teach_closes_gap(env):
    c = CONFUSIONS[0]
    s = student({c: 0.4})
    g = sim.gain(env, s, c, "rule_refresh")
    sim.teach(env, s, c, "rule_refresh")
    assert s.skill[c] == pytest.approx(0.4 + g * 0.6)


def test_teach_at_full_skill_stays_full(env):
    s = student({CONFUSIONS[0]: 1.0})
    sim.teach(env, s, CONFUSIONS[0], "walkthrough")
    assert s.skill[CONFUSIONS[0]] == 1.0
