import json

import pytest

from coding_tutor import catalog
from coding_tutor.catalog import CatalogError


def topic_json(tid, **kw):
    return {"id": tid, "title": tid.title(), "kind": "hcc", "description": "", "order": 10, "enabled": True, **kw}


def make_topic(root, tid, tables=("t1",), scenarios=None, **kw):
    """Create content/topics/<tid> with tables and optional scenarios {table: [ids]}."""
    folder = root / tid
    (folder / "tables").mkdir(parents=True)
    (folder / "topic.json").write_text(json.dumps(topic_json(tid, **kw)), encoding="utf-8")
    for t in tables:
        (folder / "tables" / f"{t}.json").write_text(json.dumps({"id": t}), encoding="utf-8")
    for t, ids in (scenarios or {}).items():
        (folder / "scenarios" / t).mkdir(parents=True)
        for sid in ids:
            (folder / "scenarios" / t / f"{sid}.json").write_text(json.dumps({"id": sid, "table": t}), encoding="utf-8")
    return folder


# ---- topics ----
def test_load_topics_sorted_and_disabled_hidden(tmp_path):
    make_topic(tmp_path, "zeta", ("z1",), order=1)
    make_topic(tmp_path, "alpha", ("a1",), order=5)
    make_topic(tmp_path, "old", ("o1",), enabled=False)
    (tmp_path / "_drafts").mkdir()  # ignored: underscore folders are not topics
    assert [t.id for t in catalog.load_topics(tmp_path)] == ["zeta", "alpha"]
    assert [t.id for t in catalog.load_topics(tmp_path, include_disabled=True)] == ["zeta", "alpha", "old"]


def test_load_topics_missing_root_is_empty(tmp_path):
    assert catalog.load_topics(tmp_path / "nope") == []


@pytest.mark.parametrize(
    ("data", "match"),
    [
        (None, "missing topic.json"),
        (topic_json("other"), "must equal the folder name"),
        ({**topic_json("ckd"), "kind": "magic"}, "must be one of"),
        ({k: v for k, v in topic_json("ckd").items() if k != "title"}, "missing required 'title'"),
    ],
)
def test_load_topic_rejects_bad_folders(tmp_path, data, match):
    folder = tmp_path / "ckd"
    folder.mkdir()
    if data is not None:
        (folder / "topic.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CatalogError, match=match):
        catalog.load_topic(folder)


# ---- tables and scenarios ----
def test_table_index_and_topic_of(tmp_path):
    make_topic(tmp_path, "ckd", ("ckd_a", "ckd_b"))
    make_topic(tmp_path, "dm", ("dm_a",))
    index = catalog.table_index(catalog.load_topics(tmp_path))
    assert sorted(index) == ["ckd_a", "ckd_b", "dm_a"]
    assert catalog.topic_of("dm_a", index).id == "dm"
    with pytest.raises(CatalogError, match="no topic has a table 'nope'"):
        catalog.topic_of("nope", index)


def test_table_index_rejects_duplicate_and_missing_ids(tmp_path):
    make_topic(tmp_path, "a", ("same",))
    make_topic(tmp_path, "b", ("same",))
    with pytest.raises(CatalogError, match="already used"):
        catalog.table_index(catalog.load_topics(tmp_path))
    bad = tmp_path / "bad"
    make_topic(bad, "c", ())
    (bad / "c" / "tables" / "x.json").write_text("{}", encoding="utf-8")
    with pytest.raises(CatalogError, match="has no id"):
        catalog.table_index(catalog.load_topics(bad))


def test_scenario_paths_and_load_scenarios(tmp_path):
    make_topic(tmp_path, "ckd", ("t1", "t2"), {"t1": ["s2", "s1"], "t2": ["s3"]})
    make_topic(tmp_path, "dm", ("t3",), {"t3": ["s4"]}, enabled=False)
    topics = catalog.load_topics(tmp_path)
    assert [p.stem for p in catalog.scenario_paths(topics)] == ["s1", "s2", "s3"]
    assert [p.stem for p in catalog.scenario_paths(topics, {"t2"})] == ["s3"]
    assert [r["id"] for r in catalog.load_scenarios(root=tmp_path)] == ["s1", "s2", "s3"]  # disabled topic left out
    assert [r["id"] for r in catalog.load_scenarios(topic_ids={"ckd"}, table_ids={"t1"}, root=tmp_path)] == ["s1", "s2"]
    assert catalog.scenario_dir(topics[0], "t1") == tmp_path / "ckd" / "scenarios" / "t1"
    assert catalog.load_scenarios(root=tmp_path / "empty") == []


def test_load_scenarios_from_a_flat_directory(tmp_path):
    (tmp_path / "t1").mkdir()
    (tmp_path / "t1" / "b.json").write_text(json.dumps({"id": "b"}), encoding="utf-8")
    (tmp_path / "t1" / "a.json").write_text(json.dumps({"id": "a"}), encoding="utf-8")
    assert [r["id"] for r in catalog.load_scenarios(directory=tmp_path)] == ["a", "b"]
    assert catalog.load_scenarios(directory=tmp_path, table_ids={"other"}) == []
    with pytest.raises(FileNotFoundError, match="not found"):
        catalog.load_scenarios(directory=tmp_path / "missing")


# ---- HCC groups ----
def test_load_hcc_groups_and_index(tmp_path):
    path = tmp_path / "g.json"
    path.write_text(
        json.dumps({"model": "m", "groups": {"kidney": {"title": "Kidney", "hccs": ["326", "327"]}}}), "utf-8"
    )
    groups = catalog.load_hcc_groups(path)
    assert catalog.group_of_hcc(groups) == {"326": "kidney", "327": "kidney"}


@pytest.mark.parametrize(
    ("groups", "match"),
    [
        ({"a": {"title": "A", "hccs": ["1"]}, "b": {"title": "B", "hccs": ["1"]}}, "HCC 1 is in both"),
        ({"a": {"title": "A", "hccs": []}}, "needs at least 1"),
        ({"a": {"title": "A", "hccs": ["x1"]}}, "does not match"),
    ],
)
def test_load_hcc_groups_rejects_bad_files(tmp_path, groups, match):
    path = tmp_path / "g.json"
    path.write_text(json.dumps({"model": "m", "groups": groups}), encoding="utf-8")
    with pytest.raises(CatalogError, match=match):
        catalog.load_hcc_groups(path)


# ---- the real content ----
def test_real_catalog_is_consistent(tables):
    topics = catalog.load_topics(include_disabled=True)
    index = catalog.table_index(topics)
    assert set(tables) <= set(index)  # every loaded table belongs to a topic
    for r in catalog.load_scenarios():
        assert r["table"] in index, r["id"]


def test_real_hcc_groups_list_every_v28_hcc_once(db):
    groups = catalog.load_hcc_groups()
    listed = [h for g in groups.values() for h in g["hccs"]]
    model = {h for (h,) in db.execute("SELECT hcc FROM hcc_label WHERE model = 'CMS-HCC-V28'")}
    assert len(listed) == len(set(listed)) and set(listed) == model
