import datetime as dt

import polars as pl
import pytest
from builders import (
    DUST_DEVIL,
    ECHO_SHARD,
    MYSTIC_SHOT,
    RIVAL,
    _hero_rec,
    _seed_hero_history,
    build_match,
)

from deadlock_matches import export, queries


def test_item_value(pq):
    v = queries.item_value("Mystic Shot", parquet_dir=pq)

    assert v["builds"] == 1
    assert v["owned_s"] == 1500
    assert v["damage"] == 90
    assert v["per_min"] == pytest.approx(3.6)
    assert v["dealt_after_buy"] == 1300
    assert v["percent_of_hero_damage"] == pytest.approx(100 * 90 / 1300)


def test_item_value_sold_buy_still_counts(sold_pq):
    v = queries.item_value("Mystic Shot", parquet_dir=sold_pq)

    assert v["builds"] == 1
    assert v["owned_s"] == 600
    assert v["damage"] == 90
    assert v["per_min"] == pytest.approx(9.0)
    assert v["dealt_after_buy"] == 1300
    assert v["percent_of_hero_damage"] == pytest.approx(100 * 90 / 1300)


def test_item_value_rebuy_counts_damage_once(rebuy_pq):
    v = queries.item_value("Mystic Shot", parquet_dir=rebuy_pq)

    assert v["builds"] == 1
    assert v["owned_s"] == (900 - 300) + (1800 - 1200)
    assert v["damage"] == 90


def test_item_value_rebuy_excludes_gap_damage(rebuy_pq):
    v = queries.item_value("Mystic Shot", parquet_dir=rebuy_pq)

    assert v["dealt_after_buy"] == (1500 - 200) + (2600 - 2000)


def test_item_value_without_damage(pq):
    v = queries.item_value("Echo Shard", parquet_dir=pq)

    assert v["percent_of_hero_damage"] == 0.0


def test_item_value_hero_filter(pq):
    assert queries.item_value("Echo Shard", parquet_dir=pq)["builds"] == 2
    assert queries.item_value("Echo Shard", parquet_dir=pq, hero="Mirage")["builds"] == 1


def test_item_value_accounts_filter(pq):
    v = queries.item_value("Echo Shard", parquet_dir=pq, accounts=[42])

    assert v["builds"] == 1
    assert v["owned_s"] == 900

    assert queries.item_value("Echo Shard", parquet_dir=pq, accounts=[42, 43])["builds"] == 2
    assert queries.item_value("Mystic Shot", parquet_dir=pq, accounts=[43])["builds"] == 0


def test_item_value_unknown_item(pq):
    with pytest.raises(ValueError, match="Unknown item"):
        queries.item_value("Nonsense Item", parquet_dir=pq)


def test_item_buys_ranks_named_purchases_only(pq):
    df = queries.item_buys(parquet_dir=pq, accounts=[42]).collect().sort("buy_n")

    assert df.get_column("item").to_list() == ["Mystic Shot", "Echo Shard"]
    assert df.get_column("buy_n").to_list() == [1, 2]


def test_item_buys_filters_item_name(pq):
    df = queries.item_buys("Echo Shard", parquet_dir=pq, accounts=[42]).collect()

    assert df.height == 1
    assert df.get_column("game_time_s")[0] == 900
    assert df.get_column("buy_n")[0] == 2


def test_item_buys_filters_accounts(pq):
    df = queries.item_buys(parquet_dir=pq, accounts=[43]).collect()

    assert df.get_column("account_id").to_list() == [43]
    assert df.get_column("buy_n").to_list() == [1]


def test_item_buys_requires_accounts(pq):
    with pytest.raises(ValueError, match="no accounts"):
        queries.item_buys(parquet_dir=pq, accounts=[])


def test_item_buys_filters_tier(pq):
    df = queries.item_buys(parquet_dir=pq, accounts=[42], tier=4).collect()

    assert df.get_column("item").to_list() == ["Echo Shard"]
    assert df.get_column("buy_n").to_list() == [2]


def test_item_buys_tier_and_item_combine(pq):
    assert (
        queries.item_buys("Mystic Shot", parquet_dir=pq, accounts=[42], tier=4).collect().is_empty()
    )
    assert (
        queries.item_buys("Mystic Shot", parquet_dir=pq, accounts=[42], tier=2).collect().height
        == 1
    )


def _effective_by_item(parquet_dir, account_id=42):
    df = queries.item_events_effective(parquet_dir).collect()

    return {
        r["item_id"]: r["effective_cost"]
        for r in df.filter(pl.col("account_id") == account_id).iter_rows(named=True)
    }


def test_effective_cost_outright_buy_pays_the_era_price(effective_pq):
    assert _effective_by_item(effective_pq)[DUST_DEVIL] == 500


def test_effective_cost_nets_the_consumed_component(effective_pq):
    by_item = _effective_by_item(effective_pq)

    assert by_item[ECHO_SHARD] == 1750
    assert by_item[MYSTIC_SHOT] == 1250


def test_effective_cost_sell_gets_no_refund_credit(effective_pq):
    by_item = _effective_by_item(effective_pq)

    assert by_item[DUST_DEVIL] == 500
    assert sum(by_item.values()) == 3500


def test_effective_cost_upgrade_without_components_pays_full_price(effective_pq):
    assert _effective_by_item(effective_pq, account_id=43)[ECHO_SHARD] == 3000


def test_effective_cost_sums_to_the_souls_spent(effective_pq):
    df = queries.item_events_effective(effective_pq).collect().filter(pl.col("account_id") == 42)
    consumed = int(df.filter(pl.col("flags") == 1).get_column("cost").sum())
    total = int(df.get_column("cost").sum())

    assert df.get_column("effective_cost").sum() == total - consumed


def test_effective_cost_same_second_upgrades_credit_once(double_upgrade_pq):
    by_item = _effective_by_item(double_upgrade_pq)

    assert by_item[RIVAL] == 750
    assert by_item[ECHO_SHARD] == 3000
    assert sum(by_item.values()) == 5500


def test_effective_cost_tier_skip_credits_the_chain(skip_upgrade_pq):
    by_item = _effective_by_item(skip_upgrade_pq)

    assert by_item[ECHO_SHARD] == 2500
    assert by_item[DUST_DEVIL] == 500


def test_effective_cost_chain_collision_prefers_the_direct_component(chain_collision_pq):
    by_item = _effective_by_item(chain_collision_pq)

    assert by_item[MYSTIC_SHOT] == 750
    assert by_item[RIVAL] == 2000
    assert by_item[ECHO_SHARD] == 3000


def test_item_games_effective_cost(effective_pq):
    df = queries.item_games("Echo Shard", parquet_dir=effective_pq, accounts=[42]).collect()

    assert df.get_column("effective_cost").to_list() == [1750]


def test_item_games_effective_cost_null_without_history(pq, monkeypatch):
    monkeypatch.setattr(export, "PARQUET_DIR", pq)

    df = queries.item_games("Echo Shard", parquet_dir=pq, accounts=[42]).collect()

    assert df.get_column("effective_cost").to_list() == [None]


def test_item_games_joins_buy_and_damage(pq):
    df = queries.item_games("Mystic Shot", "Mirage", pq, accounts=[42]).collect()

    assert df.height == 1
    assert df.get_column("game_time_s")[0] == 300
    assert df.get_column("owned_s")[0] == 1500
    assert df.get_column("won")[0] is True
    assert df.get_column("damage")[0] == 90


def test_item_games_adds_purchase_order_columns(pq):
    df = queries.item_games("Mystic Shot", "Mirage", pq, accounts=[42]).collect()

    assert df.get_column("buy_n")[0] == 1
    assert df.get_column("tier_buy_n")[0] == 1
    assert df.get_column("first_tier_item")[0] == "Mystic Shot"
    assert df.get_column("first_tier_time_s")[0] == 300
    assert df.get_column("is_first_tier_item")[0] is True


def test_item_games_marks_first_tier_item(pq):
    df = queries.item_games("Echo Shard", "Mirage", pq, accounts=[42]).collect()

    assert df.get_column("buy_n")[0] == 2
    assert df.get_column("tier_buy_n")[0] == 1
    assert df.get_column("first_tier_item")[0] == "Echo Shard"
    assert df.get_column("is_first_tier_item")[0] is True


def test_item_games_order_columns_null_when_unbuilt(pq):
    df = queries.item_games("Healbane", "Mirage", pq, accounts=[42]).collect()

    assert df.get_column("buy_n")[0] is None
    assert df.get_column("tier_buy_n")[0] is None
    assert df.get_column("first_tier_item")[0] == "Mystic Shot"
    assert df.get_column("is_first_tier_item")[0] is False


def test_item_games_sold_buy_still_built(sold_pq):
    df = queries.item_games("Mystic Shot", "Mirage", sold_pq, accounts=[42]).collect()

    assert df.height == 1
    assert df.get_column("game_time_s")[0] == 300
    assert df.get_column("owned_s")[0] == 600
    assert df.get_column("damage")[0] == 90
    assert df.get_column("dealt_after_buy")[0] == 1300


def test_item_games_dealt_after_buy(pq):
    df = queries.item_games("Mystic Shot", "Mirage", pq, accounts=[42]).collect()

    assert df.get_column("dealt_after_buy")[0] == 1300


def test_item_games_keeps_unbuilt_games(pq):
    df = queries.item_games("Healbane", "Mirage", pq, accounts=[42]).collect()

    assert df.height == 1
    assert df.get_column("game_time_s")[0] is None
    assert df.get_column("dealt_after_buy")[0] is None


def test_item_games_unknown_item(pq):
    with pytest.raises(ValueError, match="Unknown item"):
        queries.item_games("Nonsense Item", parquet_dir=pq, accounts=[42])


def test_item_games_hero_filter(pq):
    assert queries.item_games("Echo Shard", "Haze", pq, accounts=[42]).collect().is_empty()


def test_item_games_since_filters_days(pq):
    kept = queries.item_games("Mystic Shot", "Mirage", pq, accounts=[42], since="2026-06-30")

    assert kept.collect().height == 1

    gone = queries.item_games("Mystic Shot", "Mirage", pq, accounts=[42], since="2026-07-04")

    assert gone.collect().is_empty()


def test_ability_upgrades_maps_ability_rows(pq):
    df = queries.ability_upgrades("Mirage", pq, accounts=[42], tz="America/Chicago").collect()

    assert df.get_column("ability").to_list() == ["Dust Devil"]
    assert df.get_column("game_time_s").to_list() == [60]
    assert df.get_column("ability_upgrade_n").to_list() == [1]
    assert df.get_column("ability_point_cost").to_list() == [0]
    assert df.get_column("ability_points_spent").to_list() == [0]
    assert df.get_column("ability_unlock_n").to_list() == [1]
    assert df.get_column("reward").to_list() == ["ability_unlocks"]
    assert df.get_column("level").to_list() == [1]
    assert df.get_column("required_souls").to_list() == [0]


def test_ability_upgrades_tracks_order_and_souls(pq):
    df = queries.ability_upgrades("Mirage", pq, accounts=[42], tz="America/Chicago").collect()

    row = df.filter(pl.col("ability") == "Echo Shard")
    assert row.is_empty()

    dust = df.filter(pl.col("ability") == "Dust Devil")
    assert dust.get_column("ability_upgrade_n").to_list() == [1]


def test_ability_upgrades_maps_tier_costs_to_soul_thresholds(tmp_path):
    info = build_match(match_id=900)
    player = info.players[0]
    del player.items[:]

    for item_id, t in [
        (3733594387, 19),
        (3733594387, 48),
        (2221949202, 101),
        (1336069669, 188),
        (3733594387, 262),
        (1336069669, 320),
        (2604653402, 381),
        (1336069669, 541),
        (2221949202, 594),
        (2221949202, 673),
        (1336069669, 860),
        (3733594387, 1170),
        (2221949202, 1555),
        (2604653402, 1725),
        (2604653402, 1870),
        (2604653402, 2393),
    ]:
        it = player.items.add()
        it.item_id = item_id
        it.game_time_s = t

    for name, df in export.build_tables([info], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.ability_upgrades("Mirage", tmp_path, accounts=[42], tz="America/Chicago").collect()

    assert df.get_column("ability_point_cost").to_list() == [
        0,
        1,
        0,
        0,
        2,
        1,
        0,
        2,
        1,
        2,
        5,
        5,
        5,
        1,
        2,
        5,
    ]
    assert df.get_column("ability_points_spent").to_list()[-1] == 32
    assert df.get_column("required_souls").to_list()[-1] == 48600
    assert df.get_column("level").to_list()[-1] == 36


def test_ability_upgrades_maps_events_to_level_rewards(pq):
    df = queries.ability_upgrades("Mirage", pq, accounts=[42], tz="America/Chicago").collect()

    assert df.get_column("ability").to_list() == ["Dust Devil"]
    assert df.get_column("game_time_s").to_list() == [60]
    assert df.get_column("ability_upgrade_n").to_list() == [1]
    assert df.get_column("ability_event_n").to_list() == [1]
    assert df.get_column("reward").to_list() == ["ability_unlocks"]
    assert df.get_column("level").to_list() == [1]
    assert df.get_column("required_souls").to_list() == [0]


def _dust_match(match_id, start_ts, n_events):
    info = build_match(match_id=match_id)
    info.start_time = start_ts
    player = info.players[0]
    del player.items[:]

    for i in range(n_events):
        it = player.items.add()
        it.item_id = DUST_DEVIL
        it.game_time_s = 60 + i * 60

    return info


def test_ability_upgrades_uses_era_correct_soul_thresholds(tmp_path, monkeypatch):
    _seed_hero_history(tmp_path, monkeypatch, _hero_rec(1000, rs=500), _hero_rec(1000, rs=800))
    ts1 = int(dt.datetime(2026, 1, 15, tzinfo=dt.UTC).timestamp())
    ts2 = int(dt.datetime(2026, 2, 15, tzinfo=dt.UTC).timestamp())
    tables = export.build_tables(
        [_dust_match(1, ts1, 2), _dust_match(2, ts2, 2)], exclude=("movement",)
    )

    for name, df in tables.items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.ability_upgrades("Mirage", tmp_path, accounts=[42]).collect()
    pts = df.filter(pl.col("ability_point_cost") > 0).sort("match_id")

    assert pts.get_column("required_souls").to_list() == [500, 800]
