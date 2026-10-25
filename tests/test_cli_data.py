import argparse
import datetime as dt
import re
import unicodedata
import zoneinfo

import polars as pl
import pytest
from cli_helpers import run_main, write_cache_entry

from deadlock_matches import (
    export,
    extract,
    players,
)
from deadlock_matches.assets import (
    history,
    snapshots,
    store,
)
from deadlock_matches.cli import data
from deadlock_matches.cli.main import (
    main,
)
from deadlock_matches.extract import STEAM64_BASE, pb


@pytest.fixture(autouse=True)
def no_installed_client(monkeypatch):
    monkeypatch.setattr(extract, "installed_client_version", lambda cache_dir=None: None)


def display_width(text):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def _heal_args(tmp_path):
    return argparse.Namespace(
        parquet=str(tmp_path / "pq"),
        cache=str(tmp_path / "cache"),
        archive=str(tmp_path / "arc"),
    )


def test_heal_assets_skips_without_a_newer_build(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(data, "_extend_asset_history", lambda: calls.append(1) or True)
    monkeypatch.setattr(extract, "installed_client_version", lambda cache_dir=None: 6600)
    monkeypatch.setattr(history, "eras", lambda path: [("2026-06-01T00:00:00", 6600)])
    (tmp_path / "pq").mkdir()

    data.heal_assets(_heal_args(tmp_path), [42], ())

    assert calls == []
    assert export.read_stamp(tmp_path / "pq") == {}
    assert capsys.readouterr().out == ""


def test_heal_assets_backfills_once_per_build(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(data, "_extend_asset_history", lambda: calls.append(1) or True)
    monkeypatch.setattr(extract, "installed_client_version", lambda cache_dir=None: 6700)
    monkeypatch.setattr(history, "eras", lambda path: [("2026-06-01T00:00:00", 6600)])
    (tmp_path / "pq").mkdir()

    data.heal_assets(_heal_args(tmp_path), [42], ())
    data.heal_assets(_heal_args(tmp_path), [42], ())

    assert len(calls) == 1
    assert export.read_stamp(tmp_path / "pq")["checked_build"] == 6700

    out = capsys.readouterr().out

    assert out.count("Game updated, extending the asset history to build 6700") == 1


def test_heal_assets_offline_reports_the_retry(tmp_path, monkeypatch, capsys):
    def boom():
        raise OSError("offline")

    monkeypatch.setattr(data, "_extend_asset_history", boom)
    monkeypatch.setattr(extract, "installed_client_version", lambda cache_dir=None: 6700)
    monkeypatch.setattr(history, "eras", lambda path: [("2026-06-01T00:00:00", 6600)])
    (tmp_path / "pq").mkdir()

    data.heal_assets(_heal_args(tmp_path), [42], ())

    assert export.read_stamp(tmp_path / "pq") == {}

    out = capsys.readouterr().out

    assert "Game updated, extending the asset history to build 6700" in out
    assert "Asset update failed, the next sync retries" in out


def _stub_history_builders(monkeypatch, tmp_path, builder):
    monkeypatch.setattr(snapshots, "client_version_dates", lambda **kw: {})
    monkeypatch.setattr(history, "eras", lambda path: [("2026-06-01T00:00:00", 6600)])
    monkeypatch.setattr(store, "read_path", lambda name: tmp_path / name)
    monkeypatch.setattr(store, "write_path", lambda name: tmp_path / name)

    for _name, _path, fn in data.HISTORY_BUILDERS:
        monkeypatch.setattr(snapshots, fn, builder)


def test_extend_asset_history_reports_progress_per_table(tmp_path, monkeypatch, capsys):
    def builder(*, path, resume_from, progress, full):
        progress(1, 2, [])
        progress(2, 2, [])

        return 2

    _stub_history_builders(monkeypatch, tmp_path, builder)

    assert data._extend_asset_history() is True

    out = capsys.readouterr().out

    for name, _path, _fn in data.HISTORY_BUILDERS:
        assert f"{name:<9} 2/2 builds" in out
        assert f"{name:<9} 1 -> 2 eras" in out


def test_extend_asset_history_reports_skipped_builds(tmp_path, monkeypatch, capsys):
    def builder(*, path, resume_from, progress, full):
        progress(1, 1, [6665])

        return 1

    _stub_history_builders(monkeypatch, tmp_path, builder)

    assert data._extend_asset_history() is False

    out = capsys.readouterr().out

    assert "no asset data for client build 6665, skipped" in out


def test_extend_asset_history_ends_the_progress_line_on_failure(tmp_path, monkeypatch, capsys):
    def builder(*, path, resume_from, progress, full):
        progress(1, 2, [])

        raise OSError("offline")

    _stub_history_builders(monkeypatch, tmp_path, builder)
    monkeypatch.setattr(extract, "installed_client_version", lambda cache_dir=None: 6700)
    (tmp_path / "pq").mkdir()

    data.heal_assets(_heal_args(tmp_path), [42], ())

    out = capsys.readouterr().out

    assert "\nAsset update failed, the next sync retries" in out
    assert export.read_stamp(tmp_path / "pq") == {}


def test_heal_assets_reexports_past_the_old_horizon(tmp_path, monkeypatch, capsys):
    pq = tmp_path / "pq"
    pq.mkdir()
    export.update_stamp(
        pq,
        logic_version=export.EXPORT_LOGIC_VERSION,
        asset_horizon="2026-06-01T00:00:00",
    )
    pl.DataFrame(
        {
            "match_id": [1, 2],
            "start_time": [
                dt.datetime(2026, 5, 15, tzinfo=dt.UTC),
                dt.datetime(2026, 6, 15, tzinfo=dt.UTC),
            ],
        }
    ).write_parquet(pq / "matches.parquet")
    monkeypatch.setattr(
        history,
        "eras",
        lambda path: [("2026-06-01T00:00:00", 6600), ("2026-06-10T00:00:00", 6700)],
    )
    healed = []
    monkeypatch.setattr(export, "reexport_matches", lambda ids, *a: healed.extend(ids))
    refreshed = []
    monkeypatch.setattr(export, "refresh_asset_tables", lambda out: refreshed.append(out))

    data.heal_assets(_heal_args(tmp_path), [42], ())

    assert healed == [2]
    assert refreshed
    assert export.read_stamp(pq)["asset_horizon"] == "2026-06-10T00:00:00"
    assert "Updating 1 match with the new item data" in capsys.readouterr().out


def test_heal_assets_no_reexport_when_horizon_is_current(tmp_path, monkeypatch):
    pq = tmp_path / "pq"
    pq.mkdir()
    export.update_stamp(
        pq,
        logic_version=export.EXPORT_LOGIC_VERSION,
        asset_horizon="2026-06-10T00:00:00",
    )
    monkeypatch.setattr(
        history,
        "eras",
        lambda path: [("2026-06-10T00:00:00", 6700)],
    )

    def boom(*a):
        raise AssertionError("reexport should not run")

    monkeypatch.setattr(export, "reexport_matches", boom)
    monkeypatch.setattr(export, "refresh_asset_tables", boom)

    data.heal_assets(_heal_args(tmp_path), [42], ())

    assert export.read_stamp(pq)["asset_horizon"] == "2026-06-10T00:00:00"


def test_download_command_defaults_to_the_watchlist(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[players.Mirage]\nsomeplayer = 22\nladderer = 11\n")

    monkeypatch.setattr(
        players,
        "ladder_positions",
        lambda hero_id: {11: {"name": "lead", "rank": 1, "region": "Asia"}},
    )

    seen = {}

    def fake_download(tracked, hero_id, n, archive_dir, **modes):
        seen["tracked"] = tracked
        seen["n"] = n
        seen["modes"] = modes

        return []

    monkeypatch.setattr(players, "download_matches", fake_download)
    monkeypatch.setattr(
        players, "write_player_tables", lambda rows, out_dir, exclude, archive_dir: {"matches": 0}
    )

    main(["download", "--hero", "Mirage", "--games", "3", "--out", str(tmp_path)], config=cfg)

    assert [t["account_id"] for t in seen["tracked"]] == [22, 11]
    assert seen["tracked"][1]["rank"] == 1
    assert seen["tracked"][1]["name"] == "ladderer"
    assert seen["n"] == 3
    assert seen["modes"] == {"match_mode": 4, "game_mode": 1}

    out = capsys.readouterr().out

    assert "someplayer" in out
    assert "tracked" in out
    assert "rank 1" in out


def test_download_command_account_fills_names_from_the_ladder(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "config.toml"
    cfg.write_text("")

    monkeypatch.setattr(
        players,
        "ladder_positions",
        lambda hero_id: {11: {"name": "lead", "rank": 4, "region": "Asia"}},
    )
    seen = {}

    def fake_download(tracked, hero_id, n, archive_dir, **modes):
        seen["tracked"] = tracked

        return []

    monkeypatch.setattr(players, "download_matches", fake_download)
    monkeypatch.setattr(
        players, "write_player_tables", lambda rows, out_dir, exclude, archive_dir: {"matches": 0}
    )

    main(["download", "--hero", "Mirage", "--account", "11,22", "--out", str(tmp_path)], config=cfg)

    assert seen["tracked"][0]["name"] == "lead"
    assert seen["tracked"][0]["rank"] == 4
    assert seen["tracked"][1]["name"] == "22"

    out = capsys.readouterr().out

    assert "rank 4" in out
    assert "picked" in out


def test_download_command_without_targets_prints_guidance(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "config.toml"
    cfg.write_text("")

    def boom(*args, **kwargs):
        msg = "nothing should download"
        raise AssertionError(msg)

    monkeypatch.setattr(players, "download_matches", boom)
    monkeypatch.setattr(players, "write_player_tables", boom)

    main(["download", "--hero", "Mirage", "--out", str(tmp_path)], config=cfg)

    out = capsys.readouterr().out

    assert "No players tracked for Mirage" in out
    assert "deadlock leaderboard" in out
    assert "config.toml" in out


def _sync_config(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text('timezone = "Asia/Manila"\n[accounts]\nmain = 42\nalt1 = 43\n')

    return cfg


def _sync_api_mocks(monkeypatch, seen):
    history = {
        42: [
            {"match_id": 100, "start_time": 1_700_000_000},
            {"match_id": 101, "start_time": 1_700_100_000},
        ],
        43: [
            {"match_id": 101, "start_time": 1_700_100_000},
            {"match_id": 200, "start_time": 1_700_200_000},
        ],
    }
    monkeypatch.setattr(players, "match_history", lambda account_id: history[account_id])
    monkeypatch.setattr(extract, "archived_match_ids", lambda archive_dir: {100})

    def fake_download(match_ids, archive_dir):
        seen["ids"] = list(match_ids)

        return len(list(seen["ids"])), [], []

    monkeypatch.setattr(players, "download_metadata", fake_download)

    def fake_export_new(archive_dir, out_dir, exclude, accounts):
        seen["accounts"] = sorted(accounts)

        return export.ExportResult(counts={"matches": 2}, decoded=2, skipped=0)

    monkeypatch.setattr(export, "export_new", fake_export_new)


def test_sync_api_downloads_missing_matches_into_the_archive(tmp_path, monkeypatch, capsys):
    cfg = _sync_config(tmp_path)
    seen = {}
    _sync_api_mocks(monkeypatch, seen)

    main(["--parquet", str(tmp_path), "sync", "--source", "api"], config=cfg)

    assert seen["ids"] == [101, 200]
    assert seen["accounts"] == [42, 43]

    out = capsys.readouterr().out

    assert "3 games in the API" in out
    assert "1 already archived" in out
    assert "2 to download" in out


def test_sync_api_reports_rate_limited_matches_separately(tmp_path, monkeypatch, capsys):
    cfg = _sync_config(tmp_path)
    seen = {}
    _sync_api_mocks(monkeypatch, seen)
    monkeypatch.setattr(players, "download_metadata", lambda match_ids, archive_dir: (1, [], [200]))

    main(["--parquet", str(tmp_path), "sync", "--source", "api"], config=cfg)

    out = capsys.readouterr().out

    assert "1 deferred by the API rate limit" in out
    assert "run sync again later to continue" in out
    assert "not available" not in out


def test_sync_api_singular_counts_read_grammatically(tmp_path, monkeypatch, capsys):
    cfg = _sync_config(tmp_path)
    monkeypatch.setattr(
        players,
        "match_history",
        lambda account_id: [{"match_id": 500, "start_time": 1_700_000_000}],
    )
    monkeypatch.setattr(extract, "archived_match_ids", lambda archive_dir: set())
    monkeypatch.setattr(players, "download_metadata", lambda match_ids, archive_dir: (1, [], []))
    monkeypatch.setattr(
        export,
        "export_new",
        lambda archive_dir, out_dir, exclude, accounts: export.ExportResult(
            counts={"matches": 1}, decoded=1, skipped=0
        ),
    )

    main(["--parquet", str(tmp_path), "sync", "--source", "api"], config=cfg)

    out = capsys.readouterr().out

    assert "1 game in the API" in out
    assert "Downloaded 1 match into the archive" in out
    assert "1 games" not in out
    assert "1 matches" not in out


def test_sync_api_dry_run_skips_the_download(tmp_path, monkeypatch, capsys):
    cfg = _sync_config(tmp_path)
    seen = {}
    _sync_api_mocks(monkeypatch, seen)

    main(["--parquet", str(tmp_path), "sync", "--source", "api", "--dry-run"], config=cfg)

    assert "ids" not in seen

    out = capsys.readouterr().out

    assert "2 to download" in out


def test_sync_local_exports_the_config_accounts(tmp_path, monkeypatch, capsys):
    cfg = _sync_config(tmp_path)
    seen = {}
    monkeypatch.setattr(data, "sync_archive", lambda cache, archive: 0)

    def fake_export_new(archive_dir, out_dir, exclude, accounts):
        seen["accounts"] = sorted(accounts)

        return export.ExportResult(counts={"matches": 5}, decoded=5, skipped=0)

    monkeypatch.setattr(export, "export_new", fake_export_new)

    main(["--parquet", str(tmp_path), "sync"], config=cfg)

    assert seen["accounts"] == [42, 43]


def test_sync_local_reports_a_single_new_match(tmp_path, monkeypatch, capsys):
    cfg = _sync_config(tmp_path)
    monkeypatch.setattr(data, "sync_archive", lambda cache, archive: 0)
    monkeypatch.setattr(
        export,
        "export_new",
        lambda archive_dir, out_dir, exclude, accounts: export.ExportResult(
            counts={"matches": 1}, decoded=1, skipped=813
        ),
    )

    main(["--parquet", str(tmp_path), "sync"], config=cfg)

    assert "Exported 1 new match and skipped 813 already exported" in capsys.readouterr().out


def test_sync_local_pluralizes_several_new_matches(tmp_path, monkeypatch, capsys):
    cfg = _sync_config(tmp_path)
    monkeypatch.setattr(data, "sync_archive", lambda cache, archive: 0)
    monkeypatch.setattr(
        export,
        "export_new",
        lambda archive_dir, out_dir, exclude, accounts: export.ExportResult(
            counts={"matches": 3}, decoded=3, skipped=800
        ),
    )

    main(["--parquet", str(tmp_path), "sync"], config=cfg)

    assert "Exported 3 new matches and skipped 800 already exported" in capsys.readouterr().out


def test_sync_refuses_an_account_not_in_config(tmp_path, monkeypatch, capsys):
    cfg = _sync_config(tmp_path)
    monkeypatch.setattr(data, "sync_archive", lambda cache, archive: 0)

    main(["--parquet", str(tmp_path), "sync", "--account", "999"], config=cfg)

    out = capsys.readouterr().out

    assert "not your accounts" in out
    assert "999" in out


def test_download_command_unknown_hero(tmp_path, capsys):
    main(["download", "--hero", "Nobody", "--out", str(tmp_path)], config=tmp_path / "none.json")

    assert "Unknown hero" in capsys.readouterr().out


def test_download_command_by_match_id(tmp_path, monkeypatch, capsys):
    seen = {}

    def fake_by_id(match_ids, archive_dir):
        seen["ids"] = list(match_ids)

        return [{"match_id": m} for m in match_ids]

    monkeypatch.setattr(players, "matches_by_id", fake_by_id)
    monkeypatch.setattr(
        players,
        "write_player_tables",
        lambda rows, out_dir, exclude, archive_dir: {"matches": len(rows)},
    )

    main(["download", "--match", "900,901", "--out", str(tmp_path)], config=tmp_path / "none.json")

    assert seen["ids"] == [900, 901]

    out = capsys.readouterr().out

    assert "Downloading 2 match ID(s), got 2" in out


def test_download_command_by_account_skips_leaderboard(tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError("top_players should not be called with --account")

    monkeypatch.setattr(players, "top_players", boom)

    seen = {}

    def fake_download(tracked, hero_id, n, archive_dir, **modes):
        seen["tracked"] = tracked

        return []

    monkeypatch.setattr(players, "download_matches", fake_download)
    monkeypatch.setattr(
        players, "write_player_tables", lambda rows, out_dir, exclude, archive_dir: {"matches": 0}
    )

    main(
        ["download", "--hero", "Mirage", "--account", "77,88", "--out", str(tmp_path)],
        config=tmp_path / "none.json",
    )

    assert [t["account_id"] for t in seen["tracked"]] == [77, 88]


def test_download_command_needs_hero_or_match(tmp_path, capsys):
    main(["download", "--account", "77", "--out", str(tmp_path)], config=tmp_path / "none.json")

    assert "needs --hero" in capsys.readouterr().out


def test_leaderboard_command_lists_players_and_match_ids(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[players.Mirage]\nfriend = 22\n")

    monkeypatch.setattr(
        players,
        "top_players",
        lambda hero_id, limit: [
            {"account_id": 11, "name": "lead", "rank": 1, "region": "Asia"},
            {"account_id": 12, "name": "小曦不是小兮", "rank": 1, "region": "Asia"},
            {"account_id": 13, "name": "스노우맨", "rank": 2, "region": "Asia"},
        ],
    )
    monkeypatch.setattr(
        players,
        "recent_hero_matches",
        lambda account_id, hero_id, n, **modes: [
            {
                "match_id": 5000 + account_id,
                "start_time": 1783000000,
                "match_result": 0,
                "player_team": 0,
                "player_kills": 10,
                "player_deaths": 2,
                "player_assists": 8,
            }
        ],
    )

    main(["leaderboard", "--hero", "Mirage", "--matches", "1"], config=cfg)

    out = capsys.readouterr().out

    assert "lead" in out
    assert "小曦不是小兮" in out
    assert "스노우맨" in out
    assert "11" in out
    assert "rank 1" in out
    assert "friend" in out
    assert "tracked" in out
    assert "5011" in out
    assert "5022" in out
    assert "win" in out
    assert "10/2/8" in out

    rows = [
        line
        for line in out.splitlines()
        if line.startswith("  ") and ("rank " in line or line.endswith("tracked"))
    ]
    account_starts = []

    for line in rows:
        match = re.search(r"\d+", line)
        assert match is not None
        account = match.group()
        account_starts.append(display_width(line[: line.index(account)]))

    assert len(set(account_starts)) == 1


def test_leaderboard_command_prints_paste_ready_lines(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[players.Mirage]\nfriend = 22\n")

    monkeypatch.setattr(
        players,
        "top_players",
        lambda hero_id, limit: [
            {"account_id": 11, "name": "lead", "rank": 1, "region": "Asia"},
            {"account_id": 22, "name": "friend", "rank": 3, "region": "Europe"},
            {"account_id": 33, "name": "señor", "rank": 4, "region": "SAmerica"},
        ],
    )

    main(["leaderboard", "--hero", "Mirage"], config=cfg)

    out = capsys.readouterr().out

    assert 'deadlock download --hero "Mirage"' in out
    assert '[players."Mirage"]' in out

    block = out.split('[players."Mirage"]')[1]

    assert '"lead" = 11' in block
    assert '"señor" = 33' in block
    assert "22" not in block


@pytest.mark.parametrize(
    ("mode", "flag"),
    [
        ((extract.MATCH_MODE_STANDARD, extract.GAME_MODE_NORMAL, False), "--standard"),
        ((extract.MATCH_MODE_RANKED, extract.GAME_MODE_NORMAL, None), "--ranked"),
        ((extract.MATCH_MODE_PLACEMENT, extract.GAME_MODE_NORMAL, None), "--placement"),
        (
            (extract.MATCH_MODE_STANDARD, extract.GAME_MODE_STREET_BRAWL, None),
            "--street-brawl",
        ),
        (
            (extract.MATCH_MODE_PRIVATE_LOBBY, extract.GAME_MODE_NORMAL, None),
            "--private-lobby",
        ),
    ],
)
def test_no_pool_hint_keeps_selected_mode_in_download_command(mode, flag):
    tracked_hint = data.no_pool_hint("Mirage", tracked_in_config=True, mode=mode)
    setup_hint = data.no_pool_hint("Mirage", tracked_in_config=False, mode=mode)

    assert f'deadlock download --hero "Mirage" {flag}' in tracked_hint
    assert f'deadlock leaderboard --hero "Mirage" {flag}' in setup_hint
    assert f'deadlock download --hero "Mirage" {flag}' in setup_hint


def test_history_since_filters_matches(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, start_time=1783000000)
    write_cache_entry(cache, match_id=101, start_time=1783000000 + 5 * 86400)

    cutoff = (
        dt.datetime.fromtimestamp(1783000000 + 5 * 86400, dt.UTC)
        .astimezone(zoneinfo.ZoneInfo("America/Chicago"))
        .date()
    )

    run_main(tmp_path, "history", "--since", cutoff.isoformat())

    lines = [line.rstrip() for line in capsys.readouterr().out.splitlines()]

    assert any(line.endswith("101") for line in lines)
    assert not any(line.endswith("100") for line in lines)


def test_history_account_filter(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    run_main(tmp_path, "history", "--account", "42")

    lines = [line.rstrip() for line in capsys.readouterr().out.splitlines()]

    assert any(line.endswith("100") for line in lines)

    run_main(tmp_path, "history", "--account", "99")

    assert "No games found for accounts 99" in capsys.readouterr().out


def test_history_empty_mode_names_the_mode(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    run_main(tmp_path, "history", "--placement")

    out = capsys.readouterr().out

    assert "No New Player Placement games for accounts you" in out
    assert "cache" not in out

    run_main(tmp_path, "history", "--street-brawl", "--days", "3")

    assert "No Street Brawl games for accounts you in the last 3 days" in capsys.readouterr().out

    run_main(tmp_path, "history", "--since", "2100-01-01")

    assert "No Ranked games for accounts you since 2100-01-01" in capsys.readouterr().out


def test_history_without_an_archive_still_blames_the_cache(capsys, tmp_path):
    run_main(tmp_path, "history")

    assert "No match metadata found in cache" in capsys.readouterr().out


def test_history_defaults_to_matchmaking_and_can_select_private(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)
    write_cache_entry(
        cache,
        match_id=101,
        match_mode=pb.k_ECitadelMatchMode_PrivateLobby,
    )

    run_main(tmp_path, "history")
    normal = capsys.readouterr().out
    run_main(tmp_path, "history", "--private-lobby")
    private = capsys.readouterr().out

    assert any(line.rstrip().endswith("100") for line in normal.splitlines())
    assert not any(line.rstrip().endswith("101") for line in normal.splitlines())
    assert any(line.rstrip().endswith("101") for line in private.splitlines())
    assert not any(line.rstrip().endswith("100") for line in private.splitlines())


def test_history_lists_one_line_per_game(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000), (600, 5000)])

    cfg = tmp_path / "config.toml"
    cfg.write_text('timezone = "America/Chicago"\n[accounts]\nmain = 42\n')

    base = ["--cache", str(cache), "--archive", str(tmp_path / "arc")]
    base += ["--parquet", str(tmp_path / "pq")]
    main([*base, "history"], config=cfg)

    out = capsys.readouterr().out

    assert re.search(
        r"Day\s+Time\s+Account\s+Hero\s+Result\s+K/D/A\s+Souls\s+Damage\s+Match ID", out
    )
    assert re.search(
        r"\d{4}-\d\d-\d\d\s+\d\d:\d\d\s+main\s+Mirage\s+win\s+5/2/8\s+5,000\s+\S+\s+100", out
    )
    assert "42" not in out
    assert "77" not in out


def test_history_prints_day_once_per_local_day(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, start_time=1783000000)
    write_cache_entry(cache, match_id=101, start_time=1783000000 + 3600)
    write_cache_entry(cache, match_id=102, start_time=1783000000 + 2 * 86400)

    run_main(tmp_path, "history")

    out = capsys.readouterr().out
    tz = zoneinfo.ZoneInfo("America/Chicago")
    first_day = dt.datetime.fromtimestamp(1783000000, dt.UTC).astimezone(tz).date()
    later_day = dt.datetime.fromtimestamp(1783000000 + 2 * 86400, dt.UTC).astimezone(tz).date()

    assert out.count(first_day.isoformat()) == 1
    assert out.count(later_day.isoformat()) == 1

    line_101 = next(line for line in out.splitlines() if line.rstrip().endswith("101"))

    assert first_day.isoformat() not in line_101


def test_history_without_account_prints_hint(capsys, tmp_path):
    run_main(tmp_path, "history", accounts=None)

    assert "--account" in capsys.readouterr().out


def test_config_command_shows_path_and_settings(capsys, tmp_path):
    run_main(tmp_path, "config", accounts="main = 42")

    out = capsys.readouterr().out

    assert "config.toml" in out
    assert re.search(r"main\s+42", out)
    assert "America/Chicago" in out


def test_config_command_shows_no_excluded_tables_when_empty(capsys, tmp_path):
    run_main(tmp_path, "config")

    assert "Excluded tables: none" in capsys.readouterr().out


def test_config_command_lists_excluded_tables(capsys, tmp_path):
    run_main(tmp_path, "config", accounts="", extra='exclude = ["movement"]')

    out = capsys.readouterr().out

    assert "Excluded tables: movement" in out
    assert "none" not in out.split("Excluded tables:")[1]


def test_config_command_reports_missing_file(capsys):
    main(["config"], config="none.json")

    assert "not created yet" in capsys.readouterr().out


def test_config_edit_creates_and_opens_the_file(capsys, tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(data, "_launch_editor", opened.append)
    cfg = tmp_path / "config.toml"

    main(["config", "--edit"], config=cfg)

    assert opened == [cfg]
    assert cfg.exists()
    assert "Opened" in capsys.readouterr().out


def test_skill_command_prints_install_path(capsys, tmp_path):
    main(["skill", "path", "--dir", str(tmp_path / "skills")], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "skills/deadlock-matches/SKILL.md" in out


@pytest.mark.parametrize(
    ("agent", "directory"),
    [
        ("claude", ".claude"),
        ("codex", ".codex"),
        ("gemini", ".gemini"),
    ],
)
def test_skill_command_prints_agent_install_path(agent, directory, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(data.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("CODEX_HOME", raising=False)

    main(["skill", "path", "--agent", agent], config=tmp_path / "none.json")

    assert capsys.readouterr().out.strip() == f"~/{directory}/skills/deadlock-matches/SKILL.md"


def test_skill_command_uses_codex_home(capsys, tmp_path, monkeypatch):
    codex_home = tmp_path / "codex-home"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    main(["skill", "path", "--agent", "codex"], config=tmp_path / "none.json")

    assert capsys.readouterr().out.strip().endswith("codex-home/skills/deadlock-matches/SKILL.md")


def test_skill_command_empty_codex_home_falls_back(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(data.Path, "home", lambda: tmp_path)
    monkeypatch.setenv("CODEX_HOME", "")

    main(["skill", "path", "--agent", "codex"], config=tmp_path / "none.json")

    assert capsys.readouterr().out.strip() == "~/.codex/skills/deadlock-matches/SKILL.md"


def test_skill_command_installs_bundled_agent_skill(capsys, tmp_path):
    root = tmp_path / "skills"

    main(["skill", "install", "--dir", str(root)], config=tmp_path / "none.json")

    target = root / "deadlock-matches" / "SKILL.md"
    references = root / "deadlock-matches" / "references"
    out = capsys.readouterr().out

    assert target.exists()
    assert "Deadlock match metadata" in target.read_text()
    assert (references / "index.md").exists()
    assert (references / "patterns" / "stats.md").exists()
    assert (references / "contracts" / "queries.md").exists()
    assert (
        "Take the last sample, never `max()`" in (references / "patterns" / "stats.md").read_text()
    )
    assert "skills/deadlock-matches/SKILL.md" in out


@pytest.mark.parametrize("agent", ["claude", "codex", "gemini"])
def test_skill_command_installs_for_each_agent(agent, capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(data.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("CODEX_HOME", raising=False)

    main(["skill", "install", "--agent", agent], config=tmp_path / "none.json")

    target = tmp_path / f".{agent}" / "skills" / "deadlock-matches"
    assert (target / "SKILL.md").exists()
    assert (target / "references" / "index.md").exists()


def test_skill_command_refuses_to_overwrite_without_force(capsys, tmp_path):
    target = tmp_path / "skills" / "deadlock-matches" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("local edit")

    main(["skill", "install", "--dir", str(tmp_path / "skills")], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "already exists" in out
    assert target.read_text() == "local edit"


def test_skill_command_force_replaces_existing_skill(capsys, tmp_path):
    target = tmp_path / "skills" / "deadlock-matches" / "SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("local edit")

    main(
        ["skill", "install", "--dir", str(tmp_path / "skills"), "--force"],
        config=tmp_path / "none.json",
    )

    assert "Installed" in capsys.readouterr().out
    assert "Deadlock match metadata" in target.read_text()


def test_skill_command_prints_bundled_skill(capsys, tmp_path):
    main(["skill", "print"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "Deadlock match metadata" in out
    assert "deadlock history" in out


def test_default_command_lists_last_ten_games(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()

    for n in range(12):
        write_cache_entry(cache, match_id=100 + n, start_time=1783000000 + n * 3600)

    run_main(tmp_path)

    lines = [line.rstrip() for line in capsys.readouterr().out.splitlines()]
    listed = [line for line in lines if re.search(r"\d{3}$", line)]

    assert len(listed) == 10
    assert listed[0].endswith("102")
    assert listed[-1].endswith("111")

    run_main(tmp_path, "history", "--days", "1")

    lines = [line.rstrip() for line in capsys.readouterr().out.splitlines()]

    assert sum(1 for line in lines if re.search(r"\d{3}$", line)) == 12


def test_assets_subcommand_reports_counts(monkeypatch, capsys):
    monkeypatch.setattr(snapshots, "refresh_heroes", lambda *a, **k: 57)
    monkeypatch.setattr(snapshots, "refresh_items", lambda *a, **k: 251)
    monkeypatch.setattr(snapshots, "refresh_abilities", lambda *a, **k: 0)
    monkeypatch.setattr(snapshots, "refresh_skill_rating", lambda *a, **k: 0)
    monkeypatch.setattr(snapshots, "refresh_accolades", lambda *a, **k: 0)
    monkeypatch.setattr(snapshots, "refresh_statues", lambda *a, **k: 0)
    monkeypatch.setattr(snapshots, "history_lags", lambda **k: [])
    monkeypatch.setattr(
        snapshots, "client_version_dates", lambda **k: {6640: "2026-07-25T11:19:46"}
    )
    monkeypatch.setattr(extract, "installed_client_version", lambda *a, **k: None)

    data.refresh_assets(argparse.Namespace())

    out = capsys.readouterr().out

    assert "57 heroes" in out
    assert "251 upgrade items" in out


def test_sync_archive_reports_count_and_path(tmp_path, capsys):
    cache = tmp_path / "cache"
    cache.mkdir()
    arc = tmp_path / "arc"
    arc.mkdir()
    (arc / "123_1.bin").write_bytes(b"x")
    (arc / "124_0.bin").write_bytes(b"x")
    (arc / "124_9.bin").write_bytes(b"x")

    assert data.sync_archive(cache, arc) == 0

    out = capsys.readouterr().out

    assert "Archive: 2 matches (no new)" in out
    assert data._tilde(arc) in out
    assert not (arc / "124_0.bin").exists()


def test_new_matches_trigger_parquet_rebuild(tmp_path, capsys):
    cache = tmp_path / "cache"
    cache.mkdir()
    arc = tmp_path / "arc"
    pq = tmp_path / "pq"
    cfg = tmp_path / "config.toml"
    cfg.write_text("[accounts]\nyou = 42\n")
    write_cache_entry(cache, match_id=100)
    write_cache_entry(cache, match_id=101)

    main(
        ["--cache", str(cache), "--archive", str(arc), "--parquet", str(pq), "history"], config=cfg
    )

    captured = capsys.readouterr()

    assert "Added" not in captured.out
    assert "Archive" not in captured.out
    assert "Building the tables from the archive" in captured.err
    assert (pq / "matches").is_dir()
    assert (pq / "damage").is_dir()
    assert next((pq / "matches").glob("month=*/*.parquet"), None) is not None


def test_no_new_matches_skips_rebuild(tmp_path, capsys):
    cache = tmp_path / "cache"
    cache.mkdir()
    arc = tmp_path / "arc"
    pq = tmp_path / "pq"
    cfg = tmp_path / "config.toml"
    cfg.write_text("[accounts]\nyou = 42\n")
    write_cache_entry(cache, match_id=100)

    main(
        ["--cache", str(cache), "--archive", str(arc), "--parquet", str(pq), "history"], config=cfg
    )
    capsys.readouterr()

    written = sorted(p.stat().st_mtime_ns for p in (pq / "matches").rglob("*.parquet"))

    main(
        ["--cache", str(cache), "--archive", str(arc), "--parquet", str(pq), "history"], config=cfg
    )

    assert "100" in capsys.readouterr().out
    assert sorted(p.stat().st_mtime_ns for p in (pq / "matches").rglob("*.parquet")) == written


def write_steam_tree(tmp_path, deadlock=(42,), vdf=""):
    root = tmp_path / "Steam"
    (root / "appcache/httpcache").mkdir(parents=True)
    (root / "config").mkdir()
    (root / "config/loginusers.vdf").write_text(vdf)

    for account_id in deadlock:
        (root / f"userdata/{account_id}/1422450").mkdir(parents=True)

    return root / "appcache/httpcache"


def run_accounts(tmp_path, cache, config_text=""):
    cfg = tmp_path / "config.toml"
    cfg.write_text(config_text)

    base = ["--cache", str(cache), "--archive", str(tmp_path / "arc")]
    base += ["--parquet", str(tmp_path / "pq")]
    main([*base, "accounts"], config=cfg)


def test_accounts_command_lists_logins(capsys, tmp_path):
    vdf = (
        '"users"\n{\n'
        f'\t"{42 + STEAM64_BASE}"\n\t{{\n'
        '\t\t"AccountName"\t\t"mainlogin"\n'
        '\t\t"PersonaName"\t\t"Main Guy"\n'
        '\t\t"Timestamp"\t\t"200"\n'
        "\t}\n}\n"
    )
    cache = write_steam_tree(tmp_path, deadlock=(42, 43), vdf=vdf)

    run_accounts(tmp_path, cache, "[accounts]\nmain = 42\n")

    out = capsys.readouterr().out

    assert "mainlogin" in out
    assert "Main Guy" in out
    assert "main" in out


def test_accounts_command_shows_the_local_game_span(capsys, tmp_path):
    cache = write_steam_tree(tmp_path, deadlock=(42, 43))
    write_cache_entry(cache, match_id=100, start_time=1783044000, stats=[(300, 3000)])
    write_cache_entry(cache, match_id=101, salt=2, start_time=1783684800, stats=[(300, 3000)])
    cfg = tmp_path / "config.toml"
    cfg.write_text('timezone = "America/Chicago"\n[accounts]\nmain = 42\nalt1 = 43\n')

    base = ["--cache", str(cache), "--archive", str(tmp_path / "arc")]
    base += ["--parquet", str(tmp_path / "pq")]
    main([*base, "history", "--account", "42"], config=cfg)
    capsys.readouterr()

    main([*base, "accounts"], config=cfg)

    out = capsys.readouterr().out
    played = next(line for line in out.splitlines() if line.startswith("  42 "))
    empty = next(line for line in out.splitlines() if line.startswith("  43 "))

    assert "First game" in out
    assert "Last game" in out
    assert "2026-07-02" in played
    assert "2026-07-10" in played
    assert "2026-" not in empty


def test_accounts_command_suggests_unconfigured_alts(capsys, tmp_path):
    vdf = (
        '"users"\n{\n'
        f'\t"{42 + STEAM64_BASE}"\n\t{{\n'
        '\t\t"AccountName"\t\t"mainlogin"\n'
        '\t\t"PersonaName"\t\t"Main Guy"\n'
        '\t\t"Timestamp"\t\t"200"\n'
        "\t}\n}\n"
    )
    cache = write_steam_tree(tmp_path, deadlock=(42, 43), vdf=vdf)

    run_accounts(tmp_path, cache, "[accounts]\nmain = 42\n")

    out = capsys.readouterr().out

    assert "[accounts]" in out
    assert "alt1 = 43" in out
    assert "42" not in out.split("[accounts]")[1]
    assert "mainlogin" not in out.split("[accounts]")[1]


def test_accounts_command_all_configured(capsys, tmp_path):
    cache = write_steam_tree(tmp_path, deadlock=(42,))

    run_accounts(tmp_path, cache, "[accounts]\nmain = 42\n")

    out = capsys.readouterr().out

    assert "already covers" in out
    assert "[accounts]" not in out


def test_accounts_command_without_steam(capsys, tmp_path):
    (tmp_path / "cache").mkdir()

    run_accounts(tmp_path, tmp_path / "cache")

    assert "No Steam accounts" in capsys.readouterr().out


def test_suggest_names_starts_at_main():
    assert data._suggest_names(3, []) == ["main", "alt1", "alt2"]


def test_suggest_names_skips_taken_case_insensitively():
    assert data._suggest_names(2, ["Main", "alt2"]) == ["alt1", "alt3"]


def test_accounts_command_suggests_main_when_config_empty(capsys, tmp_path):
    cache = write_steam_tree(tmp_path, deadlock=(42, 43))

    run_accounts(tmp_path, cache)

    block = capsys.readouterr().out.split("[accounts]")[1]

    assert "main = 42" in block
    assert "alt1 = 43" in block


def test_backfill_without_confirm_only_warns(monkeypatch, capsys):
    called = []
    monkeypatch.setattr(snapshots, "client_version_dates", lambda **kw: {1: "2026-01-05T00:00:00"})

    for _name, _path, fn in data.HISTORY_BUILDERS:
        monkeypatch.setattr(snapshots, fn, lambda **kw: called.append(True))

    main(["assets", "--backfill"], config="none.json")

    out = capsys.readouterr().out

    assert "--confirm" in out
    assert called == []


def test_backfill_confirm_runs_every_builder(monkeypatch, capsys):
    monkeypatch.setattr(snapshots, "client_version_dates", lambda **kw: {1: "2026-01-05T00:00:00"})

    for n, (_name, _path, fn) in enumerate(data.HISTORY_BUILDERS, start=30):
        monkeypatch.setattr(snapshots, fn, lambda n=n, **kw: n)

    main(["assets", "--backfill", "--confirm"], config="none.json")

    out = capsys.readouterr().out

    for name, _path, _fn in data.HISTORY_BUILDERS:
        assert name in out

    assert "30 eras" in out


def test_history_builders_cover_every_build_function():
    in_assets = {n for n in vars(snapshots) if n.startswith("build_") and n.endswith("_history")}
    listed = {fn for _name, _path, fn in data.HISTORY_BUILDERS}

    assert in_assets - {"build_asset_history"} == listed


def test_live_history_checks_match_history_builders():
    checks = {name for name, *_ in snapshots.LIVE_HISTORY_CHECKS}
    builders = {name for name, _path, _fn in data.HISTORY_BUILDERS}

    assert checks == builders


def _stub_refreshes(monkeypatch, builds=None, installed=None):
    for fn in (
        "refresh_heroes",
        "refresh_items",
        "refresh_abilities",
        "refresh_skill_rating",
        "refresh_accolades",
        "refresh_statues",
    ):
        monkeypatch.setattr(snapshots, fn, lambda *a, **k: 0)

    dates = builds if builds is not None else {6640: "2026-07-25T11:19:46"}
    monkeypatch.setattr(snapshots, "client_version_dates", lambda **k: dates)
    monkeypatch.setattr(extract, "installed_client_version", lambda *a, **k: installed)


def test_assets_warns_when_history_trails(monkeypatch, capsys):
    _stub_refreshes(monkeypatch)
    monkeypatch.setattr(snapshots, "history_lags", lambda **k: [("items", "2026-06-30", 6601)])

    main(["assets"], config="none.json")

    out = capsys.readouterr().out

    assert "items history is behind the live patch" in out
    assert "6601" in out
    assert "--backfill" in out


def test_assets_quiet_when_history_current(monkeypatch, capsys):
    _stub_refreshes(monkeypatch)
    monkeypatch.setattr(snapshots, "history_lags", lambda **k: [])

    main(["assets"], config="none.json")

    out = capsys.readouterr().out

    assert "behind the live patch" not in out


def test_assets_reports_live_build_behind_installed(monkeypatch, capsys):
    _stub_refreshes(
        monkeypatch,
        builds={6628: "2026-07-08T10:00:00", 6640: "2026-07-25T11:19:46"},
        installed=6642,
    )
    monkeypatch.setattr(snapshots, "history_lags", lambda **k: [])

    main(["assets"], config="none.json")

    out = capsys.readouterr().out

    assert "Live data: build 6640 (2026-07-25), behind the installed client 6642" in out


def test_assets_reports_live_build_matching_installed(monkeypatch, capsys):
    _stub_refreshes(monkeypatch, installed=6640)
    monkeypatch.setattr(snapshots, "history_lags", lambda **k: [])

    main(["assets"], config="none.json")

    out = capsys.readouterr().out

    assert "Live data: build 6640 (2026-07-25), matches the installed client" in out


def test_assets_reports_live_build_without_install(monkeypatch, capsys):
    _stub_refreshes(monkeypatch)
    monkeypatch.setattr(snapshots, "history_lags", lambda **k: [])

    main(["assets"], config="none.json")

    out = capsys.readouterr().out

    assert "Live data: build 6640 (2026-07-25)\n" in out
    assert "installed client" not in out


def test_assets_reports_live_build_ahead_of_installed(monkeypatch, capsys):
    _stub_refreshes(monkeypatch, installed=6628)
    monkeypatch.setattr(snapshots, "history_lags", lambda **k: [])

    main(["assets"], config="none.json")

    out = capsys.readouterr().out

    assert "Live data: build 6640 (2026-07-25), ahead of the installed client 6628" in out
