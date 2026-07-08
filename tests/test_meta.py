import pytest

from deadlock_matches import items, meta

EE = 3005970438


def _item_id(name):
    item = items.item_by_name(name)

    assert item is not None

    return item.id


def _stats():
    """Return item stats rows for Escalating Exposure and two other 6400 soul items."""
    boundless = _item_id("Boundless Spirit")
    echo = _item_id("Echo Shard")

    return [
        {"item_id": EE, "wins": 534, "losses": 466, "matches": 1000, "avg_buy_time_s": 1680},
        {"item_id": boundless, "wins": 600, "losses": 400, "matches": 1000, "avg_buy_time_s": 1980},
        {"item_id": echo, "wins": 560, "losses": 440, "matches": 1000, "avg_buy_time_s": 1500},
        {"item_id": 111, "wins": 1, "losses": 1, "matches": 2, "avg_buy_time_s": 60},
    ]


def test_rank_items_filters_small_samples_and_sorts():
    ranked = meta.rank_items(_stats(), min_matches=1000)

    assert ranked[0]["name"] == "Boundless Spirit"
    assert all(r["matches"] >= 1000 for r in ranked)
    assert not any(r["cost"] is None for r in ranked)


def test_verdict_edge_vs_same_cost_peers():
    v = meta.verdict(_stats(), "Escalating Exposure", min_matches=1000)

    assert v["win_rate"] == 53.4
    assert round(v["peer_cost_avg"], 1) == 58.0
    assert round(v["edge_vs_peers"], 1) == -4.6


def test_verdict_unknown_item_raises():
    with pytest.raises(ValueError, match="unknown item"):
        meta.verdict(_stats(), "Nope")


def test_min_badge_maps_ranks_and_all():
    assert meta.min_badge("Eternus") == 111
    assert meta.min_badge("archon") == 71
    assert meta.min_badge("all") is None


def test_min_badge_unknown_rank_raises():
    with pytest.raises(ValueError, match="Unknown rank"):
        meta.min_badge("Gold")


def test_item_stats_url_carries_badge_and_since(monkeypatch):
    seen = []
    monkeypatch.setattr(meta.api, "get_json", lambda path, **kw: seen.append(path) or [])

    meta.get_item_stats(52, badge=111, since="2026-06-30")
    meta.get_item_pairs(52)

    assert seen[0] == (
        "v1/analytics/item-stats?hero_id=52&min_average_badge=111&min_unix_timestamp=1782777600"
    )
    assert seen[1] == "v1/analytics/item-permutation-stats?hero_id=52&comb=2"


def test_bad_since_date_raises():
    with pytest.raises(ValueError):
        meta.get_item_stats(52, since="june")


def test_hero_baseline_finds_hero():
    rows = [
        {"hero_id": 1, "wins": 100, "losses": 100, "matches": 200},
        {"hero_id": 52, "wins": 60, "losses": 40, "matches": 100},
    ]

    assert meta.hero_baseline(rows, 52) == {"win_rate": 60.0, "matches": 100}
    assert meta.hero_baseline(rows, 99) is None


def test_get_hero_stats_builds_path(monkeypatch):
    seen = {}

    def fake_get(path, **kw):
        seen["path"] = path

        return []

    monkeypatch.setattr(meta.api, "get_json", fake_get)

    meta.get_hero_stats()

    assert seen["path"] == "v1/analytics/hero-stats"

    meta.get_hero_stats(badge=111, since="2026-07-01")

    assert seen["path"].startswith("v1/analytics/hero-stats?min_average_badge=111")
    assert "min_unix_timestamp=" in seen["path"]


def test_get_hero_stats_bucket_and_until_in_url(monkeypatch):
    seen = {}

    def fake_get(path, **kw):
        seen["path"] = path

        return []

    monkeypatch.setattr(meta.api, "get_json", fake_get)

    meta.get_hero_stats(bucket="avg_badge", until="2026-07-01")

    assert seen["path"] == "v1/analytics/hero-stats?bucket=avg_badge&max_unix_timestamp=1782864000"


def test_hero_meta_rates_and_sort():
    rows = [
        {"hero_id": 1, "wins": 40, "losses": 60, "matches": 100},
        {"hero_id": 2, "wins": 80, "losses": 20, "matches": 100},
        {"hero_id": 3, "wins": 100, "losses": 100, "matches": 200},
    ]

    table = meta.hero_meta(rows)

    assert [r["hero_id"] for r in table] == [2, 3, 1]
    assert table[0]["win_rate"] == 80.0
    assert table[0]["pick_rate"] == 300.0


def test_bucket_meta_pool_counts_whole_matches():
    rows = [
        {"hero_id": 1, "bucket": 80, "wins": 30, "losses": 30, "matches": 60},
        {"hero_id": 2, "bucket": 80, "wins": 30, "losses": 30, "matches": 60},
        {"hero_id": 1, "bucket": 90, "wins": 20, "losses": 16, "matches": 36},
    ]

    table = meta.bucket_meta(rows)

    assert table == [
        {"bucket": 80, "matches": 10, "share": pytest.approx(100 * 120 / 156)},
        {"bucket": 90, "matches": 3, "share": pytest.approx(100 * 36 / 156)},
    ]


def test_bucket_meta_hero_rates_inside_each_bucket():
    rows = [
        {"hero_id": 52, "bucket": 80, "wins": 6, "losses": 4, "matches": 10},
        {"hero_id": 1, "bucket": 80, "wins": 55, "losses": 55, "matches": 110},
        {"hero_id": 52, "bucket": 90, "wins": 1, "losses": 3, "matches": 4},
        {"hero_id": 1, "bucket": 90, "wins": 22, "losses": 22, "matches": 44},
    ]

    table = meta.bucket_meta(rows, hero_id=52)

    assert table[0] == {
        "bucket": 80,
        "matches": 10,
        "win_rate": 60.0,
        "pick_rate": pytest.approx(100 * 12 * 10 / 120),
    }
    assert table[1]["win_rate"] == 25.0


def test_analytics_endpoints_expire_daily(monkeypatch):
    seen = []

    def fake_get(path, **kw):
        seen.append(kw.get("max_age"))

        return []

    monkeypatch.setattr(meta.api, "get_json", fake_get)

    meta.get_item_stats(52)
    meta.get_item_pairs(52)
    meta.get_hero_stats()

    assert seen == [meta.api.DAY] * 3


def test_synergies_merges_both_purchase_orders():
    boundless = _item_id("Boundless Spirit")
    pairs = [
        {"item_ids": [EE, boundless], "wins": 400, "losses": 200, "matches": 600},
        {"item_ids": [boundless, EE], "wins": 250, "losses": 150, "matches": 400},
    ]

    syn = meta.synergies(pairs, _stats(), "Escalating Exposure", min_matches=500)

    assert len(syn["pairs"]) == 1
    assert syn["pairs"][0]["matches"] == 1000
    assert syn["pairs"][0]["pair_win_rate"] == 65.0


def test_synergies_vs_solo_and_min_matches():
    boundless = _item_id("Boundless Spirit")
    echo = _item_id("Echo Shard")
    pairs = [
        {"item_ids": [EE, boundless], "wins": 650, "losses": 350, "matches": 1000},
        {"item_ids": [EE, echo], "wins": 30, "losses": 10, "matches": 40},
    ]

    syn = meta.synergies(pairs, _stats(), "Escalating Exposure", min_matches=500)

    assert syn["solo"] == 53.4
    assert len(syn["pairs"]) == 1
    assert syn["pairs"][0]["name"] == "Boundless Spirit"
    assert round(syn["pairs"][0]["vs_solo"], 1) == 11.6
