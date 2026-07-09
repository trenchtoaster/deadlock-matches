import argparse
import bz2
import datetime as dt
import re
import zoneinfo

import polars as pl
import pytest

from deadlock_matches import (
    abilities,
    assets,
    export,
    extract,
    heroes,
    items,
    players,
    schemas,
    timeline,
)
from deadlock_matches.cli import cards, data, performance
from deadlock_matches.cli import items as cli_items
from deadlock_matches.cli import meta as cli_meta
from deadlock_matches.cli.main import build_parser, main, parse_accounts
from deadlock_matches.extract import STEAM64_BASE, pb


def write_cache_entry(
    cache_dir,
    match_id=100,
    salt=1,
    start_time=1783000000,
    won=True,
    stats=(),
    damage=(),
    ability_items=(),
    objectives=False,
    gold_sources=(),
):
    contents = pb.CMsgMatchMetaDataContents()
    info = contents.match_info
    info.match_id = match_id
    info.start_time = start_time
    info.duration_s = 1800
    info.winning_team = pb.k_ECitadelLobbyTeam_Team1 if won else pb.k_ECitadelLobbyTeam_Team0

    p = info.players.add()
    p.account_id = 42
    p.hero_id = 52
    p.team = pb.k_ECitadelLobbyTeam_Team1

    if stats:
        p.kills = 5
        p.deaths = 2
        p.assists = 8
        p.net_worth = stats[-1][1]
        p.last_hits = 150
        p.denies = 12

        enemy = info.players.add()
        enemy.account_id = 77
        enemy.hero_id = 1
        enemy.team = pb.k_ECitadelLobbyTeam_Team0
        enemy.net_worth = stats[-1][1] // 2

    sources_at = {}
    for t, source, gold, orbs in gold_sources:
        sources_at.setdefault(t, []).append((source, gold, orbs))

    for t, worth in stats:
        s = p.stats.add()
        s.time_stamp_s = t
        s.net_worth = worth

        for source, gold, orbs in sources_at.get(t, ()):
            gs = s.gold_sources.add()
            gs.source = source
            gs.gold = gold
            gs.gold_orbs = orbs

        es = enemy.stats.add()
        es.time_stamp_s = t
        es.net_worth = worth // 2

    for item_id, t in ability_items:
        it = p.items.add()
        it.item_id = item_id
        it.game_time_s = t

    if damage:
        p.player_slot = 1
        enemy.player_slot = 2

        dm = info.damage_matrix
        dm.sample_time_s.extend([300, 600])
        dealer = dm.damage_dealers.add()
        dealer.dealer_player_slot = 1

        for j, entry in enumerate(damage):
            name, values, *stat = entry
            dm.source_details.source_name.append(name)
            dm.source_details.stat_type.append(stat[0] if stat else 0)

            src = dealer.damage_sources.add()
            src.source_details_index = j
            t = src.damage_to_players.add()
            t.target_player_slot = 2
            t.damage.extend(values)

    if objectives:
        o = info.objectives.add()
        o.team = pb.k_ECitadelLobbyTeam_Team0
        o.team_objective_id = pb.k_eCitadelTeamObjective_Tier1_Lane1
        o.destroyed_time_s = 400
        o.first_damage_time_s = 100
        o.player_damage = 1000
        o.creep_damage = 200

        mb = info.mid_boss.add()
        mb.destroyed_time_s = 500
        mb.team_killed = pb.k_ECitadelLobbyTeam_Team1
        mb.team_claimed = pb.k_ECitadelLobbyTeam_Team0

    meta = pb.CMsgMatchMetaData()
    meta.match_id = match_id
    meta.match_details = contents.SerializeToString()

    header = b"replay999.valve.net\x00" + f"/1422450/{match_id}_{salt}.meta.bz2".encode() + b"\x00"
    f = cache_dir / f"entry_{match_id}"
    f.write_bytes(header + bz2.compress(meta.SerializeToString()))

    return f


def run_main(tmp_path, *args, accounts="you = 42"):
    cfg = tmp_path / "config.toml"
    contents = 'timezone = "America/Chicago"'

    if accounts:
        contents += f"\n[accounts]\n{accounts}\n"

    cfg.write_text(contents)
    (tmp_path / "cache").mkdir(exist_ok=True)

    base = ["--cache", str(tmp_path / "cache"), "--archive", str(tmp_path / "arc")]
    base += ["--parquet", str(tmp_path / "pq")]
    main([*base, *args], config=cfg)


def test_parse_accounts_single():
    assert parse_accounts("111222333") == [111222333]


def test_parse_accounts_multiple():
    assert parse_accounts("111222333, 123456") == [111222333, 123456]


def test_parse_accounts_names():
    names = {"main": 42, "old alt": 43}

    assert parse_accounts("main", names) == [42]
    assert parse_accounts("main, old alt", names) == [42, 43]
    assert parse_accounts("Main, 7", names) == [42, 7]


def test_parse_accounts_unknown_name_lists_config_names():
    with pytest.raises(argparse.ArgumentTypeError, match=r"unknown account 'nope'.*main"):
        parse_accounts("nope", {"main": 42})


def test_parse_accounts_unknown_name_without_config():
    with pytest.raises(argparse.ArgumentTypeError, match="none set"):
        parse_accounts("main")


def test_int_list_parses_commas_and_spaces():
    from deadlock_matches.cli.main import int_list

    assert int_list("900,901") == [900, 901]
    assert int_list("900 901") == [900, 901]


def test_int_list_rejects_non_numeric():
    from deadlock_matches.cli.main import int_list

    with pytest.raises(argparse.ArgumentTypeError, match="not a numeric id"):
        int_list("abc")


def test_download_command_merges_config_players_after_top_players(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "config.toml"
    cfg.write_text('[players.Mirage]\nsomeplayer = 22\n"already-top" = 11\n')

    monkeypatch.setattr(
        players,
        "top_players",
        lambda hero_id, limit: [{"account_id": 11, "name": "lead", "rank": 1, "region": "Asia"}],
    )

    seen = {}

    def fake_download(tracked, hero_id, n):
        seen["tracked"] = tracked
        seen["hero_id"] = hero_id
        seen["n"] = n

        return []

    monkeypatch.setattr(players, "download_matches", fake_download)
    monkeypatch.setattr(
        players, "write_player_tables", lambda rows, out_dir, exclude: {"matches": 0}
    )

    main(["download", "--hero", "Mirage", "--games", "3", "--out", str(tmp_path)], config=cfg)

    assert [t["account_id"] for t in seen["tracked"]] == [11, 22]
    assert seen["tracked"][1]["name"] == "someplayer"
    assert seen["n"] == 3

    out = capsys.readouterr().out

    assert "lead" in out
    assert "someplayer" in out
    assert "rank 1" in out


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

        return len(list(seen["ids"])), []

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


def test_sync_refuses_an_account_not_in_config(tmp_path, monkeypatch, capsys):
    cfg = _sync_config(tmp_path)
    monkeypatch.setattr(data, "sync_archive", lambda cache, archive: 0)

    main(["--parquet", str(tmp_path), "sync", "--account", "999"], config=cfg)

    out = capsys.readouterr().out

    assert "not your accounts" in out
    assert "999" in out


def test_builds_command_prints_shared_core(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        players,
        "top_players",
        lambda hero_id, limit: [{"account_id": 11, "name": "lead", "rank": 1, "region": "Asia"}],
    )

    win = {"win": True, "seq": [{"name": "Healbane", "min": 8, "slot": "spirit", "tier": 2}]}
    loss = {"win": False, "seq": [{"name": "Healbane", "min": 9, "slot": "spirit", "tier": 2}]}
    monkeypatch.setattr(players, "player_builds", lambda account_id, hero_id, n: [win, loss])

    main(["builds", "--hero", "Mirage"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "Top 1 Mirage players:" in out
    assert "lead" in out
    assert "Healbane" in out
    assert "Win %" in out
    assert "Loss %" in out
    assert "100%" in out
    assert "spirit T2" in out


def test_download_command_unknown_hero(tmp_path, capsys):
    main(["download", "--hero", "Nobody", "--out", str(tmp_path)], config=tmp_path / "none.json")

    assert "Unknown hero" in capsys.readouterr().out


def test_download_command_by_match_id(tmp_path, monkeypatch, capsys):
    seen = {}

    def fake_by_id(match_ids):
        seen["ids"] = list(match_ids)

        return [{"match_id": m} for m in match_ids]

    monkeypatch.setattr(players, "matches_by_id", fake_by_id)
    monkeypatch.setattr(
        players, "write_player_tables", lambda rows, out_dir, exclude: {"matches": len(rows)}
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

    def fake_download(tracked, hero_id, n):
        seen["tracked"] = tracked

        return []

    monkeypatch.setattr(players, "download_matches", fake_download)
    monkeypatch.setattr(
        players, "write_player_tables", lambda rows, out_dir, exclude: {"matches": 0}
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
        lambda hero_id, limit: [{"account_id": 11, "name": "lead", "rank": 1, "region": "Asia"}],
    )
    monkeypatch.setattr(
        players,
        "recent_hero_matches",
        lambda account_id, hero_id, n: [
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
    assert "11" in out
    assert "rank 1" in out
    assert "friend" in out
    assert "config" in out
    assert "5011" in out
    assert "5022" in out
    assert "win" in out
    assert "10/2/8" in out


def test_parser_rejects_account_list_form(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("accounts = [42, 43]")

    with pytest.raises(SystemExit, match=r"\[accounts\] table"):
        build_parser(p)


def test_parser_hero_always_required(tmp_path):
    with pytest.raises(SystemExit):
        build_parser(tmp_path / "config.toml").parse_args(["builds"])


def test_parser_account_defaults_from_table_config(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[accounts]\nmain = 42\n"old alt" = 43\n')

    args = build_parser(p).parse_args(["history"])

    assert args.account == [42, 43]


def test_parser_account_name_resolves(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[accounts]\nmain = 42\n"old alt" = 43\n')

    args = build_parser(p).parse_args(["winrate", "--account", "old alt"])

    assert args.account == [43]


def test_parser_account_flag_overrides_config(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[accounts]\nmain = 42\n")

    args = build_parser(p).parse_args(["compare", "--hero", "Haze", "--account", "7,8"])

    assert args.account == [7, 8]


def test_compare_unknown_stat_lists_options(capsys, tmp_path):
    run_main(tmp_path, "compare", "--hero", "Mirage", "--stat", "nonsense", "--account", "42")

    out = capsys.readouterr().out

    assert "Unknown stat: nonsense" in out
    assert "farm" in out
    assert "creep_kills" in out
    assert "souls_player" in out
    assert "gold_player" not in out


def test_snapshot_field_accepts_souls_names():
    assert performance._snapshot_field("creep_kills") == "creep_kills"
    assert performance._snapshot_field("souls_player") == "gold_player"
    assert performance._snapshot_field("souls_denied") == "gold_denied"
    assert performance._snapshot_field("net_worth") == "net_worth"
    assert performance._snapshot_field("bogus") is None


def test_compare_without_account_prints_hint(capsys, tmp_path):
    run_main(tmp_path, "compare", "--hero", "Haze", accounts=None)

    out = capsys.readouterr().out

    assert "config.toml" in out
    assert "--account" in out


def test_winrate_without_account_prints_hint(capsys, tmp_path):
    run_main(tmp_path, "winrate", accounts=None)

    assert "--account" in capsys.readouterr().out


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

    out = capsys.readouterr().out

    assert "Match 101" in out
    assert "Match 100" not in out


def test_history_account_filter(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    run_main(tmp_path, "history", "--account", "42")

    assert "Match 100" in capsys.readouterr().out

    run_main(tmp_path, "history", "--account", "99")

    assert "No match metadata found" in capsys.readouterr().out


def test_history_marks_your_rows_and_hides_ids(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000), (600, 5000)])

    cfg = tmp_path / "config.toml"
    cfg.write_text('timezone = "America/Chicago"\n[accounts]\nmain = 42\n')

    base = ["--cache", str(cache), "--archive", str(tmp_path / "arc")]
    base += ["--parquet", str(tmp_path / "pq")]
    main([*base, "history"], config=cfg)

    out = capsys.readouterr().out

    assert "You (marked * below): main (42)" in out
    assert "Account" not in out
    assert re.search(r"Mirage\s+\*\s+5/2/8", out)
    assert "77" not in out


def test_match_prints_interval_table(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000), (600, 5000)])

    run_main(tmp_path, "match", "--account", "42")

    out = capsys.readouterr().out

    assert "Match 100: Mirage, win," in out
    assert "Final: 5/2/8, 5,000 souls" in out
    assert "150 last hits, 12 denies" in out
    assert re.search(r"0-5m\s+3,000\s+600", out)
    assert re.search(r"5-10m\s+2,000\s+400", out)


def test_match_defaults_to_most_recent(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])
    write_cache_entry(cache, match_id=101, start_time=1783000000 + 86400, stats=[(300, 4000)])

    run_main(tmp_path, "match", "--account", "42")

    assert "Match 101" in capsys.readouterr().out


def test_match_interval_flag(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000), (600, 5000)])

    run_main(tmp_path, "match", "--account", "42", "--interval", "10")

    out = capsys.readouterr().out

    assert re.search(r"0-10m\s+5,000\s+500", out)
    assert "5-10m" not in out


def test_match_damage_flag_prints_source_table(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000), (600, 5000)],
        damage=[
            ("citadel_weapon_mirage_set", [500, 1200]),
            ("mirage_tornado", [800]),
            ("Bullet", [2000]),
        ],
    )

    run_main(tmp_path, "match", "--account", "42", "--damage")

    out = capsys.readouterr().out

    assert "Match 100: Mirage, win," in out
    assert "Damage to heroes by source, 5-minute intervals" in out
    assert re.search(r"Promises Kept\s+500\s+700\s+1,200\s+60%", out)
    assert re.search(r"Dust Devil\s+0\s+800\s+800\s+40%", out)
    assert re.search(r"Total\s+500\s+1,500\s+2,000", out)
    assert re.search(r"Abilities\s+0\s+800\s+800\s+40%", out)
    assert re.search(r"Gun\s+500\s+700\s+1,200\s+60%", out)
    assert "Bullet" not in out


def test_match_damage_flag_without_damage_rows(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "--account", "42", "--damage")

    assert "no damage to heroes in match 100" in capsys.readouterr().out


def test_match_healing_flag_prints_healing_and_prevented(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000), (600, 5000)],
        damage=[
            ("mirage_tornado", [400, 900], 1),
            ("citadel_weapon_mirage_set", [100, 250], 2),
        ],
    )

    run_main(tmp_path, "match", "--account", "42", "--healing")

    out = capsys.readouterr().out

    assert "Healing by source, 5-minute intervals" in out
    assert "Healing prevented, 5-minute intervals" in out
    assert re.search(r"Dust Devil\s+400\s+500\s+900\s+100%", out)
    assert re.search(r"Promises Kept\s+100\s+150\s+250\s+100%", out)


def test_match_healing_flag_without_prevented_rows(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000), (600, 5000)],
        damage=[("mirage_tornado", [400, 900], 1)],
    )

    run_main(tmp_path, "match", "--account", "42", "--healing")

    out = capsys.readouterr().out

    assert "Healing by source" in out
    assert "Healing prevented" not in out
    assert "no heal_prevented" not in out


def test_match_abilities_flag_prints_upgrade_order(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    dust_devil = 1336069669
    fire_scarabs = 3733594387
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000), (600, 5000)],
        ability_items=[(dust_devil, 60), (fire_scarabs, 120)],
    )

    run_main(tmp_path, "match", "--account", "42", "--abilities")

    out = capsys.readouterr().out

    assert "Ability upgrades" in out
    assert "Req souls" in out
    assert re.search(r"1:00\s+1\s+1\s+0\s+unlock\s+Dust Devil\s+1", out)
    assert re.search(r"2:00\s+2\s+3\s+500\s+unlock\s+Fire Scarabs\s+1", out)
    assert "cumulative AP spend" in out


def test_match_souls_flag_prints_source_and_group_table(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    g = timeline.GoldSource
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000), (600, 5000)],
        gold_sources=[
            (300, g.LANE_CREEPS, 800, 200),
            (600, g.LANE_CREEPS, 1600, 400),
            (600, g.BOSSES, 800, 0),
            (600, g.TREASURE, 200, 0),
            (600, g.ABILITY_ASSASSINATE, 400, 0),
            (600, g.ITEM_CULTIST_SACRIFICE, 600, 0),
        ],
    )

    run_main(tmp_path, "match", "--account", "42", "--souls")

    out = capsys.readouterr().out

    assert "Souls by source, 5-minute intervals" in out
    assert re.search(r"Troopers\s+1,000\s+1,000\s+2,000\s+50%", out)
    assert re.search(r"Objectives\s+0\s+800\s+800\s+20%", out)
    assert re.search(r"Urn\s+0\s+200\s+200\s+5%", out)
    assert re.search(r"Bounty\s+0\s+400\s+400\s+10%", out)
    assert re.search(r"Cultist Sacrifice\s+0\s+600\s+600\s+15%", out)
    assert re.search(r"Total\s+1,000\s+3,000\s+4,000", out)
    assert re.search(r"Lane\s+1,000\s+1,000\s+2,000\s+50%", out)
    assert re.search(r"Objectives\s+0\s+1,000\s+1,000\s+25%", out)
    assert re.search(r"Other\s+0\s+1,000\s+1,000\s+25%", out)
    assert "gross souls earned by source" in out
    assert "Assassinate" not in out


def test_match_souls_flag_without_source_rows(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "--account", "42", "--souls")

    assert "has no soul sources in match 100" in capsys.readouterr().out


def test_match_id_not_found(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "999", "--account", "42")

    assert "Match 999 is not in the archive" in capsys.readouterr().out


def test_match_hero_flag_picks_another_player(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000), (600, 5000)])

    run_main(tmp_path, "match", "100", "--hero", "Infernus")

    out = capsys.readouterr().out

    assert "Match 100: Infernus, loss," in out
    assert "2,500 souls" in out
    assert re.search(r"0-5m\s+1,500\s+300", out)


def test_match_hero_not_in_match_lists_heroes(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "100", "--hero", "Wraith")

    out = capsys.readouterr().out

    assert "No Wraith in match 100" in out
    assert "Infernus" in out
    assert "Mirage" in out


def test_match_viewed_match_needs_hero(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "100", "--account", "99")

    out = capsys.readouterr().out

    assert "None of the configured accounts played in match 100" in out
    assert "--hero" in out


def test_match_rejects_zero_interval(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "--account", "42", "--interval", "0")

    assert "--interval must be" in capsys.readouterr().out


def test_match_without_account_prints_hint(capsys, tmp_path):
    run_main(tmp_path, "match", accounts=None)

    assert "--account" in capsys.readouterr().out


def test_match_teams_view(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000), (600, 5000)], objectives=True)

    run_main(tmp_path, "match", "--account", "42", "--teams")

    out = capsys.readouterr().out

    assert "Your team: The Archmother" in out
    assert re.search(r"0-5m\s+3,000\s+1,500\s+\+1,500", out)
    assert re.search(r"5-10m\s+2,000\s+1,000\s+\+2,500", out)
    assert "6:40  your team destroys the enemy Guardian (yellow)" in out
    assert "8:20  your team kills the mid boss, enemy team steals the Rejuvenator" in out


def test_match_teams_perspective_follows_hero(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000), (600, 5000)], objectives=True)

    run_main(tmp_path, "match", "100", "--hero", "Infernus", "--teams")

    out = capsys.readouterr().out

    assert "Your team: The Hidden King" in out
    assert "6:40  enemy team destroys your Guardian (yellow)" in out
    assert "8:20  enemy team kills the mid boss, your team steals the Rejuvenator" in out


def test_match_views_mutually_exclusive(tmp_path):
    with pytest.raises(SystemExit):
        build_parser(tmp_path / "config.toml").parse_args(["match", "--damage", "--teams"])

    with pytest.raises(SystemExit):
        build_parser(tmp_path / "config.toml").parse_args(["match", "--abilities", "--teams"])

    with pytest.raises(SystemExit):
        build_parser(tmp_path / "config.toml").parse_args(["match", "--souls", "--damage"])


def test_winrate_prints_daily_table(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, won=False)
    write_cache_entry(cache, match_id=101, start_time=1783000000 + 86400)
    write_cache_entry(cache, match_id=102, start_time=1783000000 + 86400)

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    assert "grouped by America/Chicago day" in out
    assert "Cumulative net" in out
    assert "Overall: 3 games, 2-1, 66.7% win rate, +1 net wins, 0 MVP, 0 Key Player." in out


def test_winrate_weekly_table(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, won=False)
    write_cache_entry(cache, match_id=101, start_time=1783000000 + 7 * 86400)

    run_main(tmp_path, "winrate", "--account", "42", "--by", "week")

    out = capsys.readouterr().out

    assert "grouped by America/Chicago week" in out
    assert "Week" in out
    assert "2026-06-29" in out
    assert "2026-07-06" in out
    assert "Overall: 2 games, 1-1, 50.0% win rate" in out


def test_winrate_monthly_table(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, won=False)
    write_cache_entry(cache, match_id=101, start_time=1783000000 + 31 * 86400)

    run_main(tmp_path, "winrate", "--account", "42", "--by", "month")

    out = capsys.readouterr().out

    assert "grouped by America/Chicago month" in out
    assert "Month" in out
    assert "2026-07 " in out
    assert "2026-08 " in out
    assert "2026-07-01" not in out


def test_winrate_hero_appends_public_baseline(capsys, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    rows = [{"hero_id": 52, "wins": 6000, "losses": 4000, "matches": 10000}]
    monkeypatch.setattr(performance.meta, "get_hero_stats", lambda **kw: rows)

    run_main(tmp_path, "winrate", "--account", "42", "--hero", "Mirage")

    out = capsys.readouterr().out

    assert "Overall: 1 games" in out
    assert "Mirage in Eternus+ lobbies: 60.0% win rate over 10,000 games (deadlock-api.com)" in out


def test_winrate_baseline_skipped_when_offline(capsys, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    def no_network(**kw):
        raise OSError("offline")

    monkeypatch.setattr(performance.meta, "get_hero_stats", no_network)

    run_main(tmp_path, "winrate", "--account", "42", "--hero", "Mirage")

    out = capsys.readouterr().out

    assert "Overall: 1 games" in out
    assert "deadlock-api.com" not in out


def test_meta_command_hero_table(capsys, tmp_path, monkeypatch):
    rows = [
        {"hero_id": 52, "wins": 60, "losses": 40, "matches": 100},
        {"hero_id": 1, "wins": 40, "losses": 60, "matches": 100},
    ]
    monkeypatch.setattr(cli_meta.meta, "get_hero_stats", lambda **kw: rows)

    main(["meta"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "public data (all ratings, deadlock-api.com)" in out
    assert re.search(r"Hero\s+Win rate\s+Pick rate\s+Matches", out)
    assert re.search(r"Mirage\s+60.0%\s+600.0%\s+100", out)


def test_meta_command_rating_distribution(capsys, tmp_path, monkeypatch):
    rows = [
        {"hero_id": 1, "bucket": 80, "wins": 30, "losses": 30, "matches": 60},
        {"hero_id": 1, "bucket": 116, "wins": 20, "losses": 16, "matches": 36},
    ]
    seen = {}

    def fake(**kw):
        seen.update(kw)

        return rows

    monkeypatch.setattr(cli_meta.meta, "get_hero_stats", fake)

    main(["meta", "--by", "rating", "--min-rating", "Oracle"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert seen["bucket"] == "avg_badge"
    assert seen["badge"] == 81
    assert "(Oracle+ lobbies, deadlock-api.com)" in out
    assert re.search(r"Rating\s+Matches\s+Share", out)


def test_meta_command_hero_defaults_to_weekly(capsys, tmp_path, monkeypatch):
    rows = [
        {"hero_id": 52, "bucket": 1782000000, "wins": 6, "losses": 4, "matches": 10},
        {"hero_id": 1, "bucket": 1782000000, "wins": 55, "losses": 55, "matches": 110},
    ]
    seen = {}

    def fake(**kw):
        seen.update(kw)

        return rows

    monkeypatch.setattr(cli_meta.meta, "get_hero_stats", fake)

    main(["meta", "--hero", "Mirage", "--since", "2026-06-01"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert seen["bucket"] == "start_time_week"
    assert "Mirage public data (all ratings, since 2026-06-01" in out
    assert re.search(r"Week\s+Matches\s+Win rate\s+Pick rate", out)
    assert re.search(r"10\s+60.0%\s+100.0%", out)


def test_winrate_baseline_prints_without_games(capsys, tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text('timezone = "America/Chicago"\n[accounts]\nyou = 42\n')

    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    rows = [{"hero_id": 52, "wins": 55, "losses": 45, "matches": 100}]
    monkeypatch.setattr(performance.meta, "get_hero_stats", lambda **kw: rows)

    args = ["--cache", str(cache), "--archive", str(tmp_path / "arc")]
    args += ["--parquet", str(tmp_path / "pq")]
    args += ["winrate", "--account", "99", "--hero", "Mirage"]
    main(args, config=cfg)

    out = capsys.readouterr().out

    assert "No games found" in out
    assert "Mirage in Eternus+ lobbies: 55.0% win rate over 100 games (deadlock-api.com)" in out


def test_winrate_since(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    run_main(tmp_path, "winrate", "--account", "42", "--since", "2100-01-01")

    assert "No games found" in capsys.readouterr().out


def test_winrate_no_games_for_account(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    run_main(tmp_path, "winrate", "--account", "7")

    assert "No games found" in capsys.readouterr().out


def test_assets_subcommand_reports_counts(monkeypatch, capsys):
    monkeypatch.setattr(assets, "refresh_heroes", lambda: 57)
    monkeypatch.setattr(assets, "refresh_items", lambda: 251)

    data.refresh_assets(argparse.Namespace())

    out = capsys.readouterr().out

    assert "57 heroes" in out
    assert "251 upgrade items" in out


def test_schema_command_prints_dictionary(capsys):
    main(["schema", "damage"])

    out = capsys.readouterr().out

    for name in schemas.Damage.spec():
        assert name in out


def test_schema_command_prints_sample_rows(capsys, tmp_path):
    schemas.conform(
        "players",
        [
            {
                "match_id": i,
                "account_id": 42,
                "hero_id": 52,
                "hero": "Mirage",
                "team": 1,
                "player_slot": 0,
                "assigned_lane": 4,
                "lane": "blue",
                "won": True,
                "kills": i,
                "deaths": 0,
                "assists": 1,
                "net_worth": 1000,
                "last_hits": 10,
                "denies": 0,
                "mvp_rank": 0,
            }
            for i in range(6)
        ],
    ).write_parquet(tmp_path / "players.parquet")

    main(["--parquet", str(tmp_path), "schema", "players", "--sample"], config=tmp_path / "c.toml")

    out = capsys.readouterr().out

    assert "account_id" in out
    assert "Sample rows from" in out
    assert "Mirage" in out
    assert "shape: (5, 16)" in out


def test_schema_command_samples_asset_table(capsys, tmp_path):
    (tmp_path / "assets").mkdir()
    schemas.conform(
        "item_history",
        [
            {
                "item_id": 7,
                "name": "Monster Rounds",
                "class_name": "upgrade_x",
                "cost": 800,
                "slot": "weapon",
                "tier": 1,
                "is_active": False,
                "description": None,
                "era_from": dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
                "client_version": 6076,
            }
        ],
    ).write_parquet(tmp_path / "assets" / "item_history.parquet")

    main(
        ["--parquet", str(tmp_path), "schema", "item_history", "--sample"],
        config=tmp_path / "c.toml",
    )

    out = capsys.readouterr().out

    assert "Sample rows from" in out
    assert "assets/item_history.parquet" in out
    assert "Monster Rounds" in out


def test_schema_sample_needs_table(capsys):
    main(["schema", "--sample"])

    assert "--sample needs a table name" in capsys.readouterr().out


def test_schema_command_unknown_table(capsys):
    main(["schema", "test"])

    assert "Unknown table" in capsys.readouterr().out


def test_sync_archive_reports_count_and_path(tmp_path, capsys):
    cache = tmp_path / "cache"
    cache.mkdir()
    arc = tmp_path / "arc"
    arc.mkdir()
    (arc / "123_1.bin").write_bytes(b"x")

    assert data.sync_archive(cache, arc) == 0

    out = capsys.readouterr().out

    assert "Archive: 1 matches (no new)" in out
    assert data._tilde(arc) in out


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

    out = capsys.readouterr().out

    assert "+2 new" in out
    assert "Added 2 new matches" in out
    assert (pq / "matches").is_dir()
    assert (pq / "damage").is_dir()
    assert next((pq / "matches").glob("*.parquet"), None) is not None


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
    main(
        ["--cache", str(cache), "--archive", str(arc), "--parquet", str(pq), "history"], config=cfg
    )

    out = capsys.readouterr().out

    assert "no new" in out
    assert "parquet files" not in out


def test_hero_command_prints_breakpoint(capsys, tmp_path):
    main(["hero", "Mirage", "--souls", "25000"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "Mirage at 25,000 souls: level" in out
    assert "max health" in out
    assert "ability points" in out
    assert "gun dps" in out


def test_hero_command_level_instead_of_souls(capsys, tmp_path):
    main(["hero", "Mirage", "--level", "10"], config=tmp_path / "none.json")

    assert "Mirage at level 10" in capsys.readouterr().out


def test_hero_command_base_card(capsys, tmp_path):
    main(["hero", "Mirage"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "health regen" in out
    assert "Each boon adds" in out
    assert "light / +" in out
    assert "gun dps" in out
    assert "abilities" in out
    assert "Fire Scarabs" in out
    assert "Melee" not in out


def test_hero_command_shows_alt_fire(capsys, tmp_path):
    main(["hero", "Viscous"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "alt fire" in out
    assert out.index("alt fire") > out.index("gun dps")


def test_hero_command_no_alt_fire_when_absent(capsys, tmp_path):
    main(["hero", "Mirage"], config=tmp_path / "none.json")

    assert "alt fire" not in capsys.readouterr().out


def test_hero_command_unknown_hero(capsys, tmp_path):
    main(["hero", "Nobody", "--level", "10"], config=tmp_path / "none.json")

    assert "Unknown hero" in capsys.readouterr().out


def test_ability_command_prints_numbers(capsys, tmp_path):
    main(["ability", "Dust Devil"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "Dust Devil  (Mirage ability)" in out
    assert "damage" in out
    assert "x spirit" in out
    assert "T1" in out
    assert " -> " in out


def test_ability_command_ambiguous_needs_hero(capsys, tmp_path):
    main(["ability", "Melee"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "several heroes" in out
    assert "--hero" in out

    main(["ability", "Melee", "--hero", "Mirage"], config=tmp_path / "none.json")

    assert "(Mirage ability)" in capsys.readouterr().out


def test_ability_command_shows_gun(capsys, tmp_path):
    main(["ability", "Promises Kept"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "(Mirage weapon)" in out
    assert "bullet damage" in out

    falloff = next(s for s in out.splitlines() if "damage falloff start range" in s)

    assert falloff.endswith("m")


def test_ability_command_unknown(capsys, tmp_path):
    main(["ability", "Nothing Real"], config=tmp_path / "none.json")

    assert "Unknown ability" in capsys.readouterr().out


def test_ability_command_souls_resolves_spirit(capsys, tmp_path):
    main(["ability", "Fire Scarabs", "--souls", "25000"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "at level" in out
    assert "spirit" in out
    assert "x spirit)" in out
    assert " -> " in out


def test_ability_command_souls_resolves_boons(capsys, tmp_path):
    main(["ability", "Bashdown", "--souls", "25000"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "at level" in out
    assert "spirit" in out
    assert "x light melee)" in out


def test_ability_report_renders_every_record(monkeypatch, capsys):
    for a in abilities.ability_map().values():
        monkeypatch.setattr(abilities, "ability_by_name", lambda *_, _a=a, **__: _a)
        cards.ability_report(argparse.Namespace(ability=a.name, hero=None, souls=None, level=None))

    out = capsys.readouterr().out

    assert " d p s " not in out
    assert not re.search(r"\bnan\b", out)


def test_item_command_prints_card_without_hero(capsys, tmp_path):
    main(["item", "Mercurial Magnum"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "Mercurial Magnum  (spirit tier 4, 6,400 souls)" in out
    assert "upgrades from Quicksilver Reload" in out
    assert "spirit power" in out
    assert "Passive  (cooldown 15s)" in out
    assert "fire rate" in out
    assert "win rate" not in out


def test_item_command_card_shows_active_section(capsys, tmp_path):
    main(["item", "Echo Shard"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "Active  (cooldown" in out
    assert "Reset the cooldown" in out


def test_item_command_unknown_item(capsys, tmp_path):
    main(["item", "No Such Trinket"], config=tmp_path / "none.json")

    assert "Unknown item" in capsys.readouterr().out


def test_item_card_falls_back_without_sections(capsys):
    it = items.Item(
        id=1,
        name="Old Snapshot",
        class_name="upgrade_old",
        cost=500,
        slot="weapon",
        tier=1,
        is_active=False,
        description="Does a thing",
        properties={"tech_power": 7, "bonus_fire_rate": 12},
    )

    cards.item_card(it)

    out = capsys.readouterr().out

    assert "Does a thing" in out
    assert "tech power" in out
    assert "bonus fire rate" in out


def test_item_command_games_table_collapses_not_built(monkeypatch, capsys, tmp_path):
    rows = pl.LazyFrame(
        {
            "match_id": [90111222, 90111333, 90111444],
            "account_id": [42, 42, 42],
            "hero": ["Mirage", "Mirage", "Mirage"],
            "won": [True, False, True],
            "duration_s": [1800, 2400, 2000],
            "game_time_s": [900, None, None],
            "owned_s": [900, None, None],
            "damage": [1200, None, None],
            "dealt_after_buy": [12000, None, None],
        }
    )
    monkeypatch.setattr(cli_items.queries, "item_games", lambda *a, **kw: rows)
    monkeypatch.setattr(cli_items.players, "PARQUET_DIR", tmp_path)

    def no_api(*a, **kw):
        raise ValueError("no api data")

    monkeypatch.setattr(cli_items.meta, "get_item_stats", no_api)

    args = argparse.Namespace(
        item="Mystic Shot",
        hero="Mirage",
        account=[42],
        parquet=str(tmp_path),
        top=10,
        min_rating="Eternus",
        since=None,
    )
    cli_items.item_report(args, tmp_path / "none.toml")

    out = capsys.readouterr().out

    assert "Mystic Shot (weapon tier 2, 1,600 souls) on Mirage" in out
    assert "Passive" not in out
    assert "% of dmg" in out
    assert re.search(r"90111222\s+WIN", out)
    assert "10.0%" in out
    assert re.search(r"Built\s+1\s+1\s+0", out)
    assert re.search(r"Not built\s+2\s+1\s+1", out)
    assert "90111333" not in out


def test_item_command_header_uses_account_names(monkeypatch, capsys, tmp_path):
    rows = pl.LazyFrame(
        {
            "match_id": [90111222],
            "account_id": [42],
            "hero": ["Mirage"],
            "won": [True],
            "duration_s": [1800],
            "game_time_s": [900],
            "owned_s": [900],
            "damage": [1200],
            "dealt_after_buy": [12000],
        }
    )
    monkeypatch.setattr(cli_items.queries, "item_games", lambda *a, **kw: rows)
    monkeypatch.setattr(cli_items.players, "PARQUET_DIR", tmp_path)

    def no_api(*a, **kw):
        raise ValueError("no api data")

    monkeypatch.setattr(cli_items.meta, "get_item_stats", no_api)

    cfg = tmp_path / "config.toml"
    cfg.write_text("[accounts]\nmain = 42\n")

    args = argparse.Namespace(
        item="Mystic Shot",
        hero="Mirage",
        account=[42, 99],
        parquet=str(tmp_path),
        top=10,
        min_rating="Eternus",
        since=None,
    )
    cli_items.item_report(args, cfg)

    assert "Your games (accounts main, 99, 1 found)" in capsys.readouterr().out


def test_item_command_quotes_hero_in_download_hint(monkeypatch, capsys, tmp_path):
    rows = pl.LazyFrame(
        {
            "match_id": [90111222],
            "account_id": [42],
            "hero": ["Lady Geist"],
            "won": [True],
            "duration_s": [1800],
            "game_time_s": [900],
            "owned_s": [900],
            "damage": [1200],
            "dealt_after_buy": [12000],
        }
    )
    monkeypatch.setattr(cli_items.queries, "item_games", lambda *a, **kw: rows)
    monkeypatch.setattr(cli_items.players, "PARQUET_DIR", tmp_path)

    def no_api(*a, **kw):
        raise ValueError("no api data")

    monkeypatch.setattr(cli_items.meta, "get_item_stats", no_api)

    args = argparse.Namespace(
        item="Healbane",
        hero="Lady Geist",
        account=[42],
        parquet=str(tmp_path),
        top=10,
        min_rating="Eternus",
        since=None,
    )
    cli_items.item_report(args, tmp_path / "none.toml")

    assert 'Run `deadlock download --hero "Lady Geist"`' in capsys.readouterr().out


def test_item_card_renders_every_item(capsys):
    for it in items.item_map().values():
        cards.item_card(it)

    out = capsys.readouterr().out

    assert not re.search(r"\bnan\b", out)
    assert not re.search(r"\bnone\b", out, re.IGNORECASE)


def test_hero_report_renders_every_hero(capsys):
    for h in heroes.hero_map().values():
        if not h.player_selectable or h.disabled:
            continue

        cards.hero_report(argparse.Namespace(hero=h.name, souls=None, level=None))
        cards.hero_report(argparse.Namespace(hero=h.name, souls=25000, level=None))

    out = capsys.readouterr().out

    assert "Unknown hero" not in out
    assert "Each boon adds" in out
    assert not re.search(r"\bnan\b", out)


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


def test_accounts_command_lists_and_suggests(capsys, tmp_path):
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

    for fn in (
        "build_item_history",
        "build_hero_history",
        "build_ability_history",
        "build_rank_history",
    ):
        monkeypatch.setattr(assets, fn, lambda **kw: called.append(True))

    main(["backfill"], config="none.json")

    out = capsys.readouterr().out

    assert "--confirm" in out
    assert called == []


def test_backfill_confirm_rebuilds_and_reports(monkeypatch, capsys):
    counts = {
        "build_item_history": 33,
        "build_hero_history": 25,
        "build_ability_history": 40,
        "build_rank_history": 1,
    }

    for fn, n in counts.items():
        monkeypatch.setattr(assets, fn, lambda n=n, **kw: n)

    main(["backfill", "--confirm"], config="none.json")

    out = capsys.readouterr().out

    for name in ("items", "heroes", "abilities", "ranks"):
        assert name in out

    assert "40 eras" in out


def test_hero_card_as_of_shows_era_label(capsys, tmp_path):
    main(["hero", "Mirage", "--as-of", "2026-02-01"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "as of 2026-02-01" in out


def test_hero_card_changes_lists_patches(capsys, tmp_path):
    main(["hero", "Mirage", "--changes"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "change history" in out
    assert "build" in out


def test_item_card_changes_lists_patches(capsys, tmp_path):
    main(["item", "Monster Rounds", "--changes"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "change history" in out
