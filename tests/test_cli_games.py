import re

import polars as pl
import pytest
from cli_helpers import run_main, write_cache_entry

from deadlock_matches import (
    extract,
    queries,
)
from deadlock_matches.cli import games as cli_games
from deadlock_matches.cli import match as cli_match


@pytest.fixture(autouse=True)
def no_installed_client(monkeypatch):
    monkeypatch.setattr(extract, "installed_client_version", lambda cache_dir=None: None)


def test_movement_command_prints_metric_and_game_tables(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)], paths=True)

    run_main(tmp_path, "movement", "--hero", "Mirage", "--account", "42")

    out = capsys.readouterr().out

    assert "Movement, 1 games of Mirage" in out
    assert "meters /min" in out
    assert "fighting players %" in out
    assert "All (1)" in out
    assert "Wins (" not in out
    assert "Percents cover seconds alive" in out
    assert "Per game, newest last" in out
    assert "m /min" in out
    assert "Stationary %" in out
    assert "5/2/8" in out
    assert "win" in out
    assert "  100" in out


def test_movement_command_splits_wins_and_losses(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)], paths=True)
    write_cache_entry(
        cache, match_id=101, start_time=1783003600, won=False, stats=[(300, 3000)], paths=True
    )

    run_main(tmp_path, "movement", "--hero", "Mirage", "--account", "42")

    out = capsys.readouterr().out

    assert "Movement, 2 games of Mirage" in out
    assert "All (2)" in out
    assert "Wins (1)" in out
    assert "Losses (1)" in out
    assert "loss" in out


def test_movement_table_ignores_null_results_and_prints_null_means_as_missing(capsys):
    games = pl.DataFrame(
        {
            "won": [True, None],
            "distance_min": [None, None],
            "stationary_percent": [None, None],
            "slide_percent": [None, None],
            "in_air_percent": [None, None],
            "zipline_percent": [None, None],
            "combat_percent": [None, None],
            "dashes_min": [None, None],
            "air_dashes_min": [None, None],
        },
        schema_overrides={
            "won": pl.Boolean,
            "distance_min": pl.Float64,
            "stationary_percent": pl.Float64,
            "slide_percent": pl.Float64,
            "in_air_percent": pl.Float64,
            "zipline_percent": pl.Float64,
            "combat_percent": pl.Float64,
            "dashes_min": pl.Float64,
            "air_dashes_min": pl.Float64,
        },
    )

    cli_games._movement_table(games)
    out = capsys.readouterr().out

    assert "All (2)" in out
    assert "Wins (" not in out
    assert re.search(r"meters /min\s+-", out)
    assert "0.0" not in out


def test_movement_command_game_without_rows_prints_dashes(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)], paths=True)
    write_cache_entry(cache, match_id=101, start_time=1783003600, stats=[(300, 3000)])

    run_main(tmp_path, "movement", "--hero", "Mirage", "--account", "42")

    out = capsys.readouterr().out

    assert "Movement, 2 games of Mirage" in out
    assert re.search(r"-\s+-\s+-\s+-\s+-\s+101", out)


def test_movement_command_unknown_hero_prints_error(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)], paths=True)

    run_main(tmp_path, "movement", "--hero", "Nobody", "--account", "42")

    out = capsys.readouterr().out

    assert "Unknown hero 'Nobody'" in out


def test_movement_command_without_account_prints_hint(capsys, tmp_path):
    run_main(tmp_path, "movement", "--hero", "Mirage", accounts=None)

    out = capsys.readouterr().out

    assert "No account set" in out


def test_souls_command_milestones(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    g = queries.GoldSource

    for match_id in (100, 101, 102):
        write_cache_entry(
            cache,
            match_id=match_id,
            stats=[(300, 3000), (600, 5000)],
            gold_sources=[(300, g.LANE_CREEPS, 800, 200), (600, g.LANE_CREEPS, 1600, 400)],
        )

    run_main(tmp_path, "souls", "--hero", "Mirage", "--milestones")

    out = capsys.readouterr().out

    assert "Minutes to reach a net worth, median across games" in out
    assert "You: you, 3 Mirage games" in out
    assert re.search(r"3200\s+5\.5\s+3", out)
    assert re.search(r"4800\s+9\.5\s+3", out)


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


def test_damage_command_prints_delivery_source_and_game_tables(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=((300, 3000), (600, 6000)),
        damage=(
            ("citadel_weapon_mirage", [100, 250]),
            ("mirage_tornado", [50, 100]),
            ("upgrade_toxic_bullets", [40, 50]),
        ),
    )

    run_main(tmp_path, "damage", "--hero", "Mirage", "--account", "42")

    out = capsys.readouterr().out

    assert "Damage to heroes by source, 1 games of Mirage" in out
    assert "Delivery" in out
    assert "Gun" in out
    assert "Abilities" in out
    assert "Items (bullet procs)" in out
    assert "/min owned" in out
    assert "/1k souls" in out
    assert "/game" in out
    assert "Per game, newest last" in out
    assert "win" in out
    assert "5/2/8" in out
    assert "62.5" in out
    assert "25.0" in out
    assert "12.5" in out


def test_damage_command_caps_the_per_game_table(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()

    for i in range(11):
        write_cache_entry(
            cache,
            match_id=100 + i,
            start_time=1783000000 + i * 3600,
            stats=((300, 3000),),
            damage=(("citadel_weapon_mirage", [100, 250]),),
        )

    run_main(tmp_path, "damage", "--hero", "Mirage", "--account", "42")

    out = capsys.readouterr().out

    assert "Per game, the last 10 of 11 (--games N lists more), newest last" in out
    assert "  110\n" in out
    assert "  100\n" not in out

    run_main(tmp_path, "damage", "--hero", "Mirage", "--account", "42", "--days", "30")

    out = capsys.readouterr().out

    assert "Per game, the last 10 of 11" in out
    assert "  100\n" not in out

    run_main(tmp_path, "damage", "--hero", "Mirage", "--account", "42", "--games", "11")

    out = capsys.readouterr().out

    assert "Per game, newest last" in out
    assert "  100\n" in out


def test_damage_command_resolves_fuzzy_hero_names(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=((300, 3000),),
        damage=(("citadel_weapon_mirage", [100, 250]),),
    )

    run_main(tmp_path, "damage", "--hero", "mirage", "--account", "42")

    out = capsys.readouterr().out

    assert "games of Mirage" in out


def test_damage_command_unknown_hero_prints_error(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=((300, 3000),))

    run_main(tmp_path, "damage", "--hero", "Nobody", "--account", "42")

    out = capsys.readouterr().out

    assert "Unknown hero 'Nobody'" in out


def test_damage_command_empty_mode_names_the_mode_and_accounts(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=((300, 3000),))

    run_main(tmp_path, "damage", "--hero", "Mirage", "--placement")

    out = capsys.readouterr().out

    assert "No New Player Placement games for accounts you on Mirage" in out
    assert "[42]" not in out


def test_damage_command_without_account_prints_hint(capsys, tmp_path):
    run_main(tmp_path, "damage", "--hero", "Mirage", accounts=None)

    out = capsys.readouterr().out

    assert "No account set" in out


def test_healing_command_prints_delivery_source_and_game_tables(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=((300, 3000), (600, 6000)),
        damage=(
            ("mirage_tornado", [50, 100], 1),
            ("upgrade_toxic_bullets", [40, 60], 1, 1, 1),
            ("upgrade_toxic_bullets", [15, 45], 2, 1, 2),
        ),
    )

    run_main(tmp_path, "healing", "--hero", "Mirage", "--account", "42")

    out = capsys.readouterr().out

    assert "Healing by source, 1 games of Mirage" in out
    assert "Abilities" in out
    assert "Items (bullet procs)" in out
    assert "/min owned" in out
    assert "/1k souls" in out
    assert "/game" in out
    assert "/min divides the same way with the minutes of those games" in out
    assert "Self %" in out
    assert "Healing prevented:" in out
    assert "Prevented" in out
    assert "45" in out
    assert "Per game, newest last" in out
    assert "win" in out
    assert "5/2/8" in out
    assert "62.5" in out
    assert "37.5" in out


def test_healing_command_without_prevented_rows_skips_the_table(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=((300, 3000),),
        damage=(("mirage_tornado", [50, 100], 1),),
    )

    run_main(tmp_path, "healing", "--hero", "Mirage", "--account", "42")

    out = capsys.readouterr().out

    assert "Healing by source, 1 games of Mirage" in out
    assert "Healing prevented" not in out


def test_healing_command_caps_the_per_game_table(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()

    for i in range(11):
        write_cache_entry(
            cache,
            match_id=100 + i,
            start_time=1783000000 + i * 3600,
            stats=((300, 3000),),
            damage=(("mirage_tornado", [50, 100], 1),),
        )

    run_main(tmp_path, "healing", "--hero", "Mirage", "--account", "42")

    out = capsys.readouterr().out

    assert "Per game, the last 10 of 11 (--games N lists more), newest last" in out
    assert "  110\n" in out
    assert "  100\n" not in out

    run_main(tmp_path, "healing", "--hero", "Mirage", "--account", "42", "--games", "11")

    out = capsys.readouterr().out

    assert "Per game, newest last" in out
    assert "  100\n" in out


def test_healing_command_unknown_hero_prints_error(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=((300, 3000),))

    run_main(tmp_path, "healing", "--hero", "Nobody", "--account", "42")

    out = capsys.readouterr().out

    assert "Unknown hero 'Nobody'" in out


def test_healing_command_without_account_prints_hint(capsys, tmp_path):
    run_main(tmp_path, "healing", "--hero", "Mirage", accounts=None)

    out = capsys.readouterr().out

    assert "No account set" in out


def test_souls_command_prints_group_source_and_game_tables(capsys, tmp_path):
    g = queries.GoldSource
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=((300, 3000), (600, 6000)),
        gold_sources=(
            (300, g.LANE_CREEPS, 800, 200),
            (600, g.LANE_CREEPS, 2000, 500),
            (600, g.PLAYERS, 600, 0),
            (600, g.BOSSES, 800, 0),
            (600, g.TEAM_BONUS, 100, 0),
        ),
    )

    run_main(tmp_path, "souls", "--hero", "Mirage", "--account", "42")

    out = capsys.readouterr().out

    assert "Souls by source, 1 games of Mirage" in out
    assert "Group" in out
    assert "Waves" in out
    assert "Objectives" in out
    assert "Catch-Up" in out
    assert "Troopers" in out
    assert "Enemy Kills" in out
    assert "Team Catch-Up" in out
    assert "Per game, newest last" in out
    assert "win" in out
    assert "5/2/8" in out
    assert "62.5" in out
    assert "15.0" in out
    assert "20.0" in out
    assert "4,000" in out


def test_souls_command_unknown_hero_prints_error(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=((300, 3000),))

    run_main(tmp_path, "souls", "--hero", "Nobody", "--account", "42")

    out = capsys.readouterr().out

    assert "Unknown hero 'Nobody'" in out


def test_souls_command_without_account_prints_hint(capsys, tmp_path):
    run_main(tmp_path, "souls", "--hero", "Mirage", accounts=None)

    out = capsys.readouterr().out

    assert "No account set" in out


def test_combat_command_prints_aim_and_game_tables(capsys, tmp_path):
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
            ("Parry Success", 3),
            ("Parry Miss", 2),
        ],
        shots=(1400, 600),
    )

    run_main(tmp_path, "combat", "--hero", "Mirage", "--account", "42")

    out = capsys.readouterr().out

    assert "Combat stats, 1 games of Mirage" in out
    assert "Aim vs heroes" in out
    assert "1,000" in out
    assert "25.0%" in out
    assert "20.0%" in out
    assert "Enemy fire at you" in out
    assert "Accuracy with troopers and everything else included: 70%" in out
    assert "Damage by range" in out
    assert "Falloff on your hits: 75% none, 25% partial, 0% max" in out
    assert "Parries 3 landed, 2 missed, 3.0 landed per game" in out
    assert "Per game, newest last" in out
    assert "Hit %" in out
    assert "HS %" in out
    assert "5/2/8" in out


def test_leftover_sections_drops_strays_without_bare(capsys):
    stats: dict[tuple[str | None, str], int] = {
        ("Wraith", "FullAutoTimeAt_1_stacks"): 30,
        (None, "Some Engine Counter"): 24,
    }

    cli_match.leftover_sections(stats, bare=False)

    out = capsys.readouterr().out
    fields = out.split()

    assert "Wraith" in fields
    assert "Full Auto uptime" in out
    assert fields[-6:] == ["Stacks", "Time", "Share", "1", "0:30", "100%"]
    assert "Some Engine Counter" not in out


def test_leftover_sections_prints_strays_by_default(capsys):
    cli_match.leftover_sections({(None, "Some Engine Counter"): 24})

    out = capsys.readouterr().out

    assert out == "\n  Other\n  Some Engine Counter: 24\n"


def test_combat_command_without_any_counters(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "combat", "--hero", "Mirage", "--account", "42")

    out = capsys.readouterr().out

    assert "No combat stats in 1 games of Mirage" in out


def test_combat_command_unknown_hero_prints_error(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=((300, 3000),))

    run_main(tmp_path, "combat", "--hero", "Nobody", "--account", "42")

    out = capsys.readouterr().out

    assert "Unknown hero 'Nobody'" in out


def test_combat_command_without_account_prints_hint(capsys, tmp_path):
    run_main(tmp_path, "combat", "--hero", "Mirage", accounts=None)

    out = capsys.readouterr().out

    assert "No account set" in out
