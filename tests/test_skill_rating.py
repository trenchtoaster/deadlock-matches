import datetime as dt
import json

from deadlock_matches import assets, history, skill_rating


def test_rank_asof_picks_the_era(tmp_path):
    path = tmp_path / "rank_history.parquet"

    def era(name):
        return {"11": {"tier": 11, "name": name}}

    history.write(
        path,
        [
            {"from": "2026-01-01T00:00:00", "build": 1, "records": era("Eternus")},
            {"from": "2026-07-01T00:00:00", "build": 2, "records": era("Eternal")},
        ],
    )

    assert skill_rating.rank_asof(11, dt.date(2026, 6, 20), path) == "Eternus"
    assert skill_rating.rank_asof(11, dt.date(2026, 7, 2), path) == "Eternal"


def test_rank_asof_without_history_falls_back_to_bundled(tmp_path):
    missing = tmp_path / "none.parquet"

    assert skill_rating.rank_asof(11, dt.date(2026, 7, 2), missing) == skill_rating.tier_map()[11]
    assert skill_rating.rank_asof(999, dt.date(2026, 7, 2), missing) is None


RANK_REC = {
    "tier": 7,
    "name": "Archon",
    "images": {"large": "https://example.com/rank7/badge_lg.png"},
}


def test_label_maps_tier_and_level():
    assert skill_rating.label(76) == "Archon 6"
    assert skill_rating.label(83) == "Oracle 3"
    assert skill_rating.label(111) == "Eternus 1"


def test_label_obscurus_has_no_level():
    assert skill_rating.label(0) == "Obscurus"


def test_label_none_passes_through():
    assert skill_rating.label(None) is None


def test_label_unknown_tier():
    assert skill_rating.label(996) == "badge996"


def test_tier_map_covers_all_tiers():
    tiers = skill_rating.tier_map()

    assert len(tiers) == 12
    assert tiers[1] == "Initiate"
    assert tiers[11] == "Eternus"


def test_refresh_skill_rating_drops_images(tmp_path, monkeypatch):
    monkeypatch.setattr(assets.api, "get_json", lambda path, **kw: [RANK_REC])
    p = tmp_path / "skill_rating.json"

    assert assets.refresh_skill_rating(p) == 1

    rec = json.loads(p.read_text())[0]

    assert rec == {"tier": 7, "name": "Archon"}


def test_refresh_skill_rating_clears_cache(tmp_path, monkeypatch):
    p = tmp_path / "skill_rating.json"
    p.write_text(json.dumps([{"tier": 7, "name": "Old"}]))

    assert skill_rating.label(76, p) == "Old 6"

    monkeypatch.setattr(assets.api, "get_json", lambda path, **kw: [RANK_REC])
    assets.refresh_skill_rating(p)

    assert skill_rating.label(76, p) == "Archon 6"
