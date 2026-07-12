import argparse
import bz2
import datetime as dt
import re
import shutil
import zoneinfo

import polars as pl
import pytest

from deadlock_matches import (
    export,
    extract,
    players,
    schemas,
)
from deadlock_matches.assets import (
    abilities,
    heroes,
    items,
    snapshots,
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
    account=42,
    stats=(),
    damage=(),
    ability_items=(),
    item_events=(),
    accolades=(),
    buffs=(),
    stacks=(),
    custom_stats=(),
    shots=None,
    objectives=False,
    gold_sources=(),
    teammates=0,
    team_gold_sources=(),
    death_log=(),
    lanes=False,
    enemy_worth=None,
    abandon_s=None,
    not_scored=False,
    badges=None,
    paths=False,
):
    contents = pb.CMsgMatchMetaDataContents()
    info = contents.match_info
    info.match_id = match_id
    info.start_time = start_time
    info.duration_s = 1800
    info.winning_team = pb.k_ECitadelLobbyTeam_Team1 if won else pb.k_ECitadelLobbyTeam_Team0
    info.not_scored = not_scored
    info.match_mode = pb.k_ECitadelMatchMode_Unranked

    if badges is not None:
        info.average_badge_team0, info.average_badge_team1 = badges

    p = info.players.add()
    p.account_id = account
    p.hero_id = 52
    p.team = pb.k_ECitadelLobbyTeam_Team1

    if abandon_s is not None:
        p.abandon_match_time_s = abandon_s

    mates = []

    for i in range(teammates):
        mate = info.players.add()
        mate.account_id = 43 + i
        mate.hero_id = 2 + i
        mate.team = pb.k_ECitadelLobbyTeam_Team1
        mate.player_slot = 3 + i
        mates.append(mate)

    if stats:
        p.kills = 5
        p.deaths = 2
        p.assists = 8
        p.net_worth = stats[-1][1]
        p.last_hits = 150
        p.denies = 12
        p.player_slot = 1

        enemy = info.players.add()
        enemy.account_id = 77
        enemy.hero_id = 1
        enemy.team = pb.k_ECitadelLobbyTeam_Team0
        enemy.net_worth = enemy_worth if enemy_worth is not None else stats[-1][1] // 2
        enemy.player_slot = 2

        if lanes:
            p.assigned_lane = 1
            enemy.assigned_lane = 1

    sources_at = {}
    for t, source, gold, orbs in gold_sources:
        sources_at.setdefault(t, []).append((source, gold, orbs))

    team_sources_at = {}
    for t, source, gold, orbs in team_gold_sources:
        team_sources_at.setdefault(t, []).append((source, gold, orbs))

    for t, worth in stats:
        s = p.stats.add()
        s.time_stamp_s = t
        s.net_worth = worth

        for source, gold, orbs in sources_at.get(t, ()):
            gs = s.gold_sources.add()
            gs.source = source
            gs.gold = gold
            gs.gold_orbs = orbs

        for source, gold, orbs in team_sources_at.get(t, ()):
            gs = s.gold_sources.add()
            gs.source = source
            gs.gold = gold
            gs.gold_orbs = orbs

        for mate in mates:
            ms = mate.stats.add()
            ms.time_stamp_s = t
            ms.net_worth = worth

            for source, gold, orbs in team_sources_at.get(t, ()):
                gs = ms.gold_sources.add()
                gs.source = source
                gs.gold = gold
                gs.gold_orbs = orbs

        es = enemy.stats.add()
        es.time_stamp_s = t
        es.net_worth = enemy_worth if enemy_worth is not None else worth // 2

    for item_id, t in ability_items:
        it = p.items.add()
        it.item_id = item_id
        it.game_time_s = t

    for item_id, t, sold, flags, *imbued in item_events:
        it = p.items.add()
        it.item_id = item_id
        it.game_time_s = t
        it.sold_time_s = sold
        it.flags = flags

        if imbued:
            it.imbued_ability_id = imbued[0]

    for accolade_id, value, threshold in accolades:
        acc = p.accolades.add()
        acc.accolade_id = accolade_id
        acc.accolade_stat_value = value
        acc.accolade_threshold_achieved = threshold

    for pickup, count, permanent in buffs:
        b = p.power_up_buffs.add()
        b.type = pickup
        b.value = count
        b.is_permanent = permanent

    for ability_id, value, is_enemy in stacks:
        st = (enemy if is_enemy else p).ability_stats.add()
        st.ability_id = ability_id
        st.ability_value = value

    for stat_id, (name, _) in enumerate(custom_stats, start=1):
        reg = info.custom_user_stats.add()
        reg.name = name
        reg.id = stat_id

    for stat_id, (_, value) in enumerate(custom_stats, start=1):
        cs = p.stats[-1].custom_user_stats.add()
        cs.id = stat_id
        cs.value = value

    if shots is not None:
        p.stats[-1].shots_hit, p.stats[-1].shots_missed = shots

    if paths:
        mp = info.match_paths
        mp.interval_s = 1.0
        mp.x_resolution = 100
        mp.y_resolution = 100

        track = mp.paths.add()
        track.player_slot = p.player_slot
        track.x_max = 10000.0
        track.y_max = 10000.0
        track.x_pos.extend(range(10))
        track.y_pos.extend([0] * 10)
        track.health.extend([100] * 10)
        track.combat_type.extend([1] * 4 + [0] * 6)
        track.move_type.extend([0, 4, 4, 3, 0, 7, 8, 7, 6, 0])

    for victim_slot, killer_slot, t in death_log:
        victim = p if victim_slot == 1 else enemy
        d = victim.death_details.add()
        d.game_time_s = t
        d.time_to_kill_s = 2.5
        d.death_duration_s = 20
        d.death_pos.x = 1000.0
        d.death_pos.y = 2000.0
        d.death_pos.z = 0.0

        if killer_slot:
            d.killer_player_slot = killer_slot
            d.killer_pos.x = 1000.0 + 10 * 39.37
            d.killer_pos.y = 2000.0
            d.killer_pos.z = 0.0

    if damage:
        dm = info.damage_matrix
        dm.sample_time_s.extend([300, 600])
        dealers = {}

        for j, entry in enumerate(damage):
            name, values, *rest = entry
            dm.source_details.source_name.append(name)
            dm.source_details.stat_type.append(rest[0] if rest else 0)
            dealer_slot = rest[1] if len(rest) > 1 else 1
            target_slot = rest[2] if len(rest) > 2 else 2

            dealer = dealers.get(dealer_slot)

            if dealer is None:
                dealer = dm.damage_dealers.add()
                dealer.dealer_player_slot = dealer_slot
                dealers[dealer_slot] = dealer

            src = dealer.damage_sources.add()
            src.source_details_index = j
            t = src.damage_to_players.add()
            t.target_player_slot = target_slot
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


def run_main(tmp_path, *args, accounts="you = 42", extra=""):
    cfg = tmp_path / "config.toml"
    contents = 'timezone = "America/Chicago"'

    if accounts:
        contents += f"\n[accounts]\n{accounts}\n"

    if extra:
        contents += f"\n{extra}\n"

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


def test_download_command_defaults_to_the_watchlist(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[players.Mirage]\nsomeplayer = 22\nladderer = 11\n")

    monkeypatch.setattr(
        players,
        "ladder_positions",
        lambda hero_id: {11: {"name": "lead", "rank": 1, "region": "Asia"}},
    )

    seen = {}

    def fake_download(tracked, hero_id, n, archive_dir):
        seen["tracked"] = tracked
        seen["n"] = n

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

    def fake_download(tracked, hero_id, n, archive_dir):
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
        "pool_members",
        lambda hero, parquet_dir=None, config_path=None: [
            {"name": "lead", "account_id": 11, "games": 2, "rank": 1, "downloaded_at": None}
        ],
    )

    win = {
        "account_id": 11,
        "win": True,
        "seq": [{"name": "Healbane", "min": 8, "slot": "spirit", "tier": 2}],
    }
    loss = {
        "account_id": 11,
        "win": False,
        "seq": [{"name": "Healbane", "min": 9, "slot": "spirit", "tier": 2}],
    }
    monkeypatch.setattr(
        players, "pool_builds", lambda hero, parquet_dir=None, config_path=None: [win, loss]
    )

    main(["builds", "--hero", "Mirage"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "Tracked Mirage players (2 downloaded games):" in out
    assert "lead" in out
    assert "1W 1L" in out
    assert "Healbane" in out
    assert "Win %" in out
    assert "Loss %" in out
    assert "100%" in out
    assert "spirit T2" in out


def test_builds_command_without_tracked_players_prints_hint(tmp_path, capsys):
    main(["builds", "--hero", "Mirage"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "No players tracked for Mirage" in out
    assert "deadlock leaderboard" in out


def test_builds_command_without_downloads_prints_hint(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(players, "PARQUET_DIR", tmp_path / "players-pq")
    cfg = tmp_path / "config.toml"
    cfg.write_text("[players.Mirage]\nsomeplayer = 22\n")

    main(["builds", "--hero", "Mirage"], config=cfg)

    out = capsys.readouterr().out

    assert "No downloaded games from the tracked Mirage players yet" in out
    assert 'deadlock download --hero "Mirage"' in out


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

    def fake_download(tracked, hero_id, n, archive_dir):
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
    assert "tracked" in out
    assert "5011" in out
    assert "5022" in out
    assert "win" in out
    assert "10/2/8" in out


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
    assert "souls" in out
    assert "farm" in out
    assert "denies" in out
    assert "soul_sources" in out
    assert "souls_player" not in out
    assert "ability_points" not in out
    assert "gold_player" not in out


def test_compare_without_account_prints_hint(capsys, tmp_path):
    run_main(tmp_path, "compare", "--hero", "Haze", accounts=None)

    out = capsys.readouterr().out

    assert "config.toml" in out
    assert "--account" in out


def _pool_game(match_id):
    info = pb.CMsgMatchMetaDataContents().match_info
    info.match_id = match_id
    info.start_time = 1783000000
    info.duration_s = 1800
    info.winning_team = pb.k_ECitadelLobbyTeam_Team1
    info.match_mode = pb.k_ECitadelMatchMode_Unranked

    tp = info.players.add()
    tp.account_id = 11
    tp.hero_id = 52
    tp.team = pb.k_ECitadelLobbyTeam_Team1
    tp.player_slot = 1

    for t, worth in [(180, 3000), (360, 6000)]:
        s = tp.stats.add()
        s.time_stamp_s = t
        s.net_worth = worth

    return info


def test_compare_command_reads_the_downloaded_pool(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "cache"
    cache.mkdir()

    for match_id in (100, 101, 102):
        write_cache_entry(cache, match_id=match_id, stats=[(180, 1000), (360, 2000)])

    monkeypatch.setattr(players, "match_info", lambda mid, archive_dir=None: _pool_game(mid))
    store = tmp_path / "players-pq"
    ledger = [
        {
            "match_id": match_id,
            "account_id": 11,
            "player": "pro",
            "hero_id": 52,
            "rank": 2,
            "region": "Asia",
            "downloaded_at": dt.datetime(2026, 7, 1, tzinfo=dt.UTC),
        }
        for match_id in (900, 901, 902)
    ]
    players.write_player_tables(ledger, out_dir=store)
    monkeypatch.setattr(players, "PARQUET_DIR", store)

    run_main(
        tmp_path,
        "compare",
        "--hero",
        "Mirage",
        extra="[players.Mirage]\npro = 11\n",
    )

    out = capsys.readouterr().out

    assert "You (you, 3 games) vs 1 tracked Mirage players (3 games): souls" in out
    assert re.search(r"you\s+3\s+-\s+-\s+67\s+67", out)
    assert re.search(r"pro\s+3\s+2\s+2026-07-01\s+200\s+200", out)
    assert re.search(r"0-5\s+200\s+600\s+-400\s+-2,000\s+3/3", out)
    assert re.search(r"5-10\s+200\s+600\s+-400\s+-4,000\s+3/3", out)
    assert re.search(r"10-15\s+0\s+0\s+\+0\s+-4,000\s+3/3", out)
    assert re.search(r"Total\s+67\s+200\s+-133", out)
    assert "Biggest souls gap: 0-5m, you 200/min vs tracked players 600/min" in out


def test_compare_command_shows_deaths_as_counts(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "cache"
    cache.mkdir()

    for match_id in (100, 101, 102):
        write_cache_entry(cache, match_id=match_id, stats=[(180, 1000), (360, 2000)])

    monkeypatch.setattr(players, "match_info", lambda mid, archive_dir=None: _pool_game(mid))
    store = tmp_path / "players-pq"
    ledger = [
        {
            "match_id": match_id,
            "account_id": 11,
            "player": "pro",
            "hero_id": 52,
            "rank": 2,
            "region": "Asia",
            "downloaded_at": dt.datetime(2026, 7, 1, tzinfo=dt.UTC),
        }
        for match_id in (900, 901, 902)
    ]
    players.write_player_tables(ledger, out_dir=store)
    monkeypatch.setattr(players, "PARQUET_DIR", store)

    run_main(
        tmp_path,
        "compare",
        "--hero",
        "Mirage",
        "--stat",
        "deaths",
        extra="[players.Mirage]\npro = 11\n",
    )

    out = capsys.readouterr().out

    assert "Avg/game" in out
    assert "Med/game" in out
    assert "/min" not in out
    assert re.search(r"Min\s+You\s+Them\s+Gap\s+Cumulative gap\s+Games", out)


def test_compare_command_without_tracked_players_prints_hint(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(players, "PARQUET_DIR", tmp_path / "players-pq")
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(180, 1000)])

    run_main(tmp_path, "compare", "--hero", "Mirage")

    out = capsys.readouterr().out

    assert "No players tracked for Mirage" in out
    assert "deadlock leaderboard" in out


def test_compare_command_without_downloads_prints_hint(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(players, "PARQUET_DIR", tmp_path / "players-pq")
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(180, 1000)])

    run_main(tmp_path, "compare", "--hero", "Mirage", extra="[players.Mirage]\npro = 11\n")

    out = capsys.readouterr().out

    assert "No downloaded games from the tracked Mirage players yet" in out
    assert 'deadlock download --hero "Mirage"' in out


def test_help_sections_cover_every_command(tmp_path):
    from deadlock_matches.cli.main import COMMAND_HELP, SECTIONS

    parser = build_parser(tmp_path / "config.toml")
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    registered = set(sub.choices or [])
    sectioned = [name for _, names in SECTIONS for name in names]

    assert set(sectioned) == registered
    assert len(sectioned) == len(set(sectioned))
    assert set(COMMAND_HELP) == registered


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

    assert "No match metadata found" in capsys.readouterr().out


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
        r"Account\s+Hero\s+Result\s+K/D/A\s+Souls\s+Damage\s+Timestamp\s+Match ID", out
    )
    assert re.search(r"main\s+Mirage\s+win\s+5/2/8\s+5,000\s+\S+\s+\S+ \S+\s+100", out)
    assert "42" not in out
    assert "77" not in out


def test_history_without_account_prints_hint(capsys, tmp_path):
    run_main(tmp_path, "history", accounts=None)

    assert "--account" in capsys.readouterr().out


def test_history_defaults_to_last_ten_games(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()

    for n in range(12):
        write_cache_entry(cache, match_id=100 + n, start_time=1783000000 + n * 3600)

    run_main(tmp_path, "history")

    lines = [line.rstrip() for line in capsys.readouterr().out.splitlines()]
    listed = [line for line in lines if re.search(r"\d{3}$", line)]

    assert len(listed) == 10
    assert listed[0].endswith("102")
    assert listed[-1].endswith("111")

    run_main(tmp_path, "history", "--days", "1")

    lines = [line.rstrip() for line in capsys.readouterr().out.splitlines()]

    assert sum(1 for line in lines if re.search(r"\d{3}$", line)) == 12


def test_match_prints_interval_table(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000), (600, 5000)])

    run_main(tmp_path, "match", "--account", "42")

    out = capsys.readouterr().out

    assert "Match 100: Mirage, win," in out
    assert re.search(r"Team\s+Hero\s+K/D/A\s+Souls\s+Damage\s+Obj damage", out)
    assert re.search(r"The Archmother\s+Mirage \*\s+5/2/8\s+5,000", out)
    assert re.search(r"150\s+12", out)
    assert re.search(r"0-5m\s+3,000\s+600", out)
    assert re.search(r"5-10m\s+2,000\s+400", out)
    assert re.search(r"Total\s+5,000\s+167", out)
    assert "Final:" not in out
    assert "Obj dmg" not in out


def test_match_defaults_to_most_recent(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])
    write_cache_entry(cache, match_id=101, start_time=1783000000 + 86400, stats=[(300, 4000)])

    run_main(tmp_path, "match", "--account", "42")

    assert "Match 101" in capsys.readouterr().out


def test_match_ago_steps_back_from_latest(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])
    write_cache_entry(cache, match_id=101, start_time=1783000000 + 86400, stats=[(300, 4000)])

    run_main(tmp_path, "match", "--account", "42", "--ago", "1")

    assert "Match 100" in capsys.readouterr().out


def test_match_ago_past_history_reports_the_count(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "--account", "42", "--ago", "5")

    assert "Only fewer than 6 games" in capsys.readouterr().out


def test_match_ago_with_a_match_id_is_rejected(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "100", "--account", "42", "--ago", "1")

    assert "not both" in capsys.readouterr().out


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


def test_match_items_flag_prints_buy_order(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    extra_health = 3633614685
    extra_regen = 2829638276
    fortitude = 3585132399
    duration_extender = 2951612397
    dust_devil = 1336069669
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        item_events=[
            (999999999, 30, 0, 0),
            (extra_health, 60, 300, 1),
            (extra_regen, 100, 500, 0),
            (fortitude, 300, 0, 0),
            (duration_extender, 400, 0, 0, dust_devil),
        ],
    )

    run_main(tmp_path, "match", "--account", "42", "--items")

    out = capsys.readouterr().out

    assert "Item purchases" in out
    assert re.search(
        r"1:00\s+1\s+Extra Health\s+vitality\s+1\s+[\d,]+\s+into Fortitude at 5:00", out
    )
    assert re.search(r"1:40\s+2\s+Extra Regen\s+vitality\s+1\s+[\d,]+\s+sold at 8:20", out)
    assert re.search(r"5:00\s+3\s+Fortitude\s+vitality\s+3", out)
    assert re.search(r"6:40\s+4\s+Duration Extender\s+spirit\s+2\s+[\d,]+\s+imbues Dust Devil", out)
    assert "999999999" not in out
    assert "not sold" in out


def test_match_items_upgrade_note_without_a_matching_buy(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        item_events=[(3077079169, 200, 250, 1)],
    )

    run_main(tmp_path, "match", "--account", "42", "--items")

    out = capsys.readouterr().out

    assert re.search(
        r"3:20\s+1\s+High-Velocity Rounds\s+weapon\s+1\s+[\d,]+\s+upgraded at 4:10", out
    )


def test_match_accolades_flag_prints_stat_awards(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        accolades=[(4, 39303, 0), (1, 7, 2), (999, 3, -1)],
    )

    run_main(tmp_path, "match", "--account", "42", "--accolades")

    out = capsys.readouterr().out

    assert "Accolades" in out
    assert re.search(r"kills\s+7\s+\*\*\*\s+Killer Instinct", out)
    assert re.search(r"player damage\s+39,303\s+\*\s+Bring the Pain", out)
    assert re.search(r"id999\s+3", out)
    assert "thresholds cleared" in out


def test_match_buffs_flag_prints_buff_table(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        buffs=[
            ("hp_permanent_pickup_lv2", 3, True),
            ("cd_permanent_pickup", 2, True),
            ("gun_powerup_pickup", 4, False),
        ],
    )

    run_main(tmp_path, "match", "--account", "42", "--buffs")

    out = capsys.readouterr().out

    assert "Permanent buffs" in out
    assert re.search(r"max health\s+0\s+3\s+0\s+3\s+\+60", out)
    assert re.search(r"cooldown reduction\s+2\s+0\s+0\s+2\s+\+1%", out)
    assert re.search(r"spirit power\s+0\s+0\s+0\s+0\s+-", out)
    assert "Bridge buffs" in out
    assert re.search(r"weapon\s+4", out)
    assert "gun_powerup_pickup" not in out
    assert "patch the match was played on" in out


def test_match_buffs_flag_prints_sources(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        buffs=[("hp_permanent_pickup", 16, True)],
        accolades=[(14, 2, 0)],
        custom_stats=[("PowerUp Permanent", 5), ("PowerUp Gold", 20)],
        objectives=True,
    )

    run_main(tmp_path, "match", "--account", "42", "--buffs")

    out = capsys.readouterr().out

    assert "Sources" in out
    assert re.search(r"statues collected\s+5\s+20 broken", out)
    assert re.search(r"sinner jackpots\s+2\s+\+8", out)
    assert re.search(r"mid boss kills\s+1\s+\+2 to the whole team", out)
    assert re.search(r"other sources\s+\+1 \(urn runs and light melee jackpots\)", out)


def test_match_buffs_flag_without_any_collected(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "--account", "42", "--buffs")

    out = capsys.readouterr().out

    assert "No buffs for Mirage in match 100" in out


def test_match_stacks_flag_prints_every_player(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        stacks=[(3074274290, 16, False), (2521902222, 154, True)],
    )

    run_main(tmp_path, "match", "--account", "42", "--stacks")

    out = capsys.readouterr().out

    assert "Stacks" in out
    assert re.search(r"Mirage \*\s+ally\s+Trophy Collector\s+16", out)
    assert re.search(r"Infernus\s+enemy\s+Sticky Bomb\s+154", out)
    assert "track stacks" in out


def test_match_stacks_flag_without_any_counters(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "--account", "42", "--stacks")

    out = capsys.readouterr().out

    assert "No stack counters in match 100" in out


def test_match_movement_flag_prints_lobby_and_intervals(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)], paths=True)

    run_main(tmp_path, "match", "--account", "42", "--movement")

    out = capsys.readouterr().out

    assert "Movement" in out
    assert re.search(r"Mirage \*\s+ally", out)
    assert "Mirage per interval" in out
    assert "Meters" in out
    assert "Dashes" in out
    assert "0-5m" in out
    assert "Total" in out
    assert "20.0%" in out


def test_match_movement_flag_without_paths(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "--account", "42", "--movement")

    out = capsys.readouterr().out

    assert "no movement rows in match 100" in out


def test_movement_by_player_table(capsys):
    metrics = {
        "distance_min": 39.37 * 400.0,
        "stationary_percent": 7.0,
        "slide_percent": 8.0,
        "in_air_percent": 20.0,
        "zipline_percent": 9.0,
        "combat_percent": 25.0,
        "dashes_min": 2.0,
        "air_dashes_min": 0.5,
    }
    you = pl.DataFrame([{**metrics, "distance_min": 39.37 * 350.0}])
    top = pl.DataFrame(
        [
            {"match_id": 900, "account_id": 11, **metrics},
            {"match_id": 901, "account_id": 22, **metrics},
            {"match_id": 902, "account_id": 33, **metrics},
        ]
    )
    tracked = pl.DataFrame(
        [
            {"match_id": 900, "account_id": 11, "rank": 5},
            {"match_id": 901, "account_id": 22, "rank": None},
            {"match_id": 902, "account_id": 33, "rank": None},
        ]
    )

    performance._movement_by_player(
        you, top, tracked, labels={11: "Someone", 22: "other", 33: "스노우맨"}
    )

    out = capsys.readouterr().out

    assert re.search(r"you\s+-\s+1\s+-\s+350\.0", out)
    assert re.search(r"Someone\s+11\s+1\s+5\s+400\.0", out)
    assert re.search(r"other\s+22\s+1\s+-\s+400\.0", out)
    assert re.search(r"스노우맨\s+33\s+1\s+-\s+400\.0", out)


def test_fit_name_counts_wide_characters_double():
    assert performance._fit_name("스노우맨", 14) == "스노우맨" + " " * 6
    assert performance._fit_name("스노우맨", 6) == "스노우"
    assert performance._fit_name("a-very-long-player-name", 14) == "a-very-long-pl"


COUNTERSPELL = 1414025773


def test_match_combat_flag_prints_aim_and_ranges(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        custom_stats=[
            ("Enemy Hero Accuracy##Shots", 1000),
            ("Enemy Hero Accuracy##Hits", 250),
            ("Enemy Hero Accuracy##Headshots", 50),
            ("Enemy Hero Accuracy - Incoming##Shots", 800),
            ("Enemy Hero Accuracy - Incoming##Hits", 200),
            ("Outgoing Bullet Dist##10", 3000),
            ("Outgoing Bullet Dist##20", 1000),
            ("Enemy Hero Falloff##No Falloff", 75),
            ("Enemy Hero Falloff##Partial Falloff", 25),
        ],
        shots=(1400, 600),
    )

    run_main(tmp_path, "match", "--account", "42", "--combat")

    out = capsys.readouterr().out

    assert "Aim vs heroes" in out
    assert re.search(r"Mirage \*\s+ally\s+1,000\s+25\.0%\s+20\.0%", out)
    assert "Enemy team at you: 800 shots, 200 (25%) hits, 0 (0%) headshots" in out
    assert "Accuracy with troopers and everything else included: 70%" in out
    assert "Gunfight" not in out
    assert "Damage by range" in out
    assert re.search(r"0-10m\s+3,000 \(75%\)", out)
    assert re.search(r"10-20m\s+1,000 \(25%\)", out)
    assert "Falloff on your hits: 75% none, 25% partial, 0% max" in out
    assert "Falloff on hits taken" not in out


def test_match_combat_flag_parry_lines(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        custom_stats=[("Parry Success", 4), ("Parry Miss", 2)],
        item_events=[(COUNTERSPELL, 884, 0, 0)],
        damage=[
            ("ability_melee_inferno", [100, 400], 0, 2, 1),
            ("citadel_weapon_hornet", [50, 900], 0, 2, 1),
        ],
    )

    run_main(tmp_path, "match", "--account", "42", "--combat")

    out = capsys.readouterr().out

    assert "Parries" in out
    assert "Successful 4, missed 2" in out
    assert "Melee damage taken (light/heavy melee): 400, most from Infernus (400)" in out
    assert "Counterspell bought at 14:44" in out


def test_match_combat_flag_hero_counters(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        custom_stats=[
            ("Celeste##RadiantDaggerTimeAt_0_stacks", 900),
            ("Celeste##RadiantDaggerTimeAt_2_stacks", 300),
            ("Apollo##HeroDamagePreventedWithUlt", 350),
        ],
    )

    run_main(tmp_path, "match", "--account", "42", "--combat")

    out = capsys.readouterr().out

    assert "Radiant Dagger uptime" in out
    assert re.search(r"0\s+15:00\s+75%", out)
    assert re.search(r"2\s+5:00\s+25%", out)
    assert "Hero damage prevented with ult: 350" in out


def test_match_combat_flag_souls_lines_and_exclusions(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        custom_stats=[
            ("Comeback Gold", 1200),
            ("Comeback Gold Koth", 267),
            ("Unspent Gold Minutes", 60000),
            ("Unspent AP Minutes", 45),
            ("PowerUp Gold", 35),
            ("Additional Wait Trooper Spawn", 0),
        ],
    )

    run_main(tmp_path, "match", "--account", "42", "--combat")

    out = capsys.readouterr().out

    assert "Comeback souls: 1,200" in out
    assert "Unstable Rift comeback: 267" in out
    assert "Souls held unspent on average: 2,000" in out
    assert "Ability points held unspent on average: 1.5" in out
    assert "PowerUp" not in out
    assert "Additional Wait Trooper Spawn" not in out


def test_match_combat_flag_without_any_stats(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "--account", "42", "--combat")

    out = capsys.readouterr().out

    assert "No combat stats for Mirage in match 100" in out


def test_match_combat_flag_ranks_the_lobby_by_aim(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        custom_stats=[
            ("Enemy Hero Accuracy##Shots", 1000),
            ("Enemy Hero Accuracy##Hits", 400),
            ("Enemy Hero Accuracy##Headshots", 100),
        ],
        damage=[
            ("citadel_weapon_hornet", [400, 700]),
            ("citadel_weapon_hornet_crit", [100, 300]),
        ],
    )

    run_main(tmp_path, "match", "--account", "42", "--combat")

    out = capsys.readouterr().out

    assert "Aim vs heroes" in out
    assert re.search(r"Mirage \*\s+ally\s+1,000\s+40\.0%\s+25\.0%\s+700\s+300", out)
    assert "Rates count heroes only" in out
    assert "two bullet series from the damage graph" in out
    assert "percentile" not in out.lower()


def test_match_scoreboard_shows_buff_totals(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        buffs=[
            ("hp_permanent_pickup", 5, True),
            ("wp_permanent_pickup_lv3", 2, True),
            ("gun_powerup_pickup", 4, False),
        ],
    )

    run_main(tmp_path, "match", "--account", "42")

    out = capsys.readouterr().out

    assert re.search(r"Denies\s+Buffs", out)
    assert re.search(r"Mirage \*.*\s7\n", out)


def test_match_souls_flag_prints_source_and_group_table(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    g = export.GoldSource
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
    assert re.search(r"Rift & Urn\s+0\s+200\s+200\s+5%", out)
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


def test_match_deaths_lists_killers_in_time_order(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000), (600, 5000)],
        death_log=((1, 2, 900), (1, 0, 310)),
    )

    run_main(tmp_path, "match", "100", "--deaths", "--account", "42")

    out = capsys.readouterr().out

    assert "Match 100: Mirage, win," in out
    assert re.search(r"Time\s+Killed by\s+Killed in\s+Distance\s+Respawn", out)
    assert re.search(r"5:10\s+not a player\s+2.5s\s+-\s+20s", out)
    assert re.search(r"15:00\s+Infernus\s+2.5s\s+10m\s+20s", out)
    assert out.index("not a player") < out.index("Infernus")


def test_match_kills_lists_victims(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000), (600, 5000)],
        death_log=((2, 1, 400), (1, 2, 900)),
    )

    run_main(tmp_path, "match", "100", "--kills", "--account", "42")

    out = capsys.readouterr().out

    assert re.search(r"Time\s+Kill\s+Killed in\s+Distance\s+Respawn", out)
    assert re.search(r"6:40\s+Infernus\s+2.5s\s+10m\s+20s", out)
    assert "Killed by" not in out


def test_match_laning_lane_blocks(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000), (600, 5000)],
        death_log=((1, 2, 310), (2, 1, 700)),
        objectives=True,
        lanes=True,
    )

    run_main(tmp_path, "match", "100", "--laning", "--account", "42")

    out = capsys.readouterr().out

    assert "Laning phase through 9:00 (stat columns read at the 5:00 snapshot)" in out
    assert re.search(
        r"Yellow \(your lane\)\n\s+Lane\s+Souls\s+Kills\s+Deaths\s+Damage\s+Taken", out
    )
    assert re.search(r"Yours\s+3,000", out)
    assert re.search(r"\* Mirage\s+3,000\s+0\s+1", out)
    assert re.search(r"Infernus\s+1,500\s+1\s+0", out)
    assert re.search(r"Net\s+\+1,500\s+-1\s+\+1", out)
    assert re.search(r"5:10\s+Infernus kills Mirage", out)
    assert "Mirage kills Infernus" not in out
    assert re.search(r"6:40\s+enemy Guardian falls", out)
    assert out.index("Infernus kills Mirage") < out.index("enemy Guardian falls")


def test_match_laning_without_lanes(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "100", "--laning", "6", "--account", "42")

    assert "No lane assignments in this match" in capsys.readouterr().out


def test_match_deaths_without_the_table(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "history")
    capsys.readouterr()
    shutil.rmtree(tmp_path / "pq" / "deaths")

    run_main(tmp_path, "match", "100", "--deaths", "--account", "42")

    assert "No deaths table yet" in capsys.readouterr().out


def test_match_kills_without_any(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "100", "--kills", "--account", "42")

    assert "No kills in this match" in capsys.readouterr().out


def test_match_id_not_found(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "999", "--account", "42")

    out = capsys.readouterr().out

    assert "Match 999 is not in the archive" in out
    assert "deadlock download --match 999" in out


def test_match_reads_downloaded_matches_from_the_players_store(capsys, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    foreign_cache = tmp_path / "foreign-cache"
    foreign_cache.mkdir()
    write_cache_entry(foreign_cache, match_id=500, account=99, stats=[(300, 4000)])
    foreign_arc = tmp_path / "foreign-arc"
    extract.archive(foreign_cache, foreign_arc)
    store = tmp_path / "players-store"
    export.export_all(foreign_arc, store)

    monkeypatch.setattr(export, "PARQUET_DIR", tmp_path / "pq")
    monkeypatch.setattr(players, "PARQUET_DIR", store)

    cfg = tmp_path / "config.toml"
    cfg.write_text('timezone = "America/Chicago"\n[accounts]\nyou = 42\n')
    args = ["--cache", str(cache), "--archive", str(tmp_path / "arc")]
    main([*args, "match", "500", "--hero", "Mirage"], config=cfg)

    out = capsys.readouterr().out

    assert "Reading match 500 from the players tables" in out
    assert "Match 500: Mirage, win," in out


def test_match_explicit_parquet_never_falls_back(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "500", "--hero", "Mirage")

    out = capsys.readouterr().out

    assert "Reading match 500" not in out
    assert "Match 500 is not in the archive" in out


def test_match_id_archived_but_not_yours(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])
    write_cache_entry(cache, match_id=200, account=99, stats=[(300, 4000)])

    run_main(tmp_path, "match", "200")

    out = capsys.readouterr().out

    assert "None of your accounts played in match 200" in out
    assert "deadlock download --match 200" in out


def test_match_hero_flag_picks_another_player(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000), (600, 5000)])

    run_main(tmp_path, "match", "100", "--hero", "Infernus")

    out = capsys.readouterr().out

    assert "Match 100: Infernus, loss," in out
    assert re.search(r"Infernus \*\s+0/0/0\s+2,500", out)
    assert re.search(r"Total\s+2,500", out)
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


def test_match_teams_lists_rift_win_your_team(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(600, 4000), (900, 6000)],
        teammates=5,
        team_gold_sources=[(900, 5, 247, 0)],
        objectives=True,
    )

    run_main(tmp_path, "match", "--account", "42", "--teams")

    out = capsys.readouterr().out

    assert "your team wins an Unstable Rift (+247 souls each)" in out


def test_match_teams_rift_win_reads_as_enemy_from_other_side(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(600, 4000), (900, 6000)],
        teammates=5,
        team_gold_sources=[(900, 5, 247, 0)],
        objectives=True,
    )

    run_main(tmp_path, "match", "--account", "77", "--teams")

    out = capsys.readouterr().out

    assert "enemy team wins an Unstable Rift (+247 souls each)" in out


def test_match_teams_lists_urn_delivery(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(600, 4000), (1800, 9000)],
        gold_sources=[(1800, 5, 2350, 0)],
        objectives=True,
    )

    run_main(tmp_path, "match", "--account", "42", "--teams")

    out = capsys.readouterr().out

    assert "your team delivers the Soul Urn (Mirage, +2,350 souls)" in out


def test_match_teams_no_objective_lines_before_rework(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        start_time=1780000000,
        stats=[(600, 4000), (1800, 9000)],
        teammates=5,
        team_gold_sources=[(900, 5, 247, 0)],
        gold_sources=[(1800, 5, 2350, 0)],
        objectives=True,
    )

    run_main(tmp_path, "match", "--account", "42", "--teams")

    out = capsys.readouterr().out

    assert "Unstable Rift" not in out
    assert "Soul Urn" not in out


def test_rift_minute_inverts_the_bounty():
    assert performance._rift_minute(247) == 13.0
    assert performance._rift_minute(284) == 14.0
    assert performance._rift_minute(432) == 18.0


def test_urn_minute_inverts_the_bounty():
    assert performance._urn_minute(950) == 10.0
    assert performance._urn_minute(2350) == 30.0


def test_detect_rift_reads_the_shared_payout():
    assert performance._detect_rift([247] * 6, 6, 0, 1800) == 247


def test_detect_rift_allows_one_urn_runner_in_the_window():
    assert performance._detect_rift([247, 247, 247, 247, 247, 3000], 6, 0, 1800) == 247


def test_detect_rift_subtracts_the_comeback_bonus():
    assert performance._detect_rift([574] * 6, 6, 327, 1800) == 574


def test_detect_rift_ignores_a_split_window():
    assert performance._detect_rift([247, 247, 247, 100, 200, 300], 6, 0, 1800) is None


def test_detect_rift_rejects_an_off_formula_amount():
    assert performance._detect_rift([364] * 6, 6, 0, 1800) is None


def test_detect_rift_rejects_a_payout_before_the_first_spawn():
    assert performance._detect_rift([54] * 6, 6, 0, 1800) is None


def test_detect_rift_rejects_a_payout_past_the_final_whistle():
    assert performance._detect_rift([987] * 6, 6, 0, 900) is None


def test_detect_urn_names_the_solo_runner():
    assert performance._detect_urn([2350], ["Mirage"], 0, 1800) == ("Mirage", 2350)


def test_detect_urn_sets_aside_a_shared_rift_payout():
    gains = [247, 247, 247, 247, 247, 2597]
    heroes = ["A", "B", "C", "D", "E", "Runner"]

    assert performance._detect_urn(gains, heroes, 247, 1800) == ("Runner", 2350)


def test_detect_urn_picks_the_runner_over_orb_sharers():
    assert performance._detect_urn([2000, 300], ["Runner", "Ally"], 0, 1800) == ("Runner", 2000)


def test_detect_urn_ignores_small_treasure_gains():
    assert performance._detect_urn([500], ["Mirage"], 0, 1800) is None


def test_detect_urn_rejects_a_bounty_past_the_final_whistle():
    assert performance._detect_urn([2350], ["Mirage"], 0, 1200) is None


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

    with pytest.raises(SystemExit):
        build_parser(tmp_path / "config.toml").parse_args(["match", "--items", "--abilities"])

    with pytest.raises(SystemExit):
        build_parser(tmp_path / "config.toml").parse_args(["match", "--accolades", "--items"])

    with pytest.raises(SystemExit):
        build_parser(tmp_path / "config.toml").parse_args(["match", "--buffs", "--souls"])


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


def test_winrate_abandon_footer(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, won=False, abandon_s=700)
    write_cache_entry(cache, match_id=101)

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    assert "Abandons" in out.splitlines()[2]
    assert "Abandons: 1 game — you left 1 (0-1)." in out
    assert "Without them: 1 games, 1-0, 100.0% win rate." in out


def test_winrate_abandon_footer_notes(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        abandon_s=100,
        stats=((300, 3000), (600, 6000)),
        damage=(("citadel_weapon_mirage", [100, 250]),),
    )
    write_cache_entry(cache, match_id=101, won=False, not_scored=True)

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    assert "Overall: 1 games, 1-0" in out
    assert "Abandons: 1 game — you left 1 (1-0)." in out
    assert "1 leaver reconnected and finished." in out
    assert "Not scored: 1 game left out of the table (safe to leave), 0-1 in match history." in out
    assert "Without them" not in out


def test_winrate_unscored_only_window(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, not_scored=True)

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    assert "No games found for the configured accounts" in out
    assert "Not scored: 1 game left out of the table (safe to leave), 1-0 in match history." in out


def test_winrate_lobby_column(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, badges=(95, 91))

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    assert "Lobby" in out.splitlines()[2]
    assert "Phantom 3" in out
    assert "Phantom 3 lobbies." in out


def test_winrate_lobby_blank_without_badges(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    assert "lobbies" not in out


def test_winrate_no_abandon_footer_without_abandons(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    assert "Abandons:" not in out
    assert "Not scored:" not in out


def test_laning_command_prints_rate_tables(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=((540, 3000),), lanes=True, won=True)
    write_cache_entry(
        cache, match_id=101, stats=((540, 1000),), enemy_worth=4000, lanes=True, won=False
    )

    run_main(tmp_path, "laning", "--account", "42")

    out = capsys.readouterr().out

    assert "Lane result at 9:00" in out
    assert "ahead 1k-3k" in out
    assert "won lane" in out
    assert "lost lane" in out
    assert "Your deaths by 9:00" in out
    assert "Worst teammate deaths by 9:00" in out
    assert "Overall: 2 games, 1-1, 50.0% win rate." in out


def test_laning_command_labels_a_tied_lane(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache, match_id=100, stats=((540, 2000),), enemy_worth=2000, lanes=True, won=True
    )

    run_main(tmp_path, "laning", "--account", "42")

    out = capsys.readouterr().out

    assert "even lane" in out
    assert "lost lane" not in out


def test_laning_command_drops_a_match_without_a_lane_snapshot(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=((540, 3000),), lanes=True, won=True)
    write_cache_entry(cache, match_id=101, stats=((900, 3000),), lanes=True, won=False)

    run_main(tmp_path, "laning", "--account", "42")

    out = capsys.readouterr().out

    assert "Overall: 1 games, 1-0, 100.0% win rate." in out


def test_laning_command_minutes_widens_the_window(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=((540, 1000), (900, 5000)), lanes=True)

    run_main(tmp_path, "laning", "--account", "42", "--minutes", "15")

    out = capsys.readouterr().out

    assert "Lane result at 15:00" in out
    assert "ahead 1k-3k" in out


def test_laning_command_without_account_prints_hint(capsys, tmp_path):
    run_main(tmp_path, "laning", accounts=None)

    out = capsys.readouterr().out

    assert "No account set" in out


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
    monkeypatch.setattr(snapshots, "refresh_heroes", lambda *a, **k: 57)
    monkeypatch.setattr(snapshots, "refresh_items", lambda *a, **k: 251)
    monkeypatch.setattr(snapshots, "refresh_abilities", lambda *a, **k: 0)
    monkeypatch.setattr(snapshots, "refresh_skill_rating", lambda *a, **k: 0)
    monkeypatch.setattr(snapshots, "refresh_accolades", lambda *a, **k: 0)
    monkeypatch.setattr(snapshots, "refresh_statues", lambda *a, **k: 0)
    monkeypatch.setattr(snapshots, "history_lags", lambda **k: [])

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
                "party": 0,
                "abandon_time_s": None,
            }
            for i in range(6)
        ],
    ).write_parquet(tmp_path / "players.parquet")

    main(["--parquet", str(tmp_path), "schema", "players", "--sample"], config=tmp_path / "c.toml")

    out = capsys.readouterr().out

    assert "account_id" in out
    assert "Sample rows from" in out
    assert "Mirage" in out
    assert "shape: (5, 18)" in out


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

    assert "Added" not in out
    assert "Archive" not in out
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

    written = sorted(p.stat().st_mtime_ns for p in (pq / "matches").rglob("*.parquet"))

    main(
        ["--cache", str(cache), "--archive", str(arc), "--parquet", str(pq), "history"], config=cfg
    )

    assert "100" in capsys.readouterr().out
    assert sorted(p.stat().st_mtime_ns for p in (pq / "matches").rglob("*.parquet")) == written


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


def test_ability_command_spirit_resolves_scaling(capsys, tmp_path):
    main(["ability", "Dust Devil", "--spirit", "100"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "at 100 spirit" in out
    assert "at level" not in out
    assert "damage 155 -> 215" in out


def test_ability_command_spirit_rejects_souls_and_level(capsys, tmp_path):
    main(
        ["ability", "Dust Devil", "--spirit", "100", "--souls", "25000"],
        config=tmp_path / "none.json",
    )

    out = capsys.readouterr().out

    assert "already includes boons" in out
    assert "Dust Devil  (Mirage ability)" not in out

    main(
        ["ability", "Dust Devil", "--spirit", "100", "--level", "20"], config=tmp_path / "none.json"
    )

    assert "already includes boons" in capsys.readouterr().out


def test_ability_command_spirit_with_as_of_shows_old_scaling(capsys, tmp_path):
    main(
        ["ability", "Dust Devil", "--spirit", "100", "--as-of", "2026-07-08"],
        config=tmp_path / "none.json",
    )

    assert "damage 155 -> 255" in capsys.readouterr().out


def test_ability_command_melee_resolves_scaling(capsys, tmp_path):
    main(["ability", "Bashdown", "--melee", "80"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "at 80 light melee" in out
    assert "at level" not in out
    assert "melee damage                               72  (0.9 x light melee)" in out
    assert "heavy melee damage 0 -> 92.8" in out


def test_ability_command_melee_rejects_souls_and_level(capsys, tmp_path):
    main(
        ["ability", "Bashdown", "--melee", "80", "--souls", "25000"],
        config=tmp_path / "none.json",
    )

    out = capsys.readouterr().out

    assert "--melee is the total" in out
    assert "Bashdown  (Billy ability)" not in out

    main(["ability", "Bashdown", "--melee", "80", "--level", "20"], config=tmp_path / "none.json")

    assert "--melee is the total" in capsys.readouterr().out


def test_ability_command_spirit_and_melee_combine(capsys, tmp_path):
    main(["ability", "Bashdown", "--spirit", "100", "--melee", "80"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "at 100 spirit, 80 light melee" in out
    assert "(1.1 x spirit)" in out
    assert "(0.9 x light melee)" in out


def test_ability_command_weapon_resolves_scaling(capsys, tmp_path):
    main(["ability", "Gutshot", "--weapon", "58"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "at 58% weapon damage" in out
    assert "damage                                  100.6  (0.7 x % weapon damage)" in out
    assert "bonus damage                             76.4  (0.8 x % weapon damage)" in out
    assert "damage 100.6 -> 125.6" in out


def test_ability_command_weapon_combines_with_souls(capsys, tmp_path):
    main(
        ["ability", "Gutshot", "--weapon", "58", "--souls", "25000"], config=tmp_path / "none.json"
    )

    out = capsys.readouterr().out

    assert "already includes boons" not in out
    assert "at level" in out
    assert "58% weapon damage" in out


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
    assert "Passive" in out
    assert (
        "cooldown                                  15s  (11.25s with Transcendent Cooldown)" in out
    )
    assert "fire rate" in out
    assert "win rate" not in out


def test_item_command_card_shows_active_section(capsys, tmp_path):
    main(["item", "Echo Shard"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "Active\n" in out
    assert "Reset the cooldown" in out
    assert (
        "cooldown                                  35s  (26.25s with Transcendent Cooldown)" in out
    )


def test_item_command_unknown_item(capsys, tmp_path):
    main(["item", "No Such Trinket"], config=tmp_path / "none.json")

    assert "Unknown item" in capsys.readouterr().out


def test_item_card_shows_cooldown_reduced_value(capsys, tmp_path):
    main(["item", "Siphon Bullets"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "max frequency" in out
    assert "1.2s  (0.9s with Transcendent Cooldown)" in out


def test_item_card_shows_cooldown_as_line_item(capsys, tmp_path):
    main(["item", "Metal Skin"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "Active\n" in out
    assert "cooldown" in out
    assert "24s  (18s with Transcendent Cooldown)" in out
    assert out.count("18s") == 1


def test_item_card_keeps_cooldown_when_outside_section_props(capsys, tmp_path):
    main(["item", "Mercurial Magnum"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "cooldown" in out
    assert "15s  (11.25s with Transcendent Cooldown)" in out
    assert out.count("cooldown ") == 1


def test_item_card_marks_conditional_stat(capsys, tmp_path):
    main(["item", "Close Quarters"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "weapon damage" in out
    assert "within Range" in out


def test_item_stat_line_applies_display_prefix():
    it = items.Item(
        id=1,
        name="Slow Thing",
        class_name="x",
        cost=0,
        slot="spirit",
        tier=1,
        is_active=True,
        properties={"slow_percent": 20, "bonus_souls": 180},
        labels={
            "slow_percent": {"label": "Move Speed", "postfix": "%", "prefix": "-"},
            "bonus_souls": {"label": "Bonus Souls", "postfix": "%", "prefix": "+"},
        },
    )

    slow = cards._item_stat_line(it, "slow_percent", "  ")
    souls = cards._item_stat_line(it, "bonus_souls", "  ")

    assert slow is not None
    assert souls is not None
    assert "-20%" in slow
    assert "+180%" in souls


def test_item_card_shows_slow_as_negative(capsys, tmp_path):
    main(["item", "Slowing Hex"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "move speed" in out
    assert "-20%" in out


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


def test_item_command_notes_when_tracked_players_never_bought_it(monkeypatch, capsys, tmp_path):
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
    monkeypatch.setattr(cli_items.queries, "table_exists", lambda *a, **kw: True)
    monkeypatch.setattr(
        cli_items.queries,
        "item_value",
        lambda *a, **kw: {"builds": 0, "per_min": 0.0, "percent_of_hero_damage": 0.0},
    )

    def no_api(*a, **kw):
        raise ValueError("no api data")

    monkeypatch.setattr(cli_items.meta, "get_item_stats", no_api)

    cfg = tmp_path / "config.toml"
    cfg.write_text("[players.Mirage]\npro = 11\n")

    args = argparse.Namespace(
        item="Mystic Shot",
        hero="Mirage",
        account=[42],
        parquet=str(tmp_path),
        top=10,
        min_rating="Eternus",
        since=None,
    )
    cli_items.item_report(args, cfg)

    assert "none of their downloaded games bought Mystic Shot" in capsys.readouterr().out


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

    out = capsys.readouterr().out

    assert "No players tracked for Lady Geist" in out
    assert 'deadlock download --hero "Lady Geist"' in out


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


def _stub_refreshes(monkeypatch):
    for fn in (
        "refresh_heroes",
        "refresh_items",
        "refresh_abilities",
        "refresh_skill_rating",
        "refresh_accolades",
        "refresh_statues",
    ):
        monkeypatch.setattr(snapshots, fn, lambda *a, **k: 0)


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
