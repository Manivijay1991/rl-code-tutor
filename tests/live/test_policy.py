import pytest

from coding_tutor.live.policy import (
    MAX_BATCH,
    Event,
    EventError,
    arm_key,
    known_confusions,
    parse_batch,
    parse_event,
    snapshot,
)

CONFUSIONS = frozenset({"dm:missed_with_link", "ckd:wrong_ckd_stage"})
GOOD = {"confusion": "dm:missed_with_link", "bucket": 2, "action": "contrast_pair", "reward": 1}


def test_known_confusions(tables):
    ids = known_confusions(tables)
    assert "diabetes_complications:missed_with_link" in ids
    assert len(ids) == sum(len(t["confusions"]) for t in tables.values())


def test_parse_event_ok():
    assert parse_event(GOOD, CONFUSIONS) == Event("dm:missed_with_link", 2, "contrast_pair", 1)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"confusion": "dm:nope"}, "unknown confusion"),
        ({"bucket": 4}, "bucket"),
        ({"bucket": "2"}, "bucket"),
        ({"bucket": True}, "bucket"),
        ({"action": "nap"}, "unknown action"),
        ({"reward": 2}, "reward"),
        ({"reward": True}, "reward"),
        ({"student_id": "abc"}, "unexpected fields"),
    ],
    ids=[
        "confusion",
        "bucket_range",
        "bucket_str",
        "bucket_bool",
        "action",
        "reward_range",
        "reward_bool",
        "identifier",
    ],
)
def test_parse_event_rejects(change, message):
    with pytest.raises(EventError, match=message):
        parse_event({**GOOD, **change}, CONFUSIONS)


def test_parse_event_not_an_object():
    with pytest.raises(EventError, match="object"):
        parse_event(["x"], CONFUSIONS)


def test_parse_batch_ok():
    events, client = parse_batch({"events": [GOOD, GOOD], "client": "web/0.1"}, CONFUSIONS)
    assert len(events) == 2 and client == "web/0.1"
    assert parse_batch({"events": [GOOD]}, CONFUSIONS)[1] == ""


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"events": []},
        {"events": [GOOD] * (MAX_BATCH + 1)},
        {"events": "x"},
        {"events": [GOOD], "client": "x" * 33},
        {"events": [GOOD], "client": 5},
        {"events": [GOOD], "ip": "1.2.3.4"},
        {"events": [GOOD, {**GOOD, "reward": 9}]},
    ],
    ids=["list", "empty", "too_many", "not_list", "long_client", "client_type", "extra_field", "one_bad"],
)
def test_parse_batch_rejects(payload):
    with pytest.raises(EventError):
        parse_batch(payload, CONFUSIONS)


def test_snapshot():
    rows = [("dm:missed_with_link", 1, "walkthrough", 3, 1)]
    assert snapshot(rows, 4) == {"version": 1, "events": 4, "arms": {"dm:missed_with_link|1|walkthrough": [3, 1]}}
    assert snapshot([], 0)["arms"] == {}
    assert arm_key("a:b", 3, "find_meat") == "a:b|3|find_meat"
