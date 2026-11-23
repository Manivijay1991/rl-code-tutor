from coding_tutor.api import storage
from coding_tutor.api.policy import Event

E1 = Event("dm:x", 1, "walkthrough", 1)
E0 = Event("dm:x", 1, "walkthrough", 0)


def test_record_updates_arms_and_log():
    con = storage.connect(":memory:")
    assert storage.record(con, [E1, E1, E0], "2026-11-23", "web/0.1") == 3
    assert storage.arm_rows(con) == [("dm:x", 1, "walkthrough", 2, 1)]
    assert storage.total_events(con) == 3
    assert con.execute("SELECT DISTINCT day, client FROM events").fetchall() == [("2026-11-23", "web/0.1")]


def test_record_nothing():
    con = storage.connect(":memory:")
    assert storage.record(con, [], "2026-11-23") == 0
    assert storage.arm_rows(con) == [] and storage.total_events(con) == 0


def test_persists_on_disk(tmp_path):
    path = tmp_path / "sub" / "api.sqlite"
    con = storage.connect(path)
    storage.record(con, [E1], "d")
    con.close()
    assert storage.arm_rows(storage.connect(path)) == [("dm:x", 1, "walkthrough", 1, 0)]


def test_no_identifier_columns():
    con = storage.connect(":memory:")
    cols = {r[1] for t in ("arms", "events") for r in con.execute(f"PRAGMA table_info({t})")}
    assert not cols & {"ip", "user", "user_id", "student", "student_id", "session", "timestamp"}
