import datetime as dt

import polars as pl
import pytest
from builders import LOCAL_DAY, START, add_custom_stats, build_match, build_movement_match

from deadlock_matches import export, queries
from deadlock_matches.extract import pb


def custom_pq(tmp_path):
    info = build_match()
    add_custom_stats(
        info,
        [
            ("Parry Success", 4),
            ("Bullet Stats##HeroHitRate", 24),
        ],
    )

    for name, df in export.build_tables([info], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    return tmp_path


def test_custom_stats_joins_hero_and_day(tmp_path):
    pq = custom_pq(tmp_path)
    df = queries.custom_stats(parquet_dir=pq, tz="America/Chicago").sort("stat").collect()

    assert df.get_column("stat").to_list() == ["HeroHitRate", "Parry Success"]
    assert df.get_column("group").to_list() == ["Bullet Stats", None]
    assert df.get_column("value").to_list() == [24, 4]
    assert df.get_column("hero").to_list() == ["Mirage", "Mirage"]
    assert df.get_column("won").to_list() == [True, True]
    assert df.get_column("day").to_list() == [LOCAL_DAY, LOCAL_DAY]


def test_custom_stats_final_picks_last_snapshot(tmp_path):
    info = build_match()
    add_custom_stats(info, [("Parry Success", 4)])
    early = info.players[0].stats[0].custom_user_stats.add()
    early.id = 1
    early.value = 1

    for name, df in export.build_tables([info], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    final = queries.custom_stats(stat="Parry Success", parquet_dir=tmp_path).collect()
    raw = (
        queries.custom_stats(stat="Parry Success", final=False, parquet_dir=tmp_path)
        .sort("time_stamp_s")
        .collect()
    )

    assert final.get_column("value").to_list() == [4]
    assert raw.get_column("time_stamp_s").to_list() == [180, 600]
    assert raw.get_column("value").to_list() == [1, 4]


def test_custom_stats_filters(tmp_path):
    pq = custom_pq(tmp_path)

    by_stat = queries.custom_stats(stat="Parry Success", parquet_dir=pq).collect()
    by_group = queries.custom_stats(group="Bullet Stats", parquet_dir=pq).collect()
    by_account = queries.custom_stats(accounts=[999], parquet_dir=pq).collect()
    by_match = queries.custom_stats(matches=[100], parquet_dir=pq).collect()

    assert by_stat.get_column("value").to_list() == [4]
    assert by_group.get_column("stat").to_list() == ["HeroHitRate"]
    assert by_account.is_empty()
    assert len(by_match) == 2


def test_aim_rates_percentiles_within_hero(tmp_path):
    sharp = build_match(match_id=100)
    add_custom_stats(
        sharp,
        [
            ("Enemy Hero Accuracy##Shots", 1000),
            ("Enemy Hero Accuracy##Hits", 500),
            ("Enemy Hero Accuracy##Headshots", 200),
        ],
    )

    wild = build_match(match_id=101)
    add_custom_stats(
        wild,
        [
            ("Enemy Hero Accuracy##Shots", 1000),
            ("Enemy Hero Accuracy##Hits", 200),
            ("Enemy Hero Accuracy##Headshots", 20),
        ],
    )

    low = build_match(match_id=102)
    add_custom_stats(
        low,
        [
            ("Enemy Hero Accuracy##Shots", 50),
            ("Enemy Hero Accuracy##Hits", 50),
            ("Enemy Hero Accuracy##Headshots", 50),
        ],
    )

    for name, df in export.build_tables([sharp, wild, low], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.aim_rates(min_games=2, parquet_dir=tmp_path, tz="America/Chicago").sort("match_id")

    assert df.get_column("match_id").to_list() == [100, 101]
    assert df.get_column("hit_rate").to_list() == [50.0, 20.0]
    assert df.get_column("headshot_rate").to_list() == [40.0, 10.0]
    assert df.get_column("hit_percentile").to_list() == [100.0, 50.0]
    assert df.get_column("headshot_percentile").to_list() == [100.0, 50.0]
    assert df.get_column("hero_games").to_list() == [2, 2]

    small = queries.aim_rates(parquet_dir=tmp_path, tz="America/Chicago")

    assert small.get_column("hit_percentile").to_list() == [None, None]
    assert small.get_column("headshot_percentile").to_list() == [None, None]


def test_final_stats(pq):
    df = queries.final_stats(pq, tz="America/Chicago").collect()
    me = df.filter(pl.col("account_id") == 42)

    assert me.get_column("net_worth")[0] == 6000
    assert me.get_column("shots_hit")[0] == 70
    assert me.get_column("accuracy")[0] == pytest.approx(0.7)
    assert me.get_column("headshot_rate")[0] == pytest.approx(0.25)
    assert me.get_column("hero")[0] == "Mirage"
    assert me.get_column("won")[0] is True


def test_final_stats_adds_local_day(pq):
    df = queries.final_stats(pq, tz="America/Chicago").collect()

    assert df.get_column("day").to_list() == [LOCAL_DAY, LOCAL_DAY]


def test_final_stats_null_rates_when_nothing_fired(pq):
    df = queries.final_stats(pq, tz="America/Chicago").collect()
    other = df.filter(pl.col("account_id") == 43)

    assert other.height == 1
    assert other.get_column("accuracy")[0] is None
    assert other.get_column("headshot_rate")[0] is None


def test_team_damage_ranks_within_team(rank_pq):
    df = queries.team_damage_ranks(rank_pq).collect().sort("account_id")

    assert df.get_column("account_id").to_list() == [42, 43, 44]
    assert df.get_column("team_damage_rank").to_list() == [1, 1, 2]
    assert df.get_column("top_team_damage").to_list() == [True, True, False]


def test_team_damage_ranks_uses_final_damage(rank_pq):
    df = queries.team_damage_ranks(rank_pq).collect()

    assert df.filter(pl.col("account_id") == 42)["player_damage"][0] == 1500


def test_my_deaths_joins_game_columns(movement_pq):
    df = queries.my_deaths(movement_pq, accounts=[42], tz="America/Chicago").collect()

    assert df.height == 1
    assert df.get_column("game_time_s")[0] == 100
    assert df.get_column("killer_account_id")[0] == 43
    assert df.get_column("hero")[0] == "Mirage"
    assert df.get_column("won")[0] is True


def test_death_context_counts_nearby(movement_pq):
    df = queries.death_context(
        parquet_dir=movement_pq, accounts=[42], tz="America/Chicago"
    ).collect()

    assert df.height == 1
    assert df.get_column("allies")[0] == 0
    assert df.get_column("enemies")[0] == 1
    assert df.get_column("solo")[0] is True
    assert df.get_column("outnumbered")[0] is False


def test_death_context_radius_widens(movement_pq):
    df = queries.death_context(
        radius=20000, parquet_dir=movement_pq, accounts=[42], tz="America/Chicago"
    ).collect()

    assert df.get_column("allies")[0] == 1
    assert df.get_column("enemies")[0] == 1
    assert df.get_column("solo")[0] is False


def test_death_context_requires_movement(pq):
    with pytest.raises(ValueError, match="movement table not exported"):
        queries.death_context(parquet_dir=pq, accounts=[42], tz="America/Chicago")


def test_hero_games_filters_hero_and_queue(tmp_path):
    queued = build_movement_match(match_id=100)
    lobby = build_movement_match(match_id=101)
    lobby.match_mode = pb.k_ECitadelMatchMode_PrivateLobby

    out = tmp_path / "pq"
    out.mkdir()

    for name, df in export.build_tables([queued, lobby]).items():
        df.write_parquet(out / f"{name}.parquet")

    games = queries.hero_games("Mirage", out, accounts=[42]).collect()

    assert games.get_column("match_id").to_list() == [100]


def test_hero_games_since_window(movement_pq):
    day_after = (dt.datetime.fromtimestamp(START, dt.UTC) + dt.timedelta(days=2)).date()
    late = queries.hero_games("Mirage", movement_pq, accounts=[42], since=day_after).collect()
    early = queries.hero_games(
        "Mirage", movement_pq, accounts=[42], since=dt.date(2020, 1, 1)
    ).collect()

    assert late.is_empty()
    assert early.get_column("match_id").to_list() == [100]


def test_hero_games_unknown_hero(movement_pq):
    with pytest.raises(ValueError, match="Unknown hero"):
        queries.hero_games("Nobody", movement_pq, accounts=[42])


@pytest.fixture
def melee_pq(tmp_path):
    players = pl.DataFrame(
        {
            "match_id": [700, 700, 701],
            "account_id": [42, 99, 42],
            "hero": ["Mirage", "Yamato", "Mirage"],
            "team": [1, 0, 1],
        }
    )

    damage = pl.DataFrame(
        {
            "match_id": [700, 700, 700, 700, 700, 700, 700, 701],
            "dealer_account_id": [42, 99, 99, 99, 99, 99, 99, 42],
            "target_account_id": [99, 42, 42, None, 42, 42, 42, 99],
            "source_class": [
                "ability_melee_mirage",
                "ability_melee_yamato",
                "upgrade_melee_charge",
                "ability_melee_yamato",
                "Melee",
                "citadel_weapon_yamato",
                "ability_melee_yamato",
                "ability_melee_mirage",
            ],
            "category": [
                "ability",
                "ability",
                "item",
                "ability",
                "total",
                "gun",
                "ability",
                "ability",
            ],
            "stat": [
                "damage",
                "damage",
                "damage",
                "damage",
                "damage",
                "damage",
                "healing",
                "damage",
            ],
            "damage": [300, 500, 80, 9999, 580, 1000, 50, 777],
        },
        schema_overrides={"target_account_id": pl.Int64},
    )

    custom_stats = pl.DataFrame(
        {
            "match_id": [700, 700, 700, 700],
            "account_id": [42, 42, 42, 99],
            "time_stamp_s": [180, 360, 180, 200],
            "stat": ["Parry Success", "Parry Success", "Parry Miss", "Parry Miss"],
            "value": [1, 2, 1, 3],
        }
    )

    for name, df in {
        "players": players,
        "damage": damage,
        "custom_stats": custom_stats,
    }.items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    return tmp_path


def test_melee_by_player_sums_swings_and_final_parries(melee_pq):
    rows = {r["account_id"]: r for r in queries.melee_by_player(700, melee_pq).collect().to_dicts()}

    assert rows[42]["melee_dealt"] == 300
    assert rows[42]["melee_taken"] == 500
    assert rows[42]["parries"] == 2
    assert rows[42]["missed_parries"] == 1

    assert rows[99]["melee_dealt"] == 500
    assert rows[99]["melee_taken"] == 300
    assert rows[99]["parries"] == 0
    assert rows[99]["missed_parries"] == 3


def test_melee_by_player_keeps_the_swing_pure(melee_pq):
    rows = {r["account_id"]: r for r in queries.melee_by_player(700, melee_pq).collect().to_dicts()}

    assert rows[99]["melee_dealt"] == 500
    assert rows[42]["melee_taken"] == 500


def test_melee_by_player_scopes_to_the_match(melee_pq):
    accounts = queries.melee_by_player(700, melee_pq).collect()["account_id"].to_list()

    assert sorted(accounts) == [42, 99]


def test_melee_taken_by_attacker_ranks_pure_swings(melee_pq):
    assert queries.melee_taken_by_attacker(700, 42, melee_pq).collect().rows() == [("Yamato", 500)]
