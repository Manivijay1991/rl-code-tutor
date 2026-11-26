import json
import urllib.error

import pytest

from coding_tutor.live.policy import Event
from coding_tutor.live.stores import redis
from coding_tutor.live.stores.redis import StoreError


def fake_redis():
    """An in-memory stand-in for the Upstash pipeline: supports the commands the store sends."""
    data: dict = {"hash": {}, "str": {}, "list": {}}
    sent: list = []

    def pipe(commands):
        sent.append(commands)
        out = []
        for cmd, key, *args in commands:
            if cmd == "HINCRBY":
                h = data["hash"].setdefault(key, {})
                h[args[0]] = h.get(args[0], 0) + int(args[1])
                out.append(h[args[0]])
            elif cmd == "HGETALL":
                h = data["hash"].get(key, {})
                out.append([x for kv in h.items() for x in (kv[0], str(kv[1]))] or None)
            elif cmd == "RPUSH":
                data["list"].setdefault(key, []).extend(args)
                out.append(len(data["list"][key]))
            elif cmd == "INCRBY":
                data["str"][key] = data["str"].get(key, 0) + int(args[0])
                out.append(data["str"][key])
            elif cmd == "GET":
                v = data["str"].get(key)
                out.append(None if v is None else str(v))
            elif cmd == "LRANGE":
                out.append(list(data["list"].get(key, [])) or None)
            elif cmd == "INCR":
                data["str"][key] = data["str"].get(key, 0) + 1
                out.append(data["str"][key])
            elif cmd == "EXPIRE":
                data.setdefault("ttl", {})[key] = int(args[0])
                out.append(1)
            else:
                raise AssertionError(cmd)
        return out

    return pipe, data, sent


E1 = Event("dm:x", 1, "walkthrough", 1)
E0 = Event("dm:x", 1, "walkthrough", 0)
E2 = Event("ckd:y", 2, "contrast_pair", 1)


def test_record_updates_totals_log_and_count_in_one_round_trip():
    pipe, data, sent = fake_redis()
    store = redis.redis_store(pipe)
    assert store.record([E1, E1, E0, E2], "2026-11-24", "web/0.1") == 4
    assert len(sent) == 1  # one HTTP request per batch
    assert store.arm_rows() == [("ckd:y", 2, "contrast_pair", 1, 0), ("dm:x", 1, "walkthrough", 2, 1)]
    assert store.total_events() == 4
    log = [json.loads(x) for x in data["list"]["ct:log:2026-11-24"]]
    assert log[0] == {"confusion": "dm:x", "miss_level": 1, "action": "walkthrough", "reward": 1, "client": "web/0.1"}
    assert not ({"ip", "user", "student", "timestamp"} & set(log[0]))


def test_empty_store_and_empty_batch():
    pipe, _, sent = fake_redis()
    store = redis.redis_store(pipe)
    assert store.arm_rows() == [] and store.total_events() == 0
    assert store.record([], "d") == 0
    assert len(sent) == 2  # the two reads; an empty batch sends nothing


def test_reserve_counts_every_attempt_against_both_caps_in_one_round_trip():
    pipe, data, sent = fake_redis()
    store = redis.redis_store(pipe)
    assert store.reserve(["a|1|x", "a|1|x", "a|1|x", "b|1|y"], "2026-11-26", 2, 10) == [True, True, False, True]
    assert len(sent) == 1
    assert data["str"]["ct:cap:2026-11-26:a|1|x"] == 3  # the refused attempt still counts
    assert data["str"]["ct:cap:2026-11-26:total"] == 4
    assert set(data["ttl"].values()) == {redis.CAP_TTL} and len(data["ttl"]) == 3  # every counter expires on its own
    # the total cap: one more allowed today, then everything is refused, whatever the arm
    assert store.reserve(["c|1|z", "d|1|w"], "2026-11-26", 5, 5) == [True, False]
    # a new day starts from zero
    assert store.reserve(["a|1|x"], "2026-11-27", 2, 10) == [True]


def test_feedback_is_kept_per_day_and_read_in_one_round_trip():
    pipe, data, sent = fake_redis()
    redis.redis_store(pipe).add_feedback('{"a":1}', "2026-11-25")
    redis.add_feedback(pipe, '{"b":2}', "2026-11-26")
    assert data["list"]["ct:feedback:2026-11-25"] == ['{"a":1}']
    sent.clear()
    assert redis.read_feedback(pipe, ["2026-11-24", "2026-11-25", "2026-11-26"]) == ['{"a":1}', '{"b":2}']
    assert len(sent) == 1
    assert redis.read_feedback(pipe, []) == []


def test_reserve_with_nothing_to_count_sends_nothing():
    pipe, _, sent = fake_redis()
    assert redis.redis_store(pipe).reserve([], "d", 1, 1) == []
    assert sent == []


def test_parse_arms_sums_and_sorts():
    flat = ["b|1|x|s", "2", "a|3|y|f", "1", "b|1|x|f", "5"]
    assert redis.parse_arms(flat) == [("a", 3, "y", 0, 1), ("b", 1, "x", 2, 5)]
    assert redis.parse_arms([]) == []
    with pytest.raises(ValueError):
        redis.parse_arms(["only-a-field"])


def test_store_from_env_reads_either_naming_and_requires_https():
    store = redis.store_from_env({"KV_REST_API_URL": "https://x.upstash.io", "KV_REST_API_TOKEN": "t"})
    assert callable(store.record)
    assert callable(
        redis.store_from_env({"UPSTASH_REDIS_REST_URL": "https://x", "UPSTASH_REDIS_REST_TOKEN": "t"}).arm_rows
    )
    with pytest.raises(StoreError, match="set KV_REST_API_URL"):
        redis.store_from_env({})
    with pytest.raises(StoreError, match="https"):
        redis.store_from_env({"KV_REST_API_URL": "http://x", "KV_REST_API_TOKEN": "t"})


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_upstash_pipeline_posts_commands_and_unwraps_results(monkeypatch):
    seen = {}

    def urlopen(req, timeout):
        seen.update(url=req.full_url, auth=req.get_header("Authorization"), body=json.loads(req.data), timeout=timeout)
        return FakeResponse(b'[{"result": 3}, {"result": null}]')

    monkeypatch.setattr(redis.urllib.request, "urlopen", urlopen)
    send = redis.upstash_pipeline("https://x.upstash.io/", "secret-token")
    assert send([["INCRBY", "k", 1], ["GET", "z"]]) == [3, None]
    assert seen["url"] == "https://x.upstash.io/pipeline" and seen["auth"] == "Bearer secret-token"
    assert seen["body"] == [["INCRBY", "k", 1], ["GET", "z"]]


@pytest.mark.parametrize(
    ("error", "match"),
    [
        (urllib.error.HTTPError("u", 401, "no", {}, None), "HTTP 401"),
        (urllib.error.URLError("down"), "unreachable"),
        (TimeoutError(), "unreachable"),
    ],
)
def test_upstash_pipeline_errors_never_include_the_token(monkeypatch, error, match):
    def urlopen(req, timeout):
        raise error

    monkeypatch.setattr(redis.urllib.request, "urlopen", urlopen)
    with pytest.raises(StoreError, match=match) as info:
        redis.upstash_pipeline("https://x", "secret-token")([["GET", "k"]])
    assert "secret-token" not in str(info.value)


def test_upstash_pipeline_reports_command_errors(monkeypatch):
    monkeypatch.setattr(redis.urllib.request, "urlopen", lambda req, timeout: FakeResponse(b'[{"error": "WRONGTYPE"}]'))
    with pytest.raises(StoreError, match="WRONGTYPE"):
        redis.upstash_pipeline("https://x", "t")([["GET", "k"]])
