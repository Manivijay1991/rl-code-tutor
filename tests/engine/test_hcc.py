import pytest

from coding_tutor.engine import codes, hcc

DROPS = {"35": ["36", "37", "38"], "36": ["37", "38"], "37": ["38"]}


# ---- pure hierarchy logic ----
@pytest.mark.parametrize(
    ("present", "kept", "dropped"),
    [
        ({"37", "38"}, {"37"}, {"38": "37"}),
        ({"35", "37", "38"}, {"35"}, {"37": "35", "38": "35"}),
        ({"38"}, {"38"}, {}),
        (set(), set(), {}),
        ({"37", "999"}, {"37", "999"}, {}),
    ],
    ids=["one_drop", "top_wins", "alone", "empty", "unrelated"],
)
def test_apply_hierarchy(present, kept, dropped):
    assert hcc.apply_hierarchy(present, DROPS) == (kept, dropped)


def test_apply_hierarchy_no_rules():
    assert hcc.apply_hierarchy({"37", "38"}, {}) == ({"37", "38"}, {})


def test_without_db_everything_is_empty(monkeypatch):
    monkeypatch.setattr(codes, "default_db", lambda: None)
    assert hcc.raw_hccs(["E11.22"]) == {}
    assert hcc.label("37") == "HCC 37"
    assert hcc.score(["E11.22"]) == {"segment": "CNA", "total": 0, "hccs": [], "dropped": []}


# ---- against the CMS files ----
def test_official_hierarchy_loaded(db):
    drops = hcc.hierarchy(db)
    assert drops["35"] == ["36", "37", "38"]
    assert drops["326"] == ["327", "328", "329"]
    assert "155" in drops["151"]


def test_labels(db):
    assert hcc.label("37", db) == "Diabetes with Chronic Complications"
    assert hcc.label("99999", db) == "HCC 99999"


def test_v28_weights(db):
    w = hcc.weights(db, "CNA")
    assert len(w) == 115  # V28 payment HCCs
    assert w["37"] == 0.166 and w["327"] == 0.514
    with pytest.raises(ValueError, match="unknown segment"):
        hcc.weights(db, "XYZ")


@pytest.mark.parametrize("segment", sorted(hcc.SEGMENTS))
def test_every_segment_has_weights(db, segment):
    assert len(hcc.weights(db, segment)) >= 100


def test_raw_hccs(db):
    assert hcc.raw_hccs(["E11.22", "N18.4", "Q99.99"], db) == {"37": ["E11.22"], "327": ["N18.4"]}
    assert hcc.raw_hccs([], db) == {}


def test_v28_hierarchy(db):
    s = hcc.summarize(["E1122", "Z794", "N184"], db)
    assert [h["hcc"] for h in s["hccs"]] == ["37", "327"]
    assert [d["hcc"] for d in s["dropped"]] == ["38"]


def test_unspecified_mdd_has_no_v28_hcc(db):
    assert codes.hccs(db, "F339") == []
    assert codes.hccs(db, "F331") == ["155"]


def test_score_applies_hierarchy(db):
    s = hcc.score(["E1122", "Z794", "N184"], db)
    assert s["total"] == 0.68
    assert [h["hcc"] for h in s["hccs"]] == ["37", "327"]


def test_score_empty(db):
    assert hcc.score([], db)["total"] == 0


def test_score_gap_directions(db):
    under = hcc.score_gap(["E1122"], ["E1122", "N184"], db)
    assert (under["gap"], under["direction"], under["missing_hccs"]) == (-0.514, "under", ["327"])
    over = hcc.score_gap(["E1122", "N184"], ["E1122"], db)
    assert (over["gap"], over["direction"], over["extra_hccs"]) == (0.514, "over", ["327"])
    # wrong diabetes code, but V28 weights HCC 37 and 38 the same
    same = hcc.score_gap(["E119"], ["E1122"], db)
    assert (same["gap"], same["direction"], same["missing_hccs"]) == (0.0, "none", ["37"])


def test_score_gap_invalid_segment(db):
    with pytest.raises(ValueError, match="unknown segment"):
        hcc.score_gap(["E1122"], ["E1122"], db, segment="XYZ")
