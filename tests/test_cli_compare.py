import datetime as dt
import re

import polars as pl
import pytest
from cli_helpers import run_main, write_cache_entry

from deadlock_matches import (
    export,
    extract,
    players,
)
from deadlock_matches.cli import compare as cli_compare
from deadlock_matches.extract import pb


@pytest.fixture(autouse=True)
def no_installed_client(monkeypatch):
    monkeypatch.setattr(extract, "installed_client_version", lambda cache_dir=None: None)


def test_compare_without_account_prints_hint(capsys, tmp_path):
    run_main(tmp_path, "compare", "souls", "--hero", "Haze", accounts=None)

    out = capsys.readouterr().out

    assert "config.toml" in out
    assert "--account" in out


def _pool_game(match_id, paths=False):
    info = pb.CMsgMatchMetaDataContents().match_info
    info.match_id = match_id
    info.start_time = 1783000000
    info.duration_s = 1800
    info.winning_team = pb.k_ECitadelLobbyTeam_Team1
    info.match_mode = pb.k_ECitadelMatchMode_Unranked
    info.game_mode = pb.k_ECitadelGameMode_Normal

    tp = info.players.add()
    tp.account_id = 11
    tp.hero_id = 52
    tp.team = pb.k_ECitadelLobbyTeam_Team1
    tp.player_slot = 1

    for t, worth in [(180, 3000), (360, 6000)]:
        s = tp.stats.add()
        s.time_stamp_s = t
        s.net_worth = worth

    if paths:
        mp = info.match_paths
        mp.interval_s = 1.0
        mp.x_resolution = 100
        mp.y_resolution = 100

        track = mp.paths.add()
        track.player_slot = tp.player_slot
        track.x_max = 10000.0
        track.y_max = 10000.0
        track.x_pos.extend(range(10))
        track.y_pos.extend([0] * 10)
        track.health.extend([100] * 10)
        track.combat_type.extend([1] * 4 + [0] * 6)
        track.move_type.extend([0, 4, 4, 3, 0, 7, 8, 7, 6, 0])

    return info


def _pool_game_for_account(
    match_id, account, stats, damage=(), custom_stats=(), start_time=1783000000
):
    info = pb.CMsgMatchMetaDataContents().match_info
    info.match_id = match_id
    info.start_time = start_time
    info.duration_s = 1800
    info.winning_team = pb.k_ECitadelLobbyTeam_Team1
    info.match_mode = pb.k_ECitadelMatchMode_Unranked
    info.game_mode = pb.k_ECitadelGameMode_Normal

    player = info.players.add()
    player.account_id = account
    player.hero_id = 52
    player.team = pb.k_ECitadelLobbyTeam_Team1
    player.player_slot = 1

    enemy = info.players.add()
    enemy.account_id = 77
    enemy.hero_id = 1
    enemy.team = pb.k_ECitadelLobbyTeam_Team0
    enemy.player_slot = 2

    for t, worth in stats:
        sample = player.stats.add()
        sample.time_stamp_s = t
        sample.net_worth = worth

    for stat_id, (name, _) in enumerate(custom_stats, start=1):
        reg = info.custom_user_stats.add()
        reg.name = name
        reg.id = stat_id

    for stat_id, (_, value) in enumerate(custom_stats, start=1):
        cs = player.stats[-1].custom_user_stats.add()
        cs.id = stat_id
        cs.value = value

    if damage:
        dm = info.damage_matrix
        dm.sample_time_s.extend([300, 600])
        dealer = dm.damage_dealers.add()
        dealer.dealer_player_slot = 1

        for j, entry in enumerate(damage):
            name, values, *rest = entry
            dm.source_details.source_name.append(name)
            dm.source_details.stat_type.append(rest[0] if rest else 0)

            src = dealer.damage_sources.add()
            src.source_details_index = j
            target = src.damage_to_players.add()
            target.target_player_slot = 2
            target.damage.extend(values)

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
    monkeypatch.setattr(players, "PLAYERS_PARQUET_DIR", store)

    run_main(
        tmp_path,
        "compare",
        "souls",
        "--hero",
        "Mirage",
        extra="[players.Mirage]\npro = 11\n",
    )

    out = capsys.readouterr().out

    assert "You (you, 3 Mirage games) vs 1 tracked Mirage player (3 Mirage games): souls" in out
    assert re.search(r"you\s+3\s+-\s+67\s+67", out)
    assert re.search(r"pro\s+3\s+2026-07-01\s+200\s+200", out)
    assert re.search(r"0-5\s+200\s+600\s+-400\s+-2,000\s+3/3", out)
    assert re.search(r"5-10\s+200\s+600\s+-400\s+-4,000\s+3/3", out)
    assert re.search(r"10-15\s+0\s+0\s+\+0\s+-4,000\s+3/3", out)
    assert re.search(r"Total\s+67\s+200\s+-133", out)
    assert "Biggest souls gap: 0-5m, you 200/min vs tracked players 600/min" in out


def test_compare_command_excludes_the_subject_from_the_pool(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(export, "PARQUET_DIR", tmp_path / "pq")

    store = tmp_path / "players-pq"
    monkeypatch.setattr(players, "PLAYERS_PARQUET_DIR", store)

    def downloaded_game(match_id, archive_dir=None):
        if match_id < 910:
            return _pool_game_for_account(match_id, 11, [(180, 1000), (360, 2000)])

        return _pool_game_for_account(match_id, 12, [(180, 3000), (360, 6000)])

    monkeypatch.setattr(players, "match_info", downloaded_game)
    ledger = [
        {
            "match_id": match_id,
            "account_id": account,
            "player": player,
            "hero_id": 52,
            "rank": 2,
            "region": "Asia",
            "downloaded_at": dt.datetime(2026, 7, 1, tzinfo=dt.UTC),
        }
        for player, account, match_ids in (
            ("pro", 11, (900, 901, 902)),
            ("rival", 12, (910, 911, 912)),
        )
        for match_id in match_ids
    ]
    players.write_player_tables(ledger, out_dir=store)

    run_main(
        tmp_path,
        "compare",
        "souls",
        "--hero",
        "Mirage",
        "--account",
        "pro",
        extra="[players.Mirage]\npro = 11\nrival = 12\n",
    )

    out = capsys.readouterr().out

    assert "You (pro, 3 Mirage games) vs 1 tracked Mirage player (3 Mirage games): souls" in out
    assert "you 200/min vs tracked players 600/min" in out


def test_compare_command_against_filters_the_pool(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "cache"
    cache.mkdir()

    for match_id in (100, 101, 102):
        write_cache_entry(cache, match_id=match_id, stats=[(180, 1000), (360, 2000)])

    def downloaded_game(match_id, archive_dir=None):
        if match_id < 910:
            return _pool_game_for_account(match_id, 11, [(180, 1000), (360, 2000)])

        return _pool_game_for_account(match_id, 12, [(180, 3000), (360, 6000)])

    monkeypatch.setattr(players, "match_info", downloaded_game)
    store = tmp_path / "players-pq"
    ledger = [
        {
            "match_id": match_id,
            "account_id": account,
            "player": player,
            "hero_id": 52,
            "rank": 2,
            "region": "Asia",
            "downloaded_at": dt.datetime(2026, 7, 1, tzinfo=dt.UTC),
        }
        for player, account, match_ids in (
            ("pro", 11, (900, 901, 902)),
            ("rival", 12, (910, 911, 912)),
        )
        for match_id in match_ids
    ]
    players.write_player_tables(ledger, out_dir=store)
    monkeypatch.setattr(players, "PLAYERS_PARQUET_DIR", store)

    run_main(
        tmp_path,
        "compare",
        "souls",
        "--hero",
        "Mirage",
        "--against",
        "rival",
        extra="[players.Mirage]\npro = 11\nrival = 12\n",
    )

    out = capsys.readouterr().out

    assert "You (you, 3 Mirage games) vs 1 tracked Mirage player (3 Mirage games): souls" in out
    assert "you 200/min vs tracked players 600/min" in out


def test_compare_command_pool_since_filters_the_pool(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "cache"
    cache.mkdir()

    for match_id in (100, 101, 102):
        write_cache_entry(cache, match_id=match_id, stats=[(180, 1000), (360, 2000)])

    starts = {
        900: int(dt.datetime(2026, 7, 13, 12, tzinfo=dt.UTC).timestamp()),
        901: int(dt.datetime(2026, 7, 15, 12, tzinfo=dt.UTC).timestamp()),
        902: int(dt.datetime(2026, 7, 16, 12, tzinfo=dt.UTC).timestamp()),
        903: int(dt.datetime(2026, 7, 17, 12, tzinfo=dt.UTC).timestamp()),
    }

    monkeypatch.setattr(
        players,
        "match_info",
        lambda match_id, archive_dir=None: _pool_game_for_account(
            match_id,
            11,
            [(180, 3000), (360, 6000)],
            start_time=starts[match_id],
        ),
    )
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
        for match_id in (900, 901, 902, 903)
    ]
    players.write_player_tables(ledger, out_dir=store)
    monkeypatch.setattr(players, "PLAYERS_PARQUET_DIR", store)

    run_main(
        tmp_path,
        "compare",
        "souls",
        "--hero",
        "Mirage",
        "--pool-since",
        "2026-07-15",
        extra="[players.Mirage]\npro = 11\n",
    )

    out = capsys.readouterr().out

    assert "vs 1 tracked Mirage player (3 Mirage games since 2026-07-15): souls" in out
    assert re.search(r"pro\s+3\s+2026-07-01\s+200\s+200", out)
    assert re.search(r"0-5\s+200\s+600\s+-400\s+-2,000\s+3/3", out)


def test_compare_command_milestones(tmp_path, monkeypatch, capsys):
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
    monkeypatch.setattr(players, "PLAYERS_PARQUET_DIR", store)

    run_main(
        tmp_path,
        "compare",
        "souls",
        "--hero",
        "Mirage",
        "--milestones",
        extra="[players.Mirage]\npro = 11\n",
    )

    out = capsys.readouterr().out

    assert "Minutes to reach a net worth, median across games" in out
    assert "You: you, 3 Mirage games     Them: 3 Mirage games" in out
    assert re.search(r"1600\s+4\.8\s+1\.6\s+\+3\.2\s+3/3", out)


def test_compare_command_damage_stat_prints_sources_first(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(export, "PARQUET_DIR", tmp_path / "pq")
    cache = tmp_path / "cache"
    cache.mkdir()

    for match_id in (100, 101, 102):
        write_cache_entry(
            cache,
            match_id=match_id,
            stats=[(180, 1000), (360, 2000)],
            damage=(
                ("citadel_weapon_mirage", [100, 250]),
                ("mirage_tornado", [50, 100]),
                ("upgrade_toxic_bullets", [40, 50]),
            ),
        )

    def downloaded_game(match_id, archive_dir=None):
        return _pool_game_for_account(
            match_id,
            11,
            [(180, 3000), (360, 6000)],
            damage=(
                ("citadel_weapon_mirage", [300, 600]),
                ("mirage_tornado", [200, 400]),
                ("upgrade_toxic_bullets", [100, 200]),
            ),
        )

    monkeypatch.setattr(players, "match_info", downloaded_game)
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
    monkeypatch.setattr(players, "PLAYERS_PARQUET_DIR", store)

    run_main(
        tmp_path,
        "compare",
        "damage",
        "--hero",
        "Mirage",
        extra="[players.Mirage]\npro = 11\n",
    )

    out = capsys.readouterr().out

    assert "Damage to heroes by source" in out
    assert re.search(
        r"Delivery\s+You/game\s+Them/game\s+Gap/game\s+You/min\s+Them/min\s+Gap/min", out
    )
    assert re.search(r"Total\s+400\s+1,200\s+-800\s+13\s+40\s+-27", out)
    assert "citadel_weapon_mirage" in out
    assert "Toxic Bullets" in out
    assert "Damage over time" in out
    assert re.search(r"citadel_weapon_mirage\s+Gun\s+250\s+600\s+-350\s+8\.33\s+20\s+-12", out)
    assert re.search(r"Total\s+400\s+1,200\s+-800\s+13\s+40\s+-27\s+-\s+-\s+3/3", out)


def test_compare_command_healing_stat_prints_sources_first(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(export, "PARQUET_DIR", tmp_path / "pq")
    cache = tmp_path / "cache"
    cache.mkdir()

    for match_id in (100, 101, 102):
        write_cache_entry(
            cache,
            match_id=match_id,
            stats=[(180, 1000), (360, 2000)],
            damage=(("mirage_tornado", [50, 100], 1),),
        )

    def downloaded_game(match_id, archive_dir=None):
        return _pool_game_for_account(
            match_id,
            11,
            [(180, 3000), (360, 6000)],
            damage=(("mirage_tornado", [100, 300], 1),),
        )

    monkeypatch.setattr(players, "match_info", downloaded_game)
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
    monkeypatch.setattr(players, "PLAYERS_PARQUET_DIR", store)

    run_main(
        tmp_path,
        "compare",
        "healing",
        "--hero",
        "Mirage",
        extra="[players.Mirage]\npro = 11\n",
    )

    out = capsys.readouterr().out

    assert "Healing by source" in out
    assert "Dust Devil" in out
    assert "Healing over time" in out
    assert re.search(r"Dust Devil\s+Abilities\s+100\s+300\s+-200\s+3\.33\s+10\s+-6\.67", out)
    assert re.search(r"Total\s+100\s+300\s+-200\s+3\.33\s+10\s+-6\.67\s+-\s+-\s+3/3", out)


def test_compare_command_combat_stat_prints_aggregate_table(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "cache"
    cache.mkdir()
    mine_stats = [
        ("Enemy Hero Accuracy##Shots", 100),
        ("Enemy Hero Accuracy##Hits", 25),
        ("Enemy Hero Accuracy##Headshots", 5),
        ("Enemy Hero Accuracy - Incoming##Shots", 80),
        ("Enemy Hero Accuracy - Incoming##Hits", 20),
        ("Parry Success", 3),
    ]

    for match_id in (100, 101, 102):
        write_cache_entry(
            cache,
            match_id=match_id,
            stats=[(180, 1000), (360, 2000)],
            damage=(("citadel_weapon_mirage", [100, 250]),),
            custom_stats=mine_stats,
        )

    pool_stats = [
        ("Enemy Hero Accuracy##Shots", 200),
        ("Enemy Hero Accuracy##Hits", 100),
        ("Enemy Hero Accuracy##Headshots", 30),
        ("Enemy Hero Accuracy - Incoming##Shots", 60),
        ("Enemy Hero Accuracy - Incoming##Hits", 15),
        ("Parry Success", 6),
    ]

    monkeypatch.setattr(
        players,
        "match_info",
        lambda match_id, archive_dir=None: _pool_game_for_account(
            match_id,
            11,
            [(180, 3000), (360, 6000)],
            damage=(("citadel_weapon_mirage", [300, 600]),),
            custom_stats=pool_stats,
        ),
    )
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
    monkeypatch.setattr(export, "PARQUET_DIR", tmp_path / "pq")
    monkeypatch.setattr(players, "PLAYERS_PARQUET_DIR", store)

    run_main(
        tmp_path,
        "compare",
        "combat",
        "--hero",
        "Mirage",
        extra="[players.Mirage]\npro = 11\n",
    )

    out = capsys.readouterr().out

    assert "You (you, 3 Mirage games) vs 1 tracked Mirage player (3 Mirage games): combat" in out
    assert re.search(r"Metric\s+You\s+Them\s+Gap", out)
    assert re.search(r"Hero hit %\s+25\.0%\s+50\.0%\s+-25\.0%", out)
    assert re.search(r"Hero shots /game\s+100\.0\s+200\.0\s+-100\.0", out)
    assert re.search(r"Gun damage /game\s+250\.0\s+600\.0\s+-350\.0", out)
    assert re.search(r"Gun damage /hit\s+10\.0\s+6\.0\s+\+4\.0", out)
    assert re.search(r"Parries /game\s+3\.0\s+6\.0\s+-3\.0", out)


def _fast_pool_game(match_id):
    """A pool game whose player covers twice the ground, so the gap has a side to fall on."""
    info = _pool_game(match_id, paths=True)
    track = info.match_paths.paths[0]

    del track.x_pos[:]
    track.x_pos.extend(range(0, 20, 2))

    return info


def test_compare_command_movement_stat(tmp_path, monkeypatch, capsys):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(180, 1000), (360, 2000)], paths=True)

    monkeypatch.setattr(players, "match_info", lambda mid, archive_dir=None: _fast_pool_game(mid))
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
    monkeypatch.setattr(players, "PLAYERS_PARQUET_DIR", store)

    run_main(
        tmp_path,
        "compare",
        "movement",
        "--hero",
        "Mirage",
        extra="[players.Mirage]\npro = 11\n",
    )

    out = capsys.readouterr().out

    assert "You (you, 1 Mirage game) vs 1 tracked Mirage player (3 Mirage games): movement" in out
    assert "Last download" in out
    assert "Rank" not in out
    assert re.search(r"pro\s+3\s+2026-07-01", out)
    assert "meters /min" in out
    assert "fighting players %" in out
    assert re.search(r"Metric\s+You\s+Tracked\s+Gap", out)
    assert re.search(r"meters /min\s+152\.4\s+304\.8\s+-152\.4", out)
    assert re.search(r"slide %\s+20\.0\s+20\.0\s+\+0\.0", out)
    assert re.search(r"m /min\s+Stationary\s+Slide", out)
    assert re.search(r"you\s+-\s+1\s+152\.4", out)
    assert re.search(r"pro\s+11\s+3\s+304\.8", out)


def test_compare_command_without_tracked_players_prints_hint(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(players, "PLAYERS_PARQUET_DIR", tmp_path / "players-pq")
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(180, 1000)])

    run_main(tmp_path, "compare", "souls", "--hero", "Mirage")

    out = capsys.readouterr().out

    assert "No players tracked for Mirage" in out
    assert "deadlock leaderboard" in out


def test_compare_command_without_downloads_prints_hint(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(players, "PLAYERS_PARQUET_DIR", tmp_path / "players-pq")
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(180, 1000)])

    run_main(tmp_path, "compare", "souls", "--hero", "Mirage", extra="[players.Mirage]\npro = 11\n")

    out = capsys.readouterr().out

    assert "No downloaded games from the tracked Mirage players yet" in out
    assert 'deadlock download --hero "Mirage"' in out


def test_movement_by_player_table(capsys):
    metrics = {
        "meters_min": 400.0,
        "stationary_percent": 7.0,
        "slide_percent": 8.0,
        "in_air_percent": 20.0,
        "zipline_percent": 9.0,
        "combat_percent": 25.0,
        "dashes_min": 2.0,
        "air_dashes_min": 0.5,
    }
    you = pl.DataFrame([{**metrics, "meters_min": 350.0}])
    top = pl.DataFrame(
        [
            {"match_id": 900, "account_id": 11, **metrics},
            {"match_id": 901, "account_id": 22, **metrics},
            {"match_id": 902, "account_id": 33, **metrics},
        ]
    )
    cli_compare._movement_by_player(you, top, labels={11: "Someone", 22: "other", 33: "스노우맨"})

    out = capsys.readouterr().out

    assert "Rank" not in out
    assert re.search(r"you\s+-\s+1\s+350\.0", out)
    assert re.search(r"Someone\s+11\s+1\s+400\.0", out)
    assert re.search(r"other\s+22\s+1\s+400\.0", out)
    assert re.search(r"스노우맨\s+33\s+1\s+400\.0", out)


def test_fit_name_counts_wide_characters_double():
    assert cli_compare._fit_name("스노우맨", 14) == "스노우맨" + " " * 6
    assert cli_compare._fit_name("스노우맨", 6) == "스노우"
    assert cli_compare._fit_name("a-very-long-player-name", 14) == "a-very-long-pl"
