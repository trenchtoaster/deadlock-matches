import datetime as dt

import polars as pl
import pytest
from google.protobuf import json_format

from deadlock_matches import api, export, players, queries
from deadlock_matches.extract import pb


def _build(win, names_slots):
    return {
        "win": win,
        "kda": (1, 2, 3),
        "seq": [
            {"min": i + 5, "name": n, "tier": t, "slot": s}
            for i, (n, t, s) in enumerate(names_slots)
        ],
    }


def test_item_frequency_counts_and_median():
    builds = [
        _build(True, [("Healbane", 2, "vitality"), ("Ricochet", 4, "weapon")]),
        _build(True, [("Healbane", 2, "vitality")]),
        _build(True, [("Ricochet", 4, "weapon")]),
    ]

    agg = players.item_frequency(builds)

    assert agg["n"] == 3

    healbane = next(r for r in agg["items"] if r["name"] == "Healbane")

    assert healbane["count"] == 2
    assert healbane["percent"] == 67
    assert healbane["slot"] == "vitality"


def test_item_frequency_dedupes_within_a_build():
    builds = [_build(True, [("Echo Shard", 4, "spirit"), ("Echo Shard", 4, "spirit")])]

    agg = players.item_frequency(builds)
    echo = next(r for r in agg["items"] if r["name"] == "Echo Shard")

    assert echo["count"] == 1
    assert echo["percent"] == 100


def test_item_frequency_empty():
    assert players.item_frequency([]) == {"n": 0, "items": []}


def test_build_order_keeps_sold_flags_and_filters_cheap():
    match_info = {
        "winning_team": 0,
        "players": [
            {
                "account_id": 7,
                "team": 0,
                "kills": 5,
                "deaths": 1,
                "assists": 9,
                "items": [
                    {"item_id": 3005970438, "game_time_s": 1200, "sold_time_s": 0},
                    {"item_id": 3005970438, "game_time_s": 60, "sold_time_s": 300},
                    {"item_id": 999999999, "game_time_s": 30, "sold_time_s": 0},
                ],
            }
        ],
    }

    b = players.build_order(match_info, 7)

    assert b is not None
    assert b["win"] is True
    assert [s["name"] for s in b["seq"]] == ["Escalating Exposure", "Escalating Exposure"]
    assert [s["sold"] for s in b["seq"]] == [True, False]


def test_item_frequency_excludes_sold_by_default():
    builds = [
        {
            "win": True,
            "kda": (1, 2, 3),
            "seq": [
                {"min": 1, "name": "Monster Rounds", "tier": 1, "slot": "weapon", "sold": True},
                {"min": 20, "name": "Ricochet", "tier": 4, "slot": "weapon", "sold": False},
            ],
        },
    ]

    kept = {r["name"] for r in players.item_frequency(builds)["items"]}

    assert kept == {"Ricochet"}

    full = {r["name"] for r in players.item_frequency(builds, include_sold=True)["items"]}

    assert full == {"Monster Rounds", "Ricochet"}


def _match_json(match_id=900, account_id=11, hero_id=52):
    info = pb.CMsgMatchMetaDataContents().match_info
    info.match_id = match_id
    info.start_time = 1783000000
    info.duration_s = 1800
    info.winning_team = pb.k_ECitadelLobbyTeam_Team1
    info.match_mode = pb.k_ECitadelMatchMode_Ranked

    p = info.players.add()
    p.account_id = account_id
    p.hero_id = hero_id
    p.team = pb.k_ECitadelLobbyTeam_Team1
    p.player_slot = 1
    p.kills = 5

    s = p.stats.add()
    s.time_stamp_s = 180
    s.net_worth = 3000

    return json_format.MessageToDict(info, preserving_proto_field_name=True)


def _history_row(match_id, hero_id=52, mode=1, start=1):
    return {"match_id": match_id, "hero_id": hero_id, "match_mode": mode, "start_time": start}


def test_top_players_pools_per_hero_boards_and_drops_ambiguous(monkeypatch):
    boards = {
        "Europe": [
            {"account_name": "eu1", "rank": 1, "possible_account_ids": [101]},
            {"account_name": "smurf", "rank": 2, "possible_account_ids": [201, 202]},
        ],
        "NAmerica": [{"account_name": "na1", "rank": 1, "possible_account_ids": [301]}],
    }
    calls = []

    def fake_board(region, hero_id):
        calls.append((region, hero_id))

        return boards.get(region, [])

    monkeypatch.setattr(players, "hero_leaderboard", fake_board)

    got = players.top_players(66, regions=["Europe", "NAmerica"], limit=5)

    assert [(g["name"], g["rank"], g["region"], g["account_id"]) for g in got] == [
        ("eu1", 1, "Europe", 101),
        ("na1", 1, "NAmerica", 301),
    ]
    assert calls == [("Europe", 66), ("NAmerica", 66)]


def test_top_players_respects_limit(monkeypatch):
    board = [{"account_name": f"p{r}", "rank": r, "possible_account_ids": [r]} for r in range(1, 6)]
    monkeypatch.setattr(players, "hero_leaderboard", lambda region, hero_id: board)

    got = players.top_players(66, regions=["Europe"], limit=3)

    assert [g["rank"] for g in got] == [1, 2, 3]


def test_recent_hero_matches_filters_and_sorts(monkeypatch):
    rows = [
        _history_row(1, start=5),
        _history_row(2, hero_id=99, start=9),
        _history_row(3, mode=2, start=8),
        _history_row(4, start=7),
        _history_row(5, start=6),
    ]
    monkeypatch.setattr(players, "match_history", lambda aid: rows)

    got = players.recent_hero_matches(11, 52, n=2)

    assert [m["match_id"] for m in got] == [4, 5]


def test_download_matches(tmp_path, monkeypatch):
    hist = {
        11: [_history_row(900, start=2)],
        22: [_history_row(900, start=2), _history_row(901, start=1)],
    }
    monkeypatch.setattr(players, "match_history", lambda aid: hist[aid])
    monkeypatch.setattr(api, "DATA_DIR", tmp_path)

    def fake_metadata(match_id):
        api.data_path(f"v1/matches/{match_id}/metadata").write_text("{}", encoding="utf-8")
        return _match_json(match_id)

    monkeypatch.setattr(players, "match_metadata", fake_metadata)

    tracked = [
        {"account_id": 11, "name": "someone", "rank": 3, "region": "Asia"},
        {"account_id": 22, "name": "pinned"},
    ]

    rows = players.download_matches(tracked, 52, n=5)

    assert [(r["match_id"], r["account_id"]) for r in rows] == [(900, 11), (900, 22), (901, 22)]
    assert rows[0]["rank"] == 3
    assert rows[0]["region"] == "Asia"
    assert rows[1]["rank"] is None
    assert all(r["hero_id"] == 52 for r in rows)
    assert all(r["downloaded_at"].tzinfo is not None for r in rows)


def test_download_matches_skips_failed_downloads(monkeypatch):
    monkeypatch.setattr(players, "match_history", lambda aid: [_history_row(900)])

    def boom(match_id):
        raise OSError("api down")

    monkeypatch.setattr(players, "match_metadata", boom)

    assert players.download_matches([{"account_id": 11, "name": "x"}], 52) == []


def test_matches_by_id(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DATA_DIR", tmp_path)

    def fake_metadata(match_id):
        api.data_path(f"v1/matches/{match_id}/metadata").write_text("{}", encoding="utf-8")
        return _match_json(match_id)

    monkeypatch.setattr(players, "match_metadata", fake_metadata)

    rows = players.matches_by_id([900, 901])

    assert [r["match_id"] for r in rows] == [900, 901]
    assert all(r["account_id"] is None and r["hero_id"] is None for r in rows)
    assert all(r["player"] is None and r["rank"] is None for r in rows)
    assert all(r["downloaded_at"].tzinfo is not None for r in rows)


def test_matches_by_id_skips_unreachable(monkeypatch):
    def boom(match_id):
        raise OSError("api down")

    monkeypatch.setattr(players, "match_metadata", boom)

    assert players.matches_by_id([900, 901]) == []


def test_merge_downloads_sorts_mixed_null_accounts(tmp_path):
    t0 = dt.datetime(2026, 7, 1, tzinfo=dt.UTC)
    by_id = {
        "match_id": 900,
        "account_id": None,
        "player": None,
        "hero_id": None,
        "rank": None,
        "region": None,
        "downloaded_at": t0,
    }
    tracked = {
        "match_id": 900,
        "account_id": 11,
        "player": "someone",
        "hero_id": 52,
        "rank": 3,
        "region": "Asia",
        "downloaded_at": t0,
    }

    merged = players._merge_downloads(tmp_path, [by_id, tracked])

    assert [r["account_id"] for r in merged] == [11, None]


def test_write_player_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(players, "match_metadata", lambda mid: _match_json(mid))

    t0 = dt.datetime(2026, 7, 1, tzinfo=dt.UTC)
    rows = [
        {
            "match_id": 900,
            "account_id": 11,
            "player": "someone",
            "hero_id": 52,
            "rank": 3,
            "region": "Asia",
            "downloaded_at": t0,
        }
    ]

    counts = players.write_player_tables(rows, out_dir=tmp_path / "pq")

    assert counts["matches"] == 1
    assert counts["players"] == 1
    assert counts["downloads"] == 1

    downloads = pl.read_parquet(tmp_path / "pq" / "downloads.parquet")

    assert downloads["player"][0] == "someone"
    assert downloads["region"][0] == "Asia"

    matches = queries.scan("matches", tmp_path / "pq").collect()

    assert matches["match_id"][0] == 900


def test_write_player_tables_rebuilds_drifted_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(players, "match_metadata", lambda mid: _match_json(mid))

    row = {
        "match_id": 900,
        "account_id": 11,
        "player": "someone",
        "hero_id": 52,
        "rank": 3,
        "region": "Asia",
        "downloaded_at": dt.datetime(2026, 7, 1, tzinfo=dt.UTC),
    }
    out = tmp_path / "pq"
    players.write_player_tables([row], out_dir=out)

    target = next((out / "players").glob("*.parquet"))
    pl.read_parquet(target).drop("party").write_parquet(target)

    assert export.schema_drift(out) is not None

    counts = players.write_player_tables([], out_dir=out)

    assert export.schema_drift(out) is None
    assert counts["matches"] == 1
    assert "party" in pl.read_parquet_schema(target)


def test_write_player_tables_keeps_earliest_download(tmp_path, monkeypatch):
    monkeypatch.setattr(players, "match_metadata", lambda mid: _match_json(mid))

    t0 = dt.datetime(2026, 7, 1, tzinfo=dt.UTC)
    first = {
        "match_id": 900,
        "account_id": 11,
        "player": "someone",
        "hero_id": 52,
        "rank": 3,
        "region": "Asia",
        "downloaded_at": t0,
    }
    out = tmp_path / "pq"

    players.write_player_tables([first], out_dir=out)

    redownloaded = dict(first, downloaded_at=t0 + dt.timedelta(days=3), rank=7)
    second = dict(first, match_id=901, rank=1, downloaded_at=t0 + dt.timedelta(days=1))

    counts = players.write_player_tables([redownloaded, second], out_dir=out)

    assert counts["matches"] == 2
    assert counts["downloads"] == 2

    downloads = pl.read_parquet(out / "downloads.parquet").sort("match_id")

    assert downloads["downloaded_at"].to_list() == [t0, t0 + dt.timedelta(days=1)]
    assert downloads["rank"].to_list() == [3, 1]


FIRST_GAME_DAY = dt.datetime.fromtimestamp(1783000000, dt.UTC).date()


@pytest.fixture
def tracked_pq(tmp_path, monkeypatch):
    data = {
        900: _match_json(900, account_id=11),
        901: _match_json(901, account_id=22, hero_id=1),
    }
    data[901]["start_time"] = data[901]["start_time"] + 5 * 86400
    monkeypatch.setattr(players, "match_metadata", lambda mid: data[mid])

    t0 = dt.datetime(2026, 7, 1, tzinfo=dt.UTC)
    rows = [
        {
            "match_id": 900,
            "account_id": 11,
            "player": "Someone",
            "hero_id": 52,
            "rank": 1,
            "region": "NAmerica",
            "downloaded_at": t0,
        },
        {
            "match_id": 901,
            "account_id": 22,
            "player": "other",
            "hero_id": 1,
            "rank": 2,
            "region": "Europe",
            "downloaded_at": t0,
        },
    ]
    out = tmp_path / "pq"
    players.write_player_tables(rows, out_dir=out)

    return out


def test_tracked_player_games_joins_and_local_day(tracked_pq):
    df = players.tracked_player_games(parquet_dir=tracked_pq, tz="UTC").collect().sort("match_id")

    assert df["player"].to_list() == ["Someone", "other"]
    assert df["hero"][0] == "Mirage"
    assert df["won"].to_list() == [True, True]
    assert df["day"][0] == FIRST_GAME_DAY


def test_tracked_player_games_names_case_insensitive(tracked_pq):
    df = players.tracked_player_games(["someone"], parquet_dir=tracked_pq, tz="UTC").collect()

    assert df["player"].to_list() == ["Someone"]


def test_tracked_player_games_filters_hero(tracked_pq):
    df = players.tracked_player_games(hero="Mirage", parquet_dir=tracked_pq, tz="UTC").collect()

    assert df["match_id"].to_list() == [900]


def test_tracked_player_games_since(tracked_pq):
    since = FIRST_GAME_DAY + dt.timedelta(days=1)
    df = players.tracked_player_games(since=since, parquet_dir=tracked_pq, tz="UTC").collect()

    assert df["match_id"].to_list() == [901]


def test_write_player_tables_skips_already_built(tmp_path, monkeypatch):
    calls = []

    def fake_meta(mid):
        calls.append(mid)
        return _match_json(mid)

    monkeypatch.setattr(players, "match_metadata", fake_meta)

    t0 = dt.datetime(2026, 7, 1, tzinfo=dt.UTC)
    base = {
        "account_id": 11,
        "player": "someone",
        "hero_id": 52,
        "rank": 3,
        "region": "Asia",
        "downloaded_at": t0,
    }
    out = tmp_path / "pq"

    players.write_player_tables([dict(base, match_id=900)], out_dir=out)
    calls.clear()

    counts = players.write_player_tables([dict(base, match_id=901)], out_dir=out)

    assert calls == [901]

    matches = queries.scan("matches", out).collect()

    assert sorted(matches["match_id"].to_list()) == [900, 901]
    assert matches["match_id"].n_unique() == matches.height
    assert counts["matches"] == 2
