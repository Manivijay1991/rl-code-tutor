import sqlite3

from coding_tutor.live.policy import Event
from coding_tutor.live.stores import sqlite as storage

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


def test_legacy_bucket_columns_are_renamed_and_data_kept(tmp_path):
    path = tmp_path / "old.sqlite"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE arms(confusion TEXT, bucket INTEGER, action TEXT, successes INTEGER NOT NULL DEFAULT 0, "
        "failures INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(confusion, bucket, action));"
        "CREATE TABLE events(id INTEGER PRIMARY KEY, day TEXT NOT NULL, confusion TEXT NOT NULL,"
        " bucket INTEGER NOT NULL, action TEXT NOT NULL, reward INTEGER NOT NULL, client TEXT NOT NULL DEFAULT '');"
        "INSERT INTO arms VALUES ('dm:x', 2, 'walkthrough', 3, 1);"
        "INSERT INTO events(day, confusion, bucket, action, reward) VALUES ('d', 'dm:x', 2, 'walkthrough', 1);"
    )
    old.close()
    con = storage.connect(path)
    assert storage.arm_rows(con) == [("dm:x", 2, "walkthrough", 3, 1)]
    storage.record(con, [Event("dm:x", 2, "walkthrough", 1)], "d")
    assert storage.arm_rows(con) == [("dm:x", 2, "walkthrough", 4, 1)] and storage.total_events(con) == 2
    assert storage.rename_legacy_columns(con) == []  # already migrated: nothing to do


def test_no_identifier_columns():
    con = storage.connect(":memory:")
    cols = {r[1] for t in ("arms", "events") for r in con.execute(f"PRAGMA table_info({t})")}
    assert not cols & {"ip", "user", "user_id", "student", "student_id", "session", "timestamp"}
