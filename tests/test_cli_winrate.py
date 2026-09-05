import re

import pytest
from cli_helpers import run_main, split_era_cache, write_cache_entry

from deadlock_matches import (
    extract,
)
from deadlock_matches.assets import (
    heroes,
)
from deadlock_matches.cli import winrate as cli_winrate
from deadlock_matches.cli.main import (
    main,
)
from deadlock_matches.extract import pb


@pytest.fixture(autouse=True)
def no_installed_client(monkeypatch):
    monkeypatch.setattr(extract, "installed_client_version", lambda cache_dir=None: None)


def test_winrate_without_account_prints_hint(capsys, tmp_path):
    run_main(tmp_path, "winrate", accounts=None)

    assert "--account" in capsys.readouterr().out


def test_winrate_prints_weekly_table_by_default(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, won=False)
    write_cache_entry(cache, match_id=101, start_time=1783000000 + 86400)
    write_cache_entry(cache, match_id=102, start_time=1783000000 + 86400)

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    assert "grouped by America/Chicago week" in out
    assert "Cumulative net" in out
    assert "Overall: 3 games, 2-1, 66.7% win rate, +1 net wins, 0 MVP, 0 Key Player." in out


def test_winrate_by_day_prints_one_row_per_day(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, won=False)
    write_cache_entry(cache, match_id=101, start_time=1783000000 + 86400)
    write_cache_entry(cache, match_id=102, start_time=1783000000 + 86400)

    run_main(tmp_path, "winrate", "--account", "42", "--by", "day")

    out = capsys.readouterr().out
    rows = [line for line in out.splitlines() if line.startswith("  2026-")]

    assert "grouped by America/Chicago day" in out
    assert len(rows) == 2
    assert "Overall: 3 games, 2-1, 66.7% win rate, +1 net wins, 0 MVP, 0 Key Player." in out


def test_winrate_leaves_street_brawl_out_by_default(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)
    write_cache_entry(cache, match_id=101, won=False, game_mode=pb.k_ECitadelGameMode_StreetBrawl)

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    assert "Overall: 1 games, 1-0, 100.0% win rate" in out


def test_winrate_street_brawl_flag_swaps_the_games_in(capsys, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)
    write_cache_entry(cache, match_id=101, won=False, game_mode=pb.k_ECitadelGameMode_StreetBrawl)
    monkeypatch.setattr(
        cli_winrate.meta,
        "get_hero_stats",
        lambda **kwargs: pytest.fail("public normal-mode baseline must stay out of Street Brawl"),
    )

    run_main(
        tmp_path,
        "winrate",
        "--account",
        "42",
        "--hero",
        "Mirage",
        "--street-brawl",
    )

    out = capsys.readouterr().out

    assert "Overall: 1 games, 0-1, 0.0% win rate" in out


def test_winrate_private_lobby_flag_swaps_the_games_in(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)
    write_cache_entry(
        cache,
        match_id=101,
        won=False,
        match_mode=pb.k_ECitadelMatchMode_PrivateLobby,
    )

    run_main(tmp_path, "winrate", "--account", "42", "--private-lobby")

    out = capsys.readouterr().out

    assert "Overall: 1 games, 0-1, 0.0% win rate" in out


def test_winrate_default_spans_both_queue_eras(capsys, tmp_path):
    split_era_cache(tmp_path)

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    assert "Overall: 2 games, 2-0, 100.0% win rate" in out


def test_winrate_standard_flag_keeps_only_the_unranked_queue(capsys, tmp_path):
    split_era_cache(tmp_path)

    run_main(tmp_path, "winrate", "--account", "42", "--standard")

    out = capsys.readouterr().out

    assert "Overall: 1 games, 0-1, 0.0% win rate" in out


def test_winrate_ranked_flag_leaves_out_the_older_ranked_queue(capsys, tmp_path):
    split_era_cache(tmp_path)

    run_main(tmp_path, "winrate", "--account", "42", "--ranked")

    out = capsys.readouterr().out

    assert "Overall: 1 games, 1-0, 100.0% win rate" in out


def test_winrate_by_mode_splits_standard_on_the_queue_split(capsys, tmp_path):
    split_era_cache(tmp_path)

    run_main(tmp_path, "winrate", "--by", "mode", "--account", "42")

    out = capsys.readouterr().out

    assert re.search(r"Standard \(ranked\)\s+1\s+1\s+0\s+100\.0%", out)
    assert re.search(r"Standard \(unranked\)\s+1\s+0\s+1\s+0\.0%", out)
    assert re.search(r"Ranked\s+1\s+1\s+0\s+100\.0%", out)


def test_winrate_points_column_follows_the_games_not_the_flag(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, start_time=1783000000)

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    assert "Net points" not in out
    assert "net points" not in out


def test_winrate_by_mode_honors_account_and_hero(capsys, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    private = pb.k_ECitadelMatchMode_PrivateLobby
    brawl = pb.k_ECitadelGameMode_StreetBrawl
    haze = heroes.hero_id_by_name("Haze")

    write_cache_entry(cache, match_id=100)
    write_cache_entry(cache, match_id=101, won=False)
    write_cache_entry(cache, match_id=102, game_mode=brawl)
    write_cache_entry(cache, match_id=103, game_mode=brawl)
    write_cache_entry(cache, match_id=104, won=False, game_mode=brawl)
    write_cache_entry(cache, match_id=105, match_mode=private)
    write_cache_entry(cache, match_id=106, match_mode=private)
    write_cache_entry(cache, match_id=107, won=False, match_mode=private)
    write_cache_entry(cache, match_id=108, won=False, account=43, game_mode=brawl)
    write_cache_entry(cache, match_id=109, won=False, match_mode=private, hero_id=haze)
    monkeypatch.setattr(
        cli_winrate.meta,
        "get_hero_stats",
        lambda **kwargs: pytest.fail("an all-mode table has no matching public baseline"),
    )

    run_main(
        tmp_path,
        "winrate",
        "--by",
        "mode",
        "--account",
        "42",
        "--hero",
        "Mirage",
        accounts="you = 42\nalt = 43",
    )

    out = capsys.readouterr().out

    assert re.search(r"Standard \(ranked\)\s+2\s+1\s+1\s+50\.0%", out)
    assert re.search(r"Street Brawl\s+3\s+2\s+1\s+66\.7%", out)
    assert re.search(r"Private Lobby\s+3\s+2\s+1\s+66\.7%", out)
    assert "Overall:" not in out


def test_winrate_by_mode_sorts_unknown_mode_pairs_after_known_modes(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    normal = pb.k_ECitadelGameMode_Normal
    brawl = pb.k_ECitadelGameMode_StreetBrawl
    standard = pb.k_ECitadelMatchMode_Unranked
    placement = pb.k_ECitadelMatchMode_NewPlayerPlacement
    ranked = pb.k_ECitadelMatchMode_Ranked
    private = pb.k_ECitadelMatchMode_PrivateLobby

    for match_id, match_mode, game_mode in (
        (100, standard, normal),
        (101, placement, normal),
        (102, ranked, normal),
        (103, standard, brawl),
        (104, private, normal),
        (105, ranked, brawl),
    ):
        write_cache_entry(
            cache,
            match_id=match_id,
            match_mode=match_mode,
            game_mode=game_mode,
        )

    run_main(tmp_path, "winrate", "--by", "mode", "--account", "42")

    out = capsys.readouterr().out
    labels = [
        "Standard",
        "New Player Placement",
        "Ranked",
        "Street Brawl",
        "Private Lobby",
        "Ranked / Street Brawl",
    ]
    positions = [out.index(f"\n  {label}") for label in labels]

    assert positions == sorted(positions)


def test_winrate_by_mode_rejects_a_mode_selection(capsys, tmp_path):
    run_main(tmp_path, "winrate", "--by", "mode", "--account", "42", "--street-brawl")

    assert "--by mode already includes every mode" in capsys.readouterr().out


def test_winrate_by_account_prints_one_row_per_account(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)
    write_cache_entry(cache, match_id=101, won=False)
    write_cache_entry(cache, match_id=102, account=43)

    run_main(tmp_path, "winrate", "--by", "account", accounts="you = 42\nalt = 43")

    out = capsys.readouterr().out

    assert re.search(r"you\s+2\s+1\s+1\s+50\.0%", out)
    assert re.search(r"alt\s+1\s+1\s+0\s+100\.0%", out)
    assert "Overall:" not in out


def test_winrate_by_account_follows_the_config_order(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)
    write_cache_entry(cache, match_id=101, account=43)

    run_main(tmp_path, "winrate", "--by", "account", accounts="alt = 43\nyou = 42")

    out = capsys.readouterr().out

    assert out.index("\n  alt") < out.index("\n  you")


def test_winrate_by_account_prints_ids_without_config_names(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, teammates=1)

    run_main(tmp_path, "winrate", "--by", "account", "--account", "43")

    out = capsys.readouterr().out

    assert re.search(r"43\s+1\s+1\s+0\s+100\.0%", out)


def test_winrate_by_account_honors_a_mode_flag(capsys, tmp_path):
    split_era_cache(tmp_path)

    run_main(tmp_path, "winrate", "--by", "account", "--account", "42", "--ranked")

    out = capsys.readouterr().out

    assert re.search(r"you\s+1\s+1\s+0\s+100\.0%", out)


def test_winrate_by_account_points_column_follows_the_games(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    ranked = pb.k_ECitadelMatchMode_Ranked
    write_cache_entry(cache, match_id=100, match_mode=ranked, rank_points=(5000, 5250))
    write_cache_entry(cache, match_id=101, account=43)

    run_main(tmp_path, "winrate", "--by", "account", accounts="you = 42\nalt = 43")

    out = capsys.readouterr().out

    assert "Net points" in out
    assert re.search(r"you\s+1\s+1\s+0\s+100\.0%\s+0\s+0\s+\+250", out)
    assert re.search(r"alt\s+1\s+1\s+0\s+100\.0%\s+0\s+0\s+-", out)


def test_winrate_by_account_leaves_the_points_column_out_without_ranked_games(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    run_main(tmp_path, "winrate", "--by", "account")

    out = capsys.readouterr().out

    assert "Net points" not in out


def _write_ranked_games(cache):
    """Write two Ranked wins and a loss the floor clamped to no change."""
    ranked = pb.k_ECitadelMatchMode_Ranked
    write_cache_entry(cache, match_id=100, match_mode=ranked, rank_points=(5000, 5250))
    write_cache_entry(
        cache,
        match_id=101,
        start_time=1783000000 + 86400,
        won=False,
        match_mode=ranked,
        rank_points=(5250, 5100),
    )
    write_cache_entry(
        cache,
        match_id=102,
        start_time=1783000000 + 86400,
        won=False,
        match_mode=ranked,
        rank_points=(5100, 5100),
    )


def test_winrate_ranked_table_totals_the_applied_points(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    _write_ranked_games(cache)

    run_main(tmp_path, "winrate", "--ranked", "--account", "42", "--by", "day")

    out = capsys.readouterr().out
    rows = [line for line in out.splitlines() if line.startswith("  2026-")]

    header = next(line for line in out.splitlines() if "Games" in line)

    assert "Net points" in header
    assert rows[0].endswith("+250")
    assert rows[1].endswith("-150")
    assert "+100 net points." in out


def test_winrate_ranked_thousands_separator(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        match_mode=pb.k_ECitadelMatchMode_Ranked,
        rank_points=(5000, 8500),
    )

    run_main(tmp_path, "winrate", "--ranked", "--account", "42")

    out = capsys.readouterr().out

    assert "+3,500" in out
    assert "+3,500 net points." in out


def test_winrate_standard_table_leaves_the_points_column_out(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    assert "Net points" not in out
    assert "net points" not in out
    assert "Net wins" in out


def test_winrate_ranked_without_ranked_games(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    run_main(tmp_path, "winrate", "--ranked", "--account", "42")

    out = capsys.readouterr().out

    assert "No Ranked games for accounts you" in out
    assert "Net points" not in out


def test_winrate_by_mode_gives_the_ranked_row_its_points(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    _write_ranked_games(cache)
    write_cache_entry(cache, match_id=103, start_time=1783000000 + 2 * 86400)

    run_main(tmp_path, "winrate", "--by", "mode", "--account", "42")

    out = capsys.readouterr().out
    rows = {line.split()[0]: line for line in out.splitlines() if line.startswith("  ")}

    assert "Net points" in rows["Mode"]
    assert rows["Ranked"].endswith("+100")
    assert rows["Standard"].endswith("100.0%")


def test_winrate_abandon_footer(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, won=False, abandon_s=700)
    write_cache_entry(cache, match_id=101)

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    header = next(line for line in out.splitlines() if "Games" in line)

    assert "Abandons" in header
    assert "Abandons: 1 game. You left 1 (0-1)." in out
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
    assert "Abandons: 1 game. You left 1 (1-0)." in out
    assert "1 leaver reconnected and finished." in out
    assert "Not scored: 1 game left out of the table (safe to leave), 0-1 in match history." in out
    assert "Without them" not in out


def test_winrate_unscored_only_window(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, not_scored=True)

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    assert "No Ranked games for accounts you" in out
    assert "Not scored: 1 game left out of the table (safe to leave), 1-0 in match history." in out


def test_winrate_lobby_column(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, badges=(95, 91))

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    header = next(line for line in out.splitlines() if "Games" in line)

    assert "Lobby" in header
    assert "Phantom III" in out
    assert "Phantom III lobbies." in out


def test_winrate_lobby_blank_without_badges(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    assert "lobbies" not in out


def test_winrate_lobby_names_follow_the_game_era(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, badges=(63, 63))
    write_cache_entry(cache, match_id=101, start_time=1783000000 + 32 * 86400, badges=(63, 63))

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    assert "Emissary III" in out
    assert "Ritualist III" in out
    assert "Ritualist III lobbies." in out


def test_winrate_account_lobby_names_follow_the_game_era(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, badges=(63, 63))

    run_main(tmp_path, "winrate", "--account", "42", "--by", "account")

    out = capsys.readouterr().out

    assert "Emissary III" in out
    assert "Mystic" not in out


def test_winrate_no_abandon_footer_without_abandons(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    run_main(tmp_path, "winrate", "--account", "42")

    out = capsys.readouterr().out

    assert "Abandons:" not in out
    assert "Not scored:" not in out


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
    monkeypatch.setattr(cli_winrate.meta, "get_hero_stats", lambda **kw: rows)

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

    monkeypatch.setattr(cli_winrate.meta, "get_hero_stats", no_network)

    run_main(tmp_path, "winrate", "--account", "42", "--hero", "Mirage")

    out = capsys.readouterr().out

    assert "Overall: 1 games" in out
    assert "deadlock-api.com" not in out


def test_winrate_baseline_prints_without_games(capsys, tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text('timezone = "America/Chicago"\n[accounts]\nyou = 42\n')

    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    rows = [{"hero_id": 52, "wins": 55, "losses": 45, "matches": 100}]
    monkeypatch.setattr(cli_winrate.meta, "get_hero_stats", lambda **kw: rows)

    args = ["--cache", str(cache), "--archive", str(tmp_path / "arc")]
    args += ["--parquet", str(tmp_path / "pq")]
    args += ["winrate", "--account", "99", "--hero", "Mirage"]
    main(args, config=cfg)

    out = capsys.readouterr().out

    assert "No Ranked games for accounts 99 on Mirage" in out
    assert "Mirage in Eternus+ lobbies: 55.0% win rate over 100 games (deadlock-api.com)" in out


def test_winrate_since(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    run_main(tmp_path, "winrate", "--account", "42", "--since", "2100-01-01")

    assert "No Ranked games for accounts you since 2100-01-01" in capsys.readouterr().out


def test_winrate_no_games_for_account(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100)

    run_main(tmp_path, "winrate", "--account", "7")

    assert "No Ranked games for accounts 7" in capsys.readouterr().out
