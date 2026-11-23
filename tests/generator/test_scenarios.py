import argparse
import json
import random

import pytest

from coding_tutor.engine.rules import combos, make_table
from coding_tutor.generator import scenarios
from coding_tutor.generator.scenarios import (
    build_prompt,
    check_note,
    clean,
    generate_one,
    has_phrase,
    make_record,
    pick_slots,
    requirements,
    save,
    scenario_id,
    write_note,
)

FILLER = " The patient is seen for routine follow-up today and reports feeling generally well." * 5


@pytest.fixture
def dm(tables):
    return tables["diabetes_complications"]


@pytest.fixture
def meat(tables):
    return tables["meat_support"]


def dm_slots(**kw):
    base = {"dm_type": "type2", "complication": "ckd_stage4", "provider_says_unrelated": "no", "meds": "insulin"}
    return {**base, **kw}


def fake_llm(notes):
    it = iter(notes)
    return lambda system, user, seed: next(it)


# ---- phrases and checks ----
@pytest.mark.parametrize(
    ("text", "phrase", "found"),
    [
        ("CKD stage 3 noted", "stage 3", True),
        ("CKD stage 3a noted", "stage 3", False),
        ("Hypertension, stable", "hypertension", True),
        ("", "x", False),
    ],
)
def test_has_phrase(text, phrase, found):
    assert has_phrase(text, phrase) is found


def test_requirements_dm_ckd(dm):
    req = requirements(dm, dm_slots())
    assert ["CKD stage 4", "chronic kidney disease stage 4"] in req["require"]
    assert ["insulin"] in req["require"]
    for p in ("not due to diabetes", "metformin", "polyneuropathy", "hypertension"):
        assert p in req["forbid"]
    assert "insulin" not in req["forbid"]


def test_requirements_non_exclusive_slot(meat):
    req = requirements(meat, {"condition": "copd", "documentation": "problem_list_only"})
    assert "medication list" not in req["forbid"]  # documentation slot is not exclusive


def test_requirements_missing_slot(dm):
    with pytest.raises(KeyError):
        requirements(dm, {"dm_type": "type2"})


def test_insulin_and_oral_needs_both(dm):
    req = requirements(dm, dm_slots(meds="insulin_and_oral"))
    note = "Type 2 diabetes with CKD stage 4. Takes insulin daily." + FILLER
    assert any("metformin" in p for p in check_note(note, req))
    assert check_note(note.replace("insulin daily", "insulin and metformin daily"), req) == []


def test_med_list_only_skips_condition_name(meat):
    req = requirements(meat, {"condition": "copd", "documentation": "med_list_only"})
    assert ["COPD", "chronic obstructive pulmonary disease"] not in req["require"]
    assert "COPD" in req["forbid"]
    assert any("tiotropium" in g for g in req["require"])


def test_check_note_rejects_codes_and_forbidden(dm):
    req = requirements(dm, dm_slots())
    good = "Type 2 diabetes with CKD stage 4, on insulin. Vitamin B12 normal." + FILLER
    assert check_note(good, req) == []
    assert any("code-like" in p for p in check_note(good + " Code E11.22.", req))
    assert any("code-like" in p for p in check_note(good + " E1122", req))
    assert any("not due to diabetes" in p for p in check_note(good + " CKD is not due to diabetes.", req))
    assert any("HCC" in p for p in check_note(good + " HCC captured.", req))
    assert any("length" in p for p in check_note("Type 2 diabetes, CKD stage 4, insulin.", req))


def test_every_combo_has_satisfiable_requirements(table):
    for s in combos(table):
        req = requirements(table, s)
        forbid = {p.lower() for p in req["forbid"]}
        for g in req["require"]:
            assert any(p.lower() not in forbid for p in g), (s, g)
        assert build_prompt(req)


# ---- prompt and cleanup ----
def test_build_prompt_lists_problems(dm):
    text = build_prompt(requirements(dm, dm_slots()), ["must not contain 'HTN'"])
    assert "rejected" in text and "must not contain 'HTN'" in text
    assert "rejected" not in build_prompt(requirements(dm, dm_slots()))


@pytest.mark.parametrize(
    ("raw", "out"),
    [("```text\nNote\n```", "Note"), ("**HPI** ok", "HPI ok"), ("  plain  ", "plain"), ("", "")],
)
def test_clean(raw, out):
    assert clean(raw) == out


# ---- one scenario ----
def test_write_note_retries_then_accepts(dm):
    bad = "Type 2 diabetes with CKD stage 4, on insulin. Hypertension noted." + FILLER
    good = "Type 2 diabetes with CKD stage 4, on insulin." + FILLER
    note, log = write_note(dm, dm_slots(), fake_llm([bad, good]), seed=0)
    assert note == good and len(log) == 2 and log[0]["problems"] and log[1]["seed"] == 1


def test_write_note_gives_up(dm):
    note, log = write_note(dm, dm_slots(), fake_llm(["too short"] * 3), seed=0, attempts=3)
    assert note is None and len(log) == 3


def test_write_note_zero_attempts(dm):
    assert write_note(dm, dm_slots(), fake_llm([]), seed=0, attempts=0) == (None, [])


def test_scenario_id_is_stable():
    a = scenario_id("t", {"b": "1", "a": "2"}, "n")
    assert a == scenario_id("t", {"a": "2", "b": "1"}, "n")
    assert a != scenario_id("t", {"a": "2", "b": "1"}, "other")
    assert a.startswith("t-") and len(a) == 12


def test_record_answer_comes_from_engine(dm, tmp_path):
    rec = make_record(dm, dm_slots(), "note text", "fake", [{"seed": 0, "problems": []}])
    assert rec["answer"] == ["E11.22", "N18.4", "Z79.4"]
    assert rec["status"] == "draft" and rec["question"] == dm["question"]
    assert rec["risk_score"] is None
    assert all(d["lean"] in {"over", "under", "neutral"} for d in rec["distractors"])
    path = save(rec, tmp_path)
    assert path == tmp_path / "diabetes_complications" / f"{rec['id']}.json"
    assert json.loads(path.read_text(encoding="utf-8"))["id"] == rec["id"]


def test_record_with_db_has_risk_scores(dm, db):
    rec = make_record(dm, dm_slots(), "note", "fake", [], db)
    assert rec["risk_score"]["total"] > 0
    assert all(d["risk_score_gap"]["direction"] in {"over", "under", "none"} for d in rec["distractors"])


def test_generate_one(dm, tmp_path):
    args = argparse.Namespace(attempts=1, model="fake", out=tmp_path)
    good = "Type 2 diabetes with CKD stage 4, on insulin." + FILLER
    path, log = generate_one(dm, dm_slots(), fake_llm([good]), 0, args, None)
    assert path.exists() and len(log) == 1
    assert generate_one(dm, dm_slots(), fake_llm(["bad"]), 0, args, None) == (
        None,
        [{"seed": 0, "problems": log_problems("bad", dm)}],
    )


def log_problems(note, dm):
    return check_note(note, requirements(dm, dm_slots()))


# ---- batches ----
def test_pick_slots_spreads_without_repeats(meat):
    picks = pick_slots(meat, 9, random.Random(0))
    assert len({json.dumps(p, sort_keys=True) for p in picks}) == 9


def test_pick_slots_more_than_combos_and_edges(tiny_data):
    t = make_table(tiny_data)
    assert len(pick_slots(t, 7, random.Random(0))) == 7
    assert pick_slots(t, 0, random.Random(0)) == []
    assert pick_slots(t, None, random.Random(0)) == list(combos(t))
    with pytest.raises(ValueError, match="n must be"):
        pick_slots(t, -1, random.Random(0))


def test_main_dry_run_prints_prompts(capsys):
    assert scenarios.main(["--table", "meat_support", "--n", "1", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("--- meat_support") and "Facts the note must make clear" in out


def test_main_unknown_table():
    with pytest.raises(KeyError):
        scenarios.main(["--table", "nope", "--dry-run"])


# ---- LLM settings and injection ----
def test_llm_config_flags_override_env():
    args = scenarios.parse_args(["--provider", "openai", "--model", "m", "--url", "http://h/v1"])
    cfg = scenarios.llm_config(args, {"CODING_TUTOR_LLM_MODEL": "env-model", "CODING_TUTOR_LLM_API_KEY": "k"})
    assert (cfg.provider, cfg.model, cfg.base_url, cfg.api_key) == ("openai", "m", "http://h/v1", "k")


def test_llm_config_reads_key_from_named_variable():
    args = scenarios.parse_args(["--api-key-env", "MY_KEY"])
    assert scenarios.llm_config(args, {"MY_KEY": "secret"}).api_key == "secret"


def test_llm_config_missing_key_variable():
    args = scenarios.parse_args(["--api-key-env", "MY_KEY"])
    with pytest.raises(SystemExit, match="MY_KEY is not set"):
        scenarios.llm_config(args, {})


def test_parse_args_has_no_api_key_flag(capsys):
    with pytest.raises(SystemExit):
        scenarios.parse_args(["--api-key", "sk-secret"])
    assert "unrecognized arguments" in capsys.readouterr().err


def test_main_with_injected_llm(tmp_path, capsys):
    # seed 0 picks stage 4 with hypertension, no dialysis
    good = "Chronic kidney disease, stage 4, with hypertension." + FILLER
    argv = ["--table", "ckd_staging", "--n", "1", "--seed", "0", "--out", str(tmp_path)]
    assert scenarios.main(argv, llm=fake_llm([good]), env={}) == 0
    assert "1 saved, 0 failed" in capsys.readouterr().out
    rec = json.loads(next(tmp_path.rglob("*.json")).read_text(encoding="utf-8"))
    assert rec["generator"]["model"] == "gemma4:e4b"


def test_main_reports_llm_errors(capsys):
    def broken(system, user, seed):
        raise scenarios.LLMError("http://x is not reachable: refused")

    assert scenarios.main(["--table", "ckd_staging", "--n", "1"], llm=broken, env={}) == 2
    assert "not reachable" in capsys.readouterr().err
