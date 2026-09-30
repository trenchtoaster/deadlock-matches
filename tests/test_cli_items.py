import argparse
import re

import polars as pl
import pytest

from deadlock_matches import (
    extract,
    players,
)
from deadlock_matches.assets import (
    items,
)
from deadlock_matches.cli import cards
from deadlock_matches.cli import items as cli_items
from deadlock_matches.cli.main import (
    main,
)


@pytest.fixture(autouse=True)
def no_installed_client(monkeypatch):
    monkeypatch.setattr(extract, "installed_client_version", lambda cache_dir=None: None)


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
    assert "Rank" not in out
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
    monkeypatch.setattr(players, "PLAYERS_PARQUET_DIR", tmp_path / "players-pq")
    cfg = tmp_path / "config.toml"
    cfg.write_text("[players.Mirage]\nsomeplayer = 22\n")

    main(["builds", "--hero", "Mirage"], config=cfg)

    out = capsys.readouterr().out

    assert "No downloaded games from the tracked Mirage players yet" in out
    assert 'deadlock download --hero "Mirage"' in out


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
        "cooldown                                  30s  (22.5s with Transcendent Cooldown)" in out
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

    assert re.search(r"move speed\s+-\d+%", out)


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
            "effective_cost": [1600, None, None],
        }
    )
    monkeypatch.setattr(cli_items.queries, "item_games", lambda *a, **kw: rows)
    monkeypatch.setattr(cli_items.players, "PLAYERS_PARQUET_DIR", tmp_path)

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
            "effective_cost": [1600],
        }
    )
    monkeypatch.setattr(cli_items.queries, "item_games", lambda *a, **kw: rows)
    monkeypatch.setattr(cli_items.players, "PLAYERS_PARQUET_DIR", tmp_path)
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
            "effective_cost": [1600],
        }
    )
    monkeypatch.setattr(cli_items.queries, "item_games", lambda *a, **kw: rows)
    monkeypatch.setattr(cli_items.players, "PLAYERS_PARQUET_DIR", tmp_path)

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
            "effective_cost": [1600],
        }
    )
    monkeypatch.setattr(cli_items.queries, "item_games", lambda *a, **kw: rows)
    monkeypatch.setattr(cli_items.players, "PLAYERS_PARQUET_DIR", tmp_path)

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


def test_item_on_hero_as_of_shows_era_label(capsys, tmp_path):
    main(
        ["item", "Healbane", "--hero", "Mirage", "--as-of", "2026-03-01"],
        config=tmp_path / "none.json",
    )

    assert "as of 2026-03-01" in capsys.readouterr().out


def test_item_card_changes_lists_patches(capsys, tmp_path):
    main(["item", "Monster Rounds", "--changes"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "change history" in out
