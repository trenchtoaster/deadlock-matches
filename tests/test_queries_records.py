import datetime as dt

import pytest
from builders import build_abandon_match, build_day_match, build_match

from deadlock_matches import export, queries


def test_daily_record(record_pq):
    df = queries.daily_record(record_pq, accounts=[42], tz="America/Chicago")

    assert df.get_column("games").to_list() == [3, 2]
    assert df.get_column("wins").to_list() == [1, 2]
    assert df.get_column("losses").to_list() == [2, 0]
    assert df.get_column("net").to_list() == [-1, 2]
    assert df.get_column("cum_net").to_list() == [-1, 1]
    assert df.get_column("win_rate").to_list() == pytest.approx([100 / 3, 100.0])
    assert df.get_column("day").is_sorted()


def test_daily_record_last_n_days_window(record_pq):
    df = queries.daily_record(record_pq, accounts=[42], tz="America/Chicago", days=1)

    assert df.height == 1
    assert df.get_column("games").to_list() == [2]
    assert df.get_column("cum_net").to_list() == [2]


def test_daily_record_weekly_rollup(tmp_path):
    infos = [
        build_day_match(1, 0, won=True),
        build_day_match(2, 1, won=False),
        build_day_match(3, 7, won=True),
    ]

    for name, df in export.build_tables(infos).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.daily_record(tmp_path, accounts=[42], tz="America/Chicago", by="week")

    assert df.get_column("day").to_list() == [dt.date(2026, 6, 29), dt.date(2026, 7, 6)]
    assert df.get_column("games").to_list() == [2, 1]
    assert df.get_column("wins").to_list() == [1, 1]
    assert df.get_column("net").to_list() == [0, 1]
    assert df.get_column("cum_net").to_list() == [0, 1]


def test_daily_record_monthly_rollup(tmp_path):
    infos = [
        build_day_match(1, 0, won=True),
        build_day_match(2, 31, won=False),
        build_day_match(3, 32, won=False),
    ]

    for name, df in export.build_tables(infos).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.daily_record(tmp_path, accounts=[42], tz="America/Chicago", by="month")

    assert df.get_column("day").to_list() == [dt.date(2026, 7, 1), dt.date(2026, 8, 1)]
    assert df.get_column("games").to_list() == [1, 2]
    assert df.get_column("wins").to_list() == [1, 0]
    assert df.get_column("net").to_list() == [1, -2]
    assert df.get_column("cum_net").to_list() == [1, -1]


def test_daily_record_unknown_bucket(record_pq):
    with pytest.raises(ValueError, match="Unknown bucket"):
        queries.daily_record(record_pq, accounts=[42], tz="America/Chicago", by="year")


def test_daily_record_lobby_label(tmp_path):
    info = build_day_match(1, 0, won=True)
    info.average_badge_team0 = 95
    info.average_badge_team1 = 91

    for name, df in export.build_tables([info], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.daily_record(tmp_path, accounts=[42], tz="America/Chicago")

    assert df.get_column("lobby").to_list() == ["Phantom 3"]
    assert df.get_column("rated_games").to_list() == [1]


def test_daily_record_lobby_null_without_badges(record_pq):
    df = queries.daily_record(record_pq, accounts=[42], tz="America/Chicago")

    assert df.get_column("lobby").to_list() == [None, None]
    assert df.get_column("rated_games").to_list() == [0, 0]


def test_daily_record_since_cutoff(record_pq):
    full = queries.daily_record(record_pq, accounts=[42], tz="America/Chicago")
    cutoff = full.get_column("day").to_list()[-1]

    df = queries.daily_record(
        record_pq, accounts=[42], tz="America/Chicago", since=cutoff.isoformat()
    )

    assert df.get_column("day").to_list() == [cutoff]
    assert df.get_column("games").to_list() == [2]


def test_daily_record_hero_filter(record_pq):
    full = queries.daily_record(record_pq, accounts=[42], tz="America/Chicago", hero="Mirage")

    assert full.get_column("games").sum() == 5
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

    assert df.get_column("games").to_list() == [1]
    assert df.get_column("wins").to_list() == [1]


def test_daily_record_requires_accounts(pq):
    with pytest.raises(ValueError, match="no accounts"):
        queries.daily_record(pq, accounts=[])


def test_daily_record_excludes_unscored_and_counts_abandons(abandon_pq):
    df = queries.daily_record(abandon_pq, accounts=[42], tz="America/Chicago")

    assert df.get_column("games").to_list() == [4]
    assert df.get_column("wins").to_list() == [2]
    assert df.get_column("abandons").to_list() == [3]


def test_record_games_window_filters(record_pq):
    games = queries.record_games(record_pq, accounts=[42], tz="America/Chicago", days=1)

    assert games.get_column("day").n_unique() == 1
    assert games.height == 2


def test_precomputed_games_matches_direct_calls(abandon_pq):
    games = queries.record_games(abandon_pq, accounts=[42], tz="America/Chicago")

    daily = queries.daily_record(abandon_pq, games=games)
    abandons = queries.abandon_record(abandon_pq, accounts=[42], games=games)
    unscored = queries.unscored_record(games=games)

    assert daily.equals(queries.daily_record(abandon_pq, accounts=[42], tz="America/Chicago"))
    assert abandons.equals(queries.abandon_record(abandon_pq, accounts=[42], tz="America/Chicago"))
    assert unscored.equals(queries.unscored_record(abandon_pq, accounts=[42], tz="America/Chicago"))


def test_abandon_record_flags_who_left(abandon_pq):
    df = queries.abandon_record(abandon_pq, accounts=[42], tz="America/Chicago")

    assert df.get_column("match_id").to_list() == [2, 3, 4]
    assert df.get_column("you").to_list() == [False, False, True]
    assert df.get_column("ally").to_list() == [True, False, False]
    assert df.get_column("enemy").to_list() == [False, True, False]
    assert df.get_column("won").to_list() == [False, True, False]


def test_abandon_record_buys_do_not_mark_returned(abandon_pq):
    df = queries.abandon_record(abandon_pq, accounts=[42], tz="America/Chicago")
    returned = dict(zip(df.get_column("match_id"), df.get_column("returned"), strict=True))

    assert returned == {2: False, 3: False, 4: False}


def test_abandon_record_excludes_unscored(abandon_pq):
    df = queries.abandon_record(abandon_pq, accounts=[42], tz="America/Chicago")

    assert 5 not in df.get_column("match_id").to_list()


def test_abandon_record_kills_do_not_mark_returned(tmp_path):
    info = build_abandon_match(9, leaver="enemy", abandon_s=500)
    d = info.players[0].death_details.add()
    d.game_time_s = 600
    d.killer_player_slot = 2

    for name, df in export.build_tables([info], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.abandon_record(tmp_path, accounts=[42], tz="America/Chicago")

    assert df.get_column("returned").to_list() == [False]


def test_abandon_record_returned_via_damage_growth(tmp_path):
    info = build_abandon_match(9, leaver="you", abandon_s=400)
    info.players[0].items[2].game_time_s = 100
    info.damage_matrix.sample_time_s.extend([600, 1200])

    for name, df in export.build_tables([info], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.abandon_record(tmp_path, accounts=[42], tz="America/Chicago")

    assert df.get_column("returned").to_list() == [True]


def test_abandon_record_death_after_abandon_is_not_returned(tmp_path):
    info = build_abandon_match(9, leaver="enemy", abandon_s=500)
    d = info.players[1].death_details.add()
    d.game_time_s = 700
    d.killer_player_slot = 1

    for name, df in export.build_tables([info], exclude=("movement",)).items():
        df.write_parquet(tmp_path / f"{name}.parquet")

    df = queries.abandon_record(tmp_path, accounts=[42], tz="America/Chicago")

    assert df.get_column("returned").to_list() == [False]


def test_abandon_record_empty_without_abandons(record_pq):
    df = queries.abandon_record(record_pq, accounts=[42], tz="America/Chicago")

    assert df.is_empty()


def test_unscored_record_lists_left_out_games(abandon_pq):
    df = queries.unscored_record(abandon_pq, accounts=[42], tz="America/Chicago")

    assert df.get_column("match_id").to_list() == [5]
    assert df.get_column("won").to_list() == [True]


def test_unscored_record_empty_when_all_scored(record_pq):
    df = queries.unscored_record(record_pq, accounts=[42], tz="America/Chicago")

    assert df.is_empty()
