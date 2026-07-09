import datetime as dt
import zoneinfo

import polars as pl
import pytest

from deadlock_matches import export, heroes, history, queries, schemas, timeline
from deadlock_matches.extract import pb

START = 1783000000
LOCAL_DAY = (
    dt.datetime.fromtimestamp(START, dt.UTC).astimezone(zoneinfo.ZoneInfo("America/Chicago")).date()
)


MYSTIC_SHOT = 395867183
ECHO_SHARD = 630839635
DUST_DEVIL = 1336069669


def build_match(match_id=100, account_id=42, level=None, max_health=None):
    info = pb.CMsgMatchMetaDataContents().match_info
    info.match_id = match_id
    info.start_time = START
    info.duration_s = 1800
    info.winning_team = pb.k_ECitadelLobbyTeam_Team1
    info.match_mode = pb.k_ECitadelMatchMode_Unranked

    a = info.players.add()
    a.account_id = account_id
    a.hero_id = 52
    a.team = pb.k_ECitadelLobbyTeam_Team1
    a.player_slot = 1

    for item_id, t in [(DUST_DEVIL, 60), (MYSTIC_SHOT, 300), (ECHO_SHARD, 900)]:
        it = a.items.add()
        it.item_id = item_id
        it.game_time_s = t

    if level is not None and max_health is not None:
        s = a.stats.add()
        s.time_stamp_s = 600
        s.level = level
        s.max_health = max_health

    for t, hit, miss, body, crit, dealt in [(180, 10, 10, 8, 2, 200), (600, 70, 30, 45, 15, 1500)]:
        s = a.stats.add()
        s.time_stamp_s = t
        s.net_worth = t * 10
        s.shots_hit = hit
        s.shots_missed = miss
        s.hero_bullets_hit = body
        s.hero_bullets_hit_crit = crit
        s.player_damage = dealt

    b = info.players.add()
    b.account_id = 43
    b.hero_id = 1
    b.team = pb.k_ECitadelLobbyTeam_Team0
    b.player_slot = 2

    it = b.items.add()
    it.item_id = ECHO_SHARD
    it.game_time_s = 400

    s = b.stats.add()
    s.time_stamp_s = 180

    dm = info.damage_matrix
    for name, stat_type in [
        ("citadel_weapon_mirage", 0),
        ("Bullet", 0),
        ("mirage_tornado", 1),
        ("upgrade_crackshot", 0),
    ]:
        dm.source_details.source_name.append(name)
        dm.source_details.stat_type.append(stat_type)

    d = dm.damage_dealers.add()
    d.dealer_player_slot = 1

    gun = d.damage_sources.add()
    gun.source_details_index = 0
    hero_target = gun.damage_to_players.add()
    hero_target.target_player_slot = 2
    hero_target.damage.extend([50, 150])
    creep_target = gun.damage_to_players.add()
    creep_target.target_player_slot = 0
    creep_target.damage.extend([999])

    total = d.damage_sources.add()
    total.source_details_index = 1
    t = total.damage_to_players.add()
    t.target_player_slot = 2
    t.damage.extend([150])

    heal = d.damage_sources.add()
    heal.source_details_index = 2
    t = heal.damage_to_players.add()
    t.target_player_slot = 2
    t.damage.extend([30])

    shot = d.damage_sources.add()
    shot.source_details_index = 3
    t = shot.damage_to_players.add()
    t.target_player_slot = 2
    t.damage.extend([40, 90])

    return info


def build_day_match(match_id, day, *, won):
    info = build_match(match_id=match_id)
    info.start_time = START + day * 86400
    info.winning_team = 1 if won else 0

    return info


def build_rank_match(match_id=700):
    info = build_match(match_id=match_id)

    c = info.players.add()
    c.account_id = 44
    c.hero_id = 3
    c.team = pb.k_ECitadelLobbyTeam_Team1
    c.player_slot = 3

    s = c.stats.add()
    s.time_stamp_s = 600
    s.player_damage = 900

    return info


def build_movement_match(match_id=100):
    info = build_match(match_id=match_id)

    c = info.players.add()
    c.account_id = 44
    c.hero_id = 3
    c.team = pb.k_ECitadelLobbyTeam_Team1
    c.player_slot = 3

    d = info.players[0].death_details.add()
    d.game_time_s = 100
    d.time_to_kill_s = 2.0
    d.death_duration_s = 30
    d.killer_player_slot = 2
    d.death_pos.x = 500.0
    d.death_pos.y = 500.0
    d.death_pos.z = 0.0

    s = info.players[0].stats[-1]
    g = s.gold_sources.add()
    g.source = 2
    g.gold = 700

    mp = info.match_paths
    mp.interval_s = 1.0
    mp.x_resolution = 100
    mp.y_resolution = 100

    me = mp.paths.add()
    me.player_slot = 1
    me.x_max = 10000.0
    me.y_max = 10000.0
    me.x_pos.extend(range(10))
    me.y_pos.extend([0] * 10)
    me.health.extend([100] * 10)
    me.combat_type.extend([1, 1, 1, 1, 0, 0, 0, 0, 0, 0])
    me.move_type.extend([0, 4, 4, 3, 0, 7, 8, 7, 6, 0])

    for slot, pos in [(2, 5), (3, 90)]:
        p = mp.paths.add()
        p.player_slot = slot
        p.x_max = 10000.0
        p.y_max = 10000.0
        p.x_pos.extend([pos] * 120)
        p.y_pos.extend([pos] * 120)
        p.health.extend([100] * 120)
        p.combat_type.extend([0] * 120)
        p.move_type.extend([0] * 120)

    return info


def build_interval_match(match_id=500):
    info = build_match(match_id=match_id)
    info.duration_s = 1190

    a = info.players[0]
    del a.stats[:]

    rows = [
        (300, 3000, 1000, 500, 20, 2, 4, 1, 2, 300, 200, 0),
        (600, 5000, 1500, 900, 30, 5, 4, 1, 3, 300, 500, 150),
        (1180, 8000, 4000, 2000, 55, 9, 6, 4, 7, 1500, 900, 400),
    ]
    for t, worth, dealt, taken, creeps, neutrals, denies, kills, assists, obj, heal, prev in rows:
        s = a.stats.add()
        s.time_stamp_s = t
        s.net_worth = worth
        s.player_damage = dealt
        s.player_damage_taken = taken
        s.creep_kills = creeps
        s.neutral_kills = neutrals
        s.denies = denies
        s.kills = kills
        s.assists = assists
        s.boss_damage = obj
        s.player_healing = heal
        s.heal_prevented = prev

    for t in (250, 1100):
        d = a.death_details.add()
        d.game_time_s = t

    b = info.players[1]
    for t in (200, 950, 1150):
        d = b.death_details.add()
        d.game_time_s = t
        d.killer_player_slot = 1

    info.damage_matrix.sample_time_s.extend([300, 600, 1180])

    return info


def build_sold_match(match_id=300, *, rebuy=False):
    info = build_match(match_id=match_id)
    info.players[0].items[1].sold_time_s = 900

    if rebuy:
        it = info.players[0].items.add()
        it.item_id = MYSTIC_SHOT
        it.game_time_s = 1200

        for t, dealt in [(1000, 2000), (1500, 2600)]:
            s = info.players[0].stats.add()
            s.time_stamp_s = t
            s.player_damage = dealt

    return info


@pytest.fixture
def pq(tmp_path):
    for name, df in export.build_tables([build_match()], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    return tmp_path


@pytest.fixture
def sold_pq(tmp_path):
    for name, df in export.build_tables([build_sold_match()], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    return tmp_path


@pytest.fixture
def rebuy_pq(tmp_path):
    infos = [build_sold_match(rebuy=True)]

    for name, df in export.build_tables(infos, exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    return tmp_path


@pytest.fixture
def interval_pq(tmp_path):
    for name, df in export.build_tables([build_interval_match()], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    return tmp_path


@pytest.fixture
def rank_pq(tmp_path):
    for name, df in export.build_tables([build_rank_match()], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    return tmp_path


@pytest.fixture
def two_interval_pq(tmp_path):
    infos = [build_interval_match(), build_interval_match(match_id=501)]

    for name, df in export.build_tables(infos, exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    return tmp_path


@pytest.fixture
def movement_pq(tmp_path):
    out = tmp_path / "with-movement"
    out.mkdir()

    for name, df in export.build_tables([build_movement_match()]).items():
        df.write_parquet(out / f"{name}.parquet")

    return out


@pytest.fixture
def record_pq(tmp_path):
    infos = [
        build_day_match(1, 0, won=True),
        build_day_match(2, 0, won=False),
        build_day_match(3, 0, won=False),
        build_day_match(4, 1, won=True),
        build_day_match(5, 1, won=True),
    ]

    for name, df in export.build_tables(infos).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    return tmp_path


def test_scan_reads_table(pq):
    assert queries.scan("matches", pq).collect().height == 1


def test_scan_unknown_table():
    with pytest.raises(ValueError, match="Unknown table"):
        queries.scan("test")


def test_my_games_filters_to_accounts(pq):
    df = queries.my_games(pq, accounts=[42], tz="America/Chicago").collect()

    assert df.height == 1
    assert df["account_id"][0] == 42
    assert df["won"][0] is True


def test_my_games_adds_local_day(pq):
    df = queries.my_games(pq, accounts=[42], tz="America/Chicago").collect()
    start_local = df.schema["start_local"]

    assert df["day"][0] == LOCAL_DAY
    assert isinstance(start_local, pl.Datetime)
    assert start_local.time_zone == "America/Chicago"


def test_my_games_requires_accounts(pq):
    with pytest.raises(ValueError, match="no accounts"):
        queries.my_games(pq, accounts=[])


def test_daily_record_counts_and_running_total(record_pq):
    df = queries.daily_record(record_pq, accounts=[42], tz="America/Chicago")

    assert df["games"].to_list() == [3, 2]
    assert df["wins"].to_list() == [1, 2]
    assert df["losses"].to_list() == [2, 0]
    assert df["net"].to_list() == [-1, 2]
    assert df["cum_net"].to_list() == [-1, 1]
    assert df["win_rate"].to_list() == pytest.approx([100 / 3, 100.0])
    assert df["day"].is_sorted()


def test_daily_record_last_n_days_window(record_pq):
    df = queries.daily_record(record_pq, accounts=[42], tz="America/Chicago", days=1)

    assert df.height == 1
    assert df["games"].to_list() == [2]
    assert df["cum_net"].to_list() == [2]


def test_daily_record_weekly_rollup(tmp_path):
    infos = [
        build_day_match(1, 0, won=True),
        build_day_match(2, 1, won=False),
        build_day_match(3, 7, won=True),
    ]

    for name, df in export.build_tables(infos).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.daily_record(tmp_path, accounts=[42], tz="America/Chicago", by="week")

    assert df["day"].to_list() == [dt.date(2026, 6, 29), dt.date(2026, 7, 6)]
    assert df["games"].to_list() == [2, 1]
    assert df["wins"].to_list() == [1, 1]
    assert df["net"].to_list() == [0, 1]
    assert df["cum_net"].to_list() == [0, 1]


def test_daily_record_monthly_rollup(tmp_path):
    infos = [
        build_day_match(1, 0, won=True),
        build_day_match(2, 31, won=False),
        build_day_match(3, 32, won=False),
    ]

    for name, df in export.build_tables(infos).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.daily_record(tmp_path, accounts=[42], tz="America/Chicago", by="month")

    assert df["day"].to_list() == [dt.date(2026, 7, 1), dt.date(2026, 8, 1)]
    assert df["games"].to_list() == [1, 2]
    assert df["wins"].to_list() == [1, 0]
    assert df["net"].to_list() == [1, -2]
    assert df["cum_net"].to_list() == [1, -1]


def test_daily_record_unknown_bucket(record_pq):
    with pytest.raises(ValueError, match="Unknown bucket"):
        queries.daily_record(record_pq, accounts=[42], tz="America/Chicago", by="year")


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


def test_daily_record_since_cutoff(record_pq):
    full = queries.daily_record(record_pq, accounts=[42], tz="America/Chicago")
    cutoff = full["day"].to_list()[-1]

    df = queries.daily_record(
        record_pq, accounts=[42], tz="America/Chicago", since=cutoff.isoformat()
    )

    assert df["day"].to_list() == [cutoff]
    assert df["games"].to_list() == [2]


def test_daily_record_hero_filter(record_pq):
    full = queries.daily_record(record_pq, accounts=[42], tz="America/Chicago", hero="Mirage")

    assert full["games"].sum() == 5
    assert queries.daily_record(
        record_pq, accounts=[42], tz="America/Chicago", hero="Haze"
    ).is_empty()


def test_daily_record_unknown_hero(record_pq):
    with pytest.raises(ValueError, match="Unknown hero"):
        queries.daily_record(record_pq, accounts=[42], tz="America/Chicago", hero="Nobody")


def test_daily_record_counts_alt_account_match_once(tmp_path):
    info = build_match(match_id=1)
    info.players[1].team = 1

    for name, df in export.build_tables([info]).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.daily_record(tmp_path, accounts=[42, 43], tz="America/Chicago")

    assert df["games"].to_list() == [1]
    assert df["wins"].to_list() == [1]


def test_daily_record_requires_accounts(pq):
    with pytest.raises(ValueError, match="no accounts"):
        queries.daily_record(pq, accounts=[])


def test_item_buys_ranks_named_purchases_only(pq):
    df = queries.item_buys(parquet_dir=pq, accounts=[42]).collect().sort("buy_n")

    assert df["item"].to_list() == ["Mystic Shot", "Echo Shard"]
    assert df["buy_n"].to_list() == [1, 2]


def test_item_buys_filters_item_name(pq):
    df = queries.item_buys("Echo Shard", parquet_dir=pq, accounts=[42]).collect()

    assert df.height == 1
    assert df["game_time_s"][0] == 900
    assert df["buy_n"][0] == 2


def test_item_buys_filters_accounts(pq):
    df = queries.item_buys(parquet_dir=pq, accounts=[43]).collect()

    assert df["account_id"].to_list() == [43]
    assert df["buy_n"].to_list() == [1]


def test_item_buys_requires_accounts(pq):
    with pytest.raises(ValueError, match="no accounts"):
        queries.item_buys(parquet_dir=pq, accounts=[])


def test_item_buys_filters_tier(pq):
    df = queries.item_buys(parquet_dir=pq, accounts=[42], tier=4).collect()

    assert df["item"].to_list() == ["Echo Shard"]
    assert df["buy_n"].to_list() == [2]


def test_item_buys_tier_and_item_combine(pq):
    assert (
        queries.item_buys("Mystic Shot", parquet_dir=pq, accounts=[42], tier=4).collect().is_empty()
    )
    assert (
        queries.item_buys("Mystic Shot", parquet_dir=pq, accounts=[42], tier=2).collect().height
        == 1
    )


def test_hero_scaling_frame():
    df = queries.hero_scaling().collect()
    era = df.select("era_from").unique().sort("era_from")["era_from"][-1]
    mirage = df.filter((pl.col("hero_id") == 52) & (pl.col("era_from") == era)).sort("level")

    assert mirage.height == 36
    assert mirage["level"].to_list() == list(range(1, 37))
    assert mirage["base_health"][0] < mirage["base_health"][-1]
    assert mirage["required_souls"].is_sorted()
    assert df["client_version"].null_count() == 0


def test_hero_damage_keeps_only_detail_rows_on_heroes(pq):
    df = queries.hero_damage(parquet_dir=pq, tz="America/Chicago").collect()

    assert df["source_class"].to_list() == ["citadel_weapon_mirage", "upgrade_crackshot"]
    assert df["target_account_id"].to_list() == [43, 43]
    assert df["damage"].to_list() == [150, 90]


def test_hero_damage_stat_filter(pq):
    df = queries.hero_damage("healing", parquet_dir=pq, tz="America/Chicago").collect()

    assert df["source_class"].to_list() == ["mirage_tornado"]
    assert df["damage"].to_list() == [30]


def test_hero_damage_adds_dealer_hero_and_day(pq):
    df = queries.hero_damage(parquet_dir=pq, tz="America/Chicago").collect()

    assert df["hero"].to_list() == ["Mirage", "Mirage"]
    assert df["day"].to_list() == [LOCAL_DAY, LOCAL_DAY]


def test_final_stats_takes_max_and_computes_rates(pq):
    df = queries.final_stats(pq, tz="America/Chicago").collect()
    me = df.filter(pl.col("account_id") == 42)

    assert me["net_worth"][0] == 6000
    assert me["shots_hit"][0] == 70
    assert me["accuracy"][0] == pytest.approx(0.7)
    assert me["headshot_rate"][0] == pytest.approx(0.25)
    assert me["hero"][0] == "Mirage"
    assert me["won"][0] is True


def test_final_stats_adds_local_day(pq):
    df = queries.final_stats(pq, tz="America/Chicago").collect()

    assert df["day"].to_list() == [LOCAL_DAY, LOCAL_DAY]


def test_damage_by_source_totals_share_and_rate(pq):
    df = queries.damage_by_source("Mirage", accounts=[42], parquet_dir=pq)

    assert df.columns[0] == "games"
    assert df["total"].to_list() == [150, 90]
    assert df["games"].to_list() == [1, 1]
    assert df["per_min"].to_list() == [5.0, 3.0]
    assert df["percent"].sum() == pytest.approx(100.0)


def test_damage_by_source_matches_filter(pq):
    kept = queries.damage_by_source("Mirage", accounts=[42], matches=[100], parquet_dir=pq)

    assert kept["total"].to_list() == [150, 90]

    with pytest.raises(ValueError):
        queries.damage_by_source("Mirage", accounts=[42], matches=[999], parquet_dir=pq)


def test_damage_by_source_raises_without_games(pq):
    with pytest.raises(ValueError):
        queries.damage_by_source("Haze", accounts=[42], parquet_dir=pq)

    with pytest.raises(ValueError):
        queries.damage_by_source("Mirage", accounts=[], parquet_dir=pq)


def test_souls_by_source_sums_orbs(movement_pq):
    df = queries.souls_by_source("Mirage", accounts=[42], parquet_dir=movement_pq)

    assert df.columns[0] == "games"
    assert df["souls"].sum() == 700
    assert df["games"].to_list() == [1]
    assert df["percent"].to_list() == [100.0]


def test_souls_by_source_matches_filter(movement_pq):
    kept = queries.souls_by_source("Mirage", accounts=[42], matches=[100], parquet_dir=movement_pq)

    assert kept["souls"].sum() == 700

    with pytest.raises(ValueError):
        queries.souls_by_source("Mirage", accounts=[42], matches=[999], parquet_dir=movement_pq)


def test_souls_by_source_raises_without_souls(pq):
    with pytest.raises(ValueError):
        queries.souls_by_source("Mirage", accounts=[42], parquet_dir=pq)


def test_final_stats_null_rates_when_nothing_fired(pq):
    df = queries.final_stats(pq, tz="America/Chicago").collect()
    other = df.filter(pl.col("account_id") == 43)

    assert other.height == 1
    assert other["accuracy"][0] is None
    assert other["headshot_rate"][0] is None


def test_team_damage_ranks_within_team(rank_pq):
    df = queries.team_damage_ranks(rank_pq).collect().sort("account_id")

    assert df["account_id"].to_list() == [42, 43, 44]
    assert df["team_damage_rank"].to_list() == [1, 1, 2]
    assert df["top_team_damage"].to_list() == [True, True, False]


def test_team_damage_ranks_uses_final_damage(rank_pq):
    df = queries.team_damage_ranks(rank_pq).collect()

    assert df.filter(pl.col("account_id") == 42)["player_damage"][0] == 1500


def _hero_rec(max_health, rs=500):
    return {
        "id": 52,
        "name": "Mirage",
        "class_name": "hero_mirage",
        "stats": {"max_health": max_health},
        "level_up": {"base_health_from_level": 10.0},
        "levels": [
            {
                "level": 1,
                "required_souls": 0,
                "standard_upgrade": False,
                "currencies": ["ability_unlocks"],
            },
            {
                "level": 2,
                "required_souls": rs,
                "standard_upgrade": True,
                "currencies": ["ability_points"],
            },
        ],
    }


def _seed_hero_history(tmp_path, monkeypatch, first, second):
    path = tmp_path / "hero_history.parquet"
    history.write(
        path,
        [
            {"from": "2026-01-01T00:00:00", "build": 100, "records": {"52": first}},
            {"from": "2026-02-01T00:00:00", "build": 200, "records": {"52": second}},
        ],
    )
    monkeypatch.setattr(heroes, "HERO_HISTORY_PARQUET", path)


def test_hero_scaling_asof_picks_era_correct_health(tmp_path, monkeypatch):
    _seed_hero_history(tmp_path, monkeypatch, _hero_rec(1000), _hero_rec(1200))
    left = pl.LazyFrame(
        {
            "hero_id": [52, 52],
            "level": [2, 2],
            "start_time": [
                dt.datetime(2026, 1, 15, tzinfo=dt.UTC),
                dt.datetime(2026, 2, 15, tzinfo=dt.UTC),
            ],
        }
    )

    out = queries.hero_scaling_asof(left).sort("start_time").collect()

    assert out["base_health"].to_list() == [1010.0, 1210.0]


def test_hero_scaling_asof_coalesces_prehistory(tmp_path, monkeypatch):
    _seed_hero_history(tmp_path, monkeypatch, _hero_rec(1000), _hero_rec(1200))
    left = pl.LazyFrame(
        {
            "hero_id": [52],
            "level": [2],
            "start_time": [dt.datetime(2025, 6, 1, tzinfo=dt.UTC)],
        }
    )

    out = queries.hero_scaling_asof(left).collect()

    assert out["base_health"].to_list() == [1010.0]


def test_table_exists(pq, movement_pq):
    assert queries.table_exists("deaths", pq)
    assert not queries.table_exists("movement", pq)
    assert queries.table_exists("movement", movement_pq)


def test_table_exists_unknown_table():
    with pytest.raises(ValueError, match="Unknown table"):
        queries.table_exists("test")


def test_my_deaths_joins_game_columns(movement_pq):
    df = queries.my_deaths(movement_pq, accounts=[42], tz="America/Chicago").collect()

    assert df.height == 1
    assert df["game_time_s"][0] == 100
    assert df["killer_account_id"][0] == 43
    assert df["hero"][0] == "Mirage"
    assert df["won"][0] is True


def test_death_context_counts_nearby(movement_pq):
    df = queries.death_context(
        parquet_dir=movement_pq, accounts=[42], tz="America/Chicago"
    ).collect()

    assert df.height == 1
    assert df["allies"][0] == 0
    assert df["enemies"][0] == 1
    assert df["solo"][0] is True
    assert df["outnumbered"][0] is False


def test_death_context_radius_widens(movement_pq):
    df = queries.death_context(
        radius=20000, parquet_dir=movement_pq, accounts=[42], tz="America/Chicago"
    ).collect()

    assert df["allies"][0] == 1
    assert df["enemies"][0] == 1
    assert df["solo"][0] is False


def test_death_context_requires_movement(pq):
    with pytest.raises(ValueError, match="movement table not exported"):
        queries.death_context(parquet_dir=pq, accounts=[42], tz="America/Chicago")


def test_movement_profile_metrics(movement_pq):
    df = queries.movement_profile(movement_pq).collect()
    me = df.filter(pl.col("account_id") == 42)

    assert me["alive_s"][0] == 10
    assert me["slide_percent"][0] == pytest.approx(20.0)
    assert me["in_air_percent"][0] == pytest.approx(20.0)
    assert me["zipline_percent"][0] == pytest.approx(10.0)
    assert me["combat_percent"][0] == pytest.approx(40.0)
    assert me["dashes_min"][0] == pytest.approx(6.0)
    assert me["air_dashes_min"][0] == pytest.approx(6.0)
    assert me["distance"][0] == pytest.approx(700.0)
    assert me["stationary_percent"][0] == pytest.approx(0.0)


def test_movement_profile_stationary_player(movement_pq):
    df = queries.movement_profile(movement_pq).collect()
    camper = df.filter(pl.col("account_id") == 43)

    assert camper["distance"][0] == pytest.approx(0.0)
    assert camper["stationary_percent"][0] == pytest.approx(100.0)


def test_movement_profile_single_sample_track(tmp_path):
    info = build_movement_match()
    p = info.match_paths.paths.add()
    p.player_slot = 99
    p.x_max = 10000.0
    p.y_max = 10000.0
    p.x_pos.append(1)
    p.y_pos.append(1)
    p.health.append(100)

    ghost = info.players.add()
    ghost.account_id = 99
    ghost.player_slot = 99

    for name, df in export.build_tables([info]).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.movement_profile(tmp_path).collect()
    lone = df.filter(pl.col("account_id") == 99)

    assert lone["moving_s"][0] == 0
    assert lone["distance_min"][0] is None
    assert lone["souls_per_1000_units"][0] is None


def test_movement_profile_farm(movement_pq):
    df = queries.movement_profile(movement_pq).collect()
    me = df.filter(pl.col("account_id") == 42)

    assert me["farm_souls"][0] == 700
    assert me["farm_min"][0] == pytest.approx(700 / 30)
    assert me["souls_per_1000_units"][0] == pytest.approx(1000.0)


def test_item_games_joins_buy_and_damage(pq):
    df = queries.item_games("Mystic Shot", "Mirage", pq, accounts=[42]).collect()

    assert df.height == 1
    assert df["game_time_s"][0] == 300
    assert df["owned_s"][0] == 1500
    assert df["won"][0] is True
    assert df["damage"][0] == 90


def test_item_games_adds_purchase_order_columns(pq):
    df = queries.item_games("Mystic Shot", "Mirage", pq, accounts=[42]).collect()

    assert df["buy_n"][0] == 1
    assert df["tier_buy_n"][0] == 1
    assert df["first_tier_item"][0] == "Mystic Shot"
    assert df["first_tier_time_s"][0] == 300
    assert df["is_first_tier_item"][0] is True


def test_item_games_marks_first_tier_item(pq):
    df = queries.item_games("Echo Shard", "Mirage", pq, accounts=[42]).collect()

    assert df["buy_n"][0] == 2
    assert df["tier_buy_n"][0] == 1
    assert df["first_tier_item"][0] == "Echo Shard"
    assert df["is_first_tier_item"][0] is True


def test_item_games_order_columns_null_when_unbuilt(pq):
    df = queries.item_games("Healbane", "Mirage", pq, accounts=[42]).collect()

    assert df["buy_n"][0] is None
    assert df["tier_buy_n"][0] is None
    assert df["first_tier_item"][0] == "Mystic Shot"
    assert df["is_first_tier_item"][0] is False


def test_item_games_sold_buy_still_built(sold_pq):
    df = queries.item_games("Mystic Shot", "Mirage", sold_pq, accounts=[42]).collect()

    assert df.height == 1
    assert df["game_time_s"][0] == 300
    assert df["owned_s"][0] == 600
    assert df["damage"][0] == 90
    assert df["dealt_after_buy"][0] == 1300


def test_item_games_dealt_after_buy(pq):
    df = queries.item_games("Mystic Shot", "Mirage", pq, accounts=[42]).collect()

    assert df["dealt_after_buy"][0] == 1300


def test_item_games_keeps_unbuilt_games(pq):
    df = queries.item_games("Healbane", "Mirage", pq, accounts=[42]).collect()

    assert df.height == 1
    assert df["game_time_s"][0] is None
    assert df["dealt_after_buy"][0] is None


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

    assert df["ability"].to_list() == ["Dust Devil"]
    assert df["game_time_s"].to_list() == [60]
    assert df["ability_upgrade_n"].to_list() == [1]
    assert df["ability_point_cost"].to_list() == [0]
    assert df["ability_points_spent"].to_list() == [0]
    assert df["ability_unlock_n"].to_list() == [1]
    assert df["reward"].to_list() == ["ability_unlocks"]
    assert df["level"].to_list() == [1]
    assert df["required_souls"].to_list() == [0]


def test_ability_upgrades_tracks_order_and_souls(pq):
    df = queries.ability_upgrades("Mirage", pq, accounts=[42], tz="America/Chicago").collect()

    row = df.filter(pl.col("ability") == "Echo Shard")
    assert row.is_empty()

    dust = df.filter(pl.col("ability") == "Dust Devil")
    assert dust["ability_upgrade_n"].to_list() == [1]


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

    assert df["ability_point_cost"].to_list() == [0, 1, 0, 0, 2, 1, 0, 2, 1, 2, 5, 5, 5, 1, 2, 5]
    assert df["ability_points_spent"].to_list()[-1] == 32
    assert df["required_souls"].to_list()[-1] == 48600
    assert df["level"].to_list()[-1] == 36


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

    assert pts["required_souls"].to_list() == [500, 800]


def test_snapshot_players(movement_pq):
    blocks = queries.snapshot_players("Mirage", movement_pq, accounts=[42])

    assert len(blocks) == 1
    assert timeline.snapshots(blocks[0], "souls")[-1] == (600, 6000)
    assert timeline.snapshots(blocks[0], "farm")[-1] == (600, 700)


def test_snapshot_players_unknown_hero(movement_pq):
    with pytest.raises(ValueError, match="Unknown hero"):
        queries.snapshot_players("Nobody", movement_pq, accounts=[42])


def test_match_intervals_gains_per_interval(interval_pq):
    df = queries.match_intervals(500, 42, parquet_dir=interval_pq)

    assert df["start_s"].to_list() == [0, 300, 600, 900]
    assert df["souls"].to_list() == [3000, 2000, 0, 3000]
    assert df["damage"].to_list() == [1000, 500, 0, 2500]
    assert df["damage_taken"].to_list() == [500, 400, 0, 1100]
    assert df["creeps"].to_list() == [20, 10, 0, 25]
    assert df["neutrals"].to_list() == [2, 3, 0, 4]
    assert df["denies"].to_list() == [4, 0, 0, 2]
    assert df["assists"].to_list() == [2, 1, 0, 4]
    assert df["obj_damage"].to_list() == [300, 0, 0, 1200]
    assert df["healing"].to_list() == [200, 300, 0, 400]
    assert df["heal_prevented"].to_list() == [0, 150, 0, 250]


def test_match_intervals_kills_and_deaths_from_death_record(interval_pq):
    df = queries.match_intervals(500, 42, parquet_dir=interval_pq)

    assert df["kills"].to_list() == [1, 0, 0, 2]
    assert df["deaths"].to_list() == [1, 0, 0, 1]


def test_match_intervals_last_interval_ends_at_match_end(interval_pq):
    df = queries.match_intervals(500, 42, parquet_dir=interval_pq)

    assert df["end_s"].to_list() == [300, 600, 900, 1190]
    assert df["souls_min"][0] == pytest.approx(600.0)
    assert df["souls_min"][-1] == pytest.approx(3000 * 60 / 290)


def test_match_intervals_interval_size(interval_pq):
    df = queries.match_intervals(500, 42, interval_s=600, parquet_dir=interval_pq)

    assert df["start_s"].to_list() == [0, 600]
    assert df["end_s"].to_list() == [600, 1190]
    assert df["souls"].to_list() == [5000, 3000]


def test_match_intervals_unknown_match(interval_pq):
    with pytest.raises(ValueError, match="not in the tables"):
        queries.match_intervals(999, 42, parquet_dir=interval_pq)


def test_match_intervals_no_snapshots_for_account(interval_pq):
    with pytest.raises(ValueError, match="no snapshots"):
        queries.match_intervals(500, 99, parquet_dir=interval_pq)


def test_damage_intervals_gains_ordered_by_total(interval_pq):
    df = queries.damage_intervals(500, 42, interval_s=600, parquet_dir=interval_pq)

    gun = df.slice(0, 2)
    shot = df.slice(2, 2)

    assert gun["damage"].to_list() == [50, 100]
    assert gun["start_s"].to_list() == [0, 600]
    assert gun["end_s"].to_list() == [600, 1190]
    assert gun["total"].to_list() == [150, 150]
    assert shot["damage"].to_list() == [40, 50]
    assert shot["total"].to_list() == [90, 90]


def test_damage_intervals_details_on_heroes_only(interval_pq):
    df = queries.damage_intervals(500, 42, interval_s=600, parquet_dir=interval_pq)

    assert df["source_name"].n_unique() == 2
    assert df["damage"].sum() == 240
    assert set(df["delivery"]) == {"gun", "gun_proc"}


def test_damage_intervals_other_stats(interval_pq):
    df = queries.damage_intervals(500, 42, interval_s=600, parquet_dir=interval_pq, stat="healing")

    assert df["damage"].to_list() == [0, 30]


def test_damage_intervals_no_rows_for_account(interval_pq):
    with pytest.raises(ValueError, match="no damage to heroes"):
        queries.damage_intervals(500, 99, parquet_dir=interval_pq)


def test_source_intervals_matches_damage_intervals(interval_pq):
    games = pl.DataFrame({"match_id": [500], "account_id": [42]})
    many = queries.source_intervals(games, interval_s=600, parquet_dir=interval_pq).collect()
    one = queries.damage_intervals(500, 42, interval_s=600, parquet_dir=interval_pq)

    assert many.select("source_name", "delivery", "start_s", "end_s", "damage", "total").equals(one)


def test_source_intervals_covers_every_game(two_interval_pq):
    games = pl.DataFrame({"match_id": [500, 501], "account_id": [42, 42]})
    df = queries.source_intervals(games, interval_s=600, parquet_dir=two_interval_pq).collect()

    for match_id in (500, 501):
        part = df.filter(pl.col("match_id") == match_id).select(
            "source_name", "delivery", "start_s", "end_s", "damage", "total"
        )
        one = queries.damage_intervals(match_id, 42, interval_s=600, parquet_dir=two_interval_pq)

        assert part.equals(one)


def test_source_intervals_skips_unknown_players(interval_pq):
    games = pl.DataFrame({"match_id": [500, 500], "account_id": [42, 99]})
    df = queries.source_intervals(games, interval_s=600, parquet_dir=interval_pq).collect()

    assert df["account_id"].unique().to_list() == [42]


def test_source_intervals_flags_short_tail(interval_pq):
    games = pl.DataFrame({"match_id": [500], "account_id": [42]})
    df = queries.source_intervals(games, interval_s=600, parquet_dir=interval_pq).collect()

    assert df.filter(pl.col("end_s") == 600)["full"].all()
    assert not df.filter(pl.col("end_s") == 1190)["full"].any()


def test_source_intervals_other_stats(interval_pq):
    games = pl.DataFrame({"match_id": [500], "account_id": [42]})
    df = queries.source_intervals(
        games, interval_s=600, parquet_dir=interval_pq, stat="healing"
    ).collect()

    assert df["damage"].to_list() == [0, 30]


def test_ability_upgrades_maps_events_to_level_rewards(pq):
    df = queries.ability_upgrades("Mirage", pq, accounts=[42], tz="America/Chicago").collect()

    assert df["ability"].to_list() == ["Dust Devil"]
    assert df["game_time_s"].to_list() == [60]
    assert df["ability_upgrade_n"].to_list() == [1]
    assert df["ability_event_n"].to_list() == [1]
    assert df["reward"].to_list() == ["ability_unlocks"]
    assert df["level"].to_list() == [1]
    assert df["required_souls"].to_list() == [0]


def test_team_intervals_gains_and_lead(pq):
    df = queries.team_intervals(100, 300, pq)

    assert df["start_s"].to_list() == [0, 300]
    assert df["end_s"].to_list() == [300, 600]
    assert df["souls_team1"].to_list() == [1800, 4200]
    assert df["souls_team0"].to_list() == [0, 0]
    assert df["lead"].to_list() == [-1800, -6000]


def test_team_intervals_unknown_match(pq):
    with pytest.raises(ValueError, match="not in the tables"):
        queries.team_intervals(999, parquet_dir=pq)


def test_skill_rating_labels_badge_columns():
    df = pl.DataFrame(
        {"average_badge_team0": [76, 83, 0, None]},
        schema={"average_badge_team0": pl.Int64},
    ).with_columns(queries.skill_rating("average_badge_team0").alias("label"))

    assert df["label"].to_list() == ["Archon 6", "Oracle 3", "Obscurus", None]


def _write_item_history(parquet_dir):
    rows = [
        {
            "item_id": 7,
            "name": "T",
            "class_name": "upgrade_t",
            "cost": cost,
            "slot": "weapon",
            "tier": 1,
            "is_active": False,
            "description": None,
            "era_from": dt.datetime(y, m, 1, tzinfo=dt.UTC),
            "client_version": build,
        }
        for cost, y, m, build in [(500, 2026, 1, 100), (800, 2026, 2, 200)]
    ]
    path = schemas.table_path("item_history", parquet_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    schemas.conform("item_history", rows).write_parquet(path)


def test_scan_routes_asset_tables_into_subfolder(tmp_path):
    _write_item_history(tmp_path)

    assert queries.table_exists("item_history", tmp_path)
    assert not queries.table_exists("matches", tmp_path)
    assert queries.scan("item_history", tmp_path).select(pl.len()).collect().item() == 2


def test_asset_asof_picks_era_and_coalesces_prehistory(tmp_path):
    _write_item_history(tmp_path)
    left = pl.LazyFrame(
        {
            "item_id": [7, 7, 7],
            "start_time": [
                dt.datetime(2025, 1, 1, tzinfo=dt.UTC),
                dt.datetime(2026, 1, 15, tzinfo=dt.UTC),
                dt.datetime(2026, 3, 1, tzinfo=dt.UTC),
            ],
        }
    )

    out = queries.asset_asof(left, "item_history", by="item_id", parquet_dir=tmp_path)
    out = out.sort("start_time").collect()

    assert out["cost"].to_list() == [500, 500, 800]
    assert out["client_version"].to_list() == [100, 100, 200]
