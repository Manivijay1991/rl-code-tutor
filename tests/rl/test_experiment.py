import pytest

from coding_tutor.rl import experiment
from coding_tutor.rl.experiment import POLICIES, run

SMALL = {"students": 40, "questions": 20, "windows": 4}


def test_confusion_ids(tables):
    ids = experiment.confusion_ids()
    assert len(ids) == sum(len(t["confusions"]) for t in tables.values())
    assert "diabetes_complications:missed_with_link" in ids


@pytest.mark.parametrize(
    ("per_student", "per_window", "curve"),
    [
        ([[1, 0], [1], [0], [1, 1]], 2, [2 / 3, 2 / 3]),
        ([[1], [0], [1]], 2, [0.5]),  # partial last window dropped
        ([[], []], 1, [0.0, 0.0]),  # students with no misses
        ([], 3, []),
    ],
    ids=["full", "partial", "no_rewards", "empty"],
)
def test_learning_curve(per_student, per_window, curve):
    assert experiment.learning_curve(per_student, per_window) == pytest.approx(curve)


def test_spark_clamps():
    assert experiment.spark([0.0, 0.3, 0.9, 5.0]) == "▁▁██"
    assert experiment.spark([]) == ""


def test_run_is_deterministic_and_complete():
    a, b = run(POLICIES["thompson"], 0, **SMALL), run(POLICIES["thompson"], 0, **SMALL)
    assert a == b
    assert set(a) == {"reward", "late_reward", "mastery_gain", "best_action_rate", "curve"}
    assert len(a["curve"]) == 4
    assert 0 <= a["reward"] <= 1 and 0 <= a["best_action_rate"] <= 1


def test_run_oracle_always_best():
    assert run(POLICIES["oracle"], 0, **SMALL)["best_action_rate"] == 1.0


def test_run_student_counts_questions():
    env = experiment.sim.make_env(experiment.confusion_ids(), seed=0)
    sr = experiment.run_student(env, POLICIES["random"](env, 0), questions=10)
    assert sr.n_teach == len(sr.rewards) <= 5
    assert 0 <= sr.best_hits <= sr.n_teach


def test_summarize_seeds_and_format_row():
    res = [run(POLICIES["random"], s, **SMALL) for s in (0, 1)]
    m = experiment.summarize_seeds(res)
    assert m["reward"] == pytest.approx((res[0]["reward"] + res[1]["reward"]) / 2)
    assert experiment.format_row("random", m).startswith("random ")


def test_parse_args_defaults():
    args = experiment.parse_args([])
    assert (args.students, args.questions, args.seeds, args.windows) == (1500, 40, 3, 15)


def test_parse_args_rejects_text():
    with pytest.raises(SystemExit):
        experiment.parse_args(["--students", "many"])


@pytest.mark.slow
def test_thompson_beats_random_in_simulation():
    kw = {"students": 600, "questions": 40, "windows": 5}
    ts = sum(run(POLICIES["thompson"], s, **kw)["reward"] for s in range(2))
    rnd = sum(run(POLICIES["random"], s, **kw)["reward"] for s in range(2))
    assert ts > rnd
