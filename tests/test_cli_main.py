import argparse
import datetime as dt
from pathlib import Path

import polars as pl
import pytest
from cli_helpers import run_main, write_cache_entry

from deadlock_matches import (
    export,
    extract,
    paths,
    players,
    schemas,
)
from deadlock_matches.cli.main import (
    _repair_players_store,
    build_parser,
    main,
    parse_accounts,
    resolve_store,
)
from deadlock_matches.queries import registered_views


@pytest.fixture(autouse=True)
def no_installed_client(monkeypatch):
    monkeypatch.setattr(extract, "installed_client_version", lambda cache_dir=None: None)


def test_report_rebuilds_schema_drift_without_a_new_cache_entry(tmp_path, capsys):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "history", "--account", "42")
    target = next((tmp_path / "pq" / "players").glob("month=*/*.parquet"))
    pl.read_parquet(target).drop("player_match_outcome").write_parquet(target)

    assert export.schema_drift(tmp_path / "pq") is not None
    capsys.readouterr()

    run_main(tmp_path, "history", "--account", "42")

    assert export.schema_drift(tmp_path / "pq") is None
    assert "player_match_outcome" in pl.read_parquet_schema(target)
    assert "Rebuilt all tables from the archive" in capsys.readouterr().out


def test_explicit_match_reuses_the_stored_account_filter_when_config_is_empty(tmp_path, capsys):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "history", "--account", "42")
    target = next((tmp_path / "pq" / "players").glob("month=*/*.parquet"))
    pl.read_parquet(target).drop("player_match_outcome").write_parquet(target)
    capsys.readouterr()

    run_main(tmp_path, "match", "100", "--hero", "Mirage", accounts=None)

    assert export.schema_drift(tmp_path / "pq") is None
    assert export.stored_accounts(tmp_path / "pq") == [42]
    out = capsys.readouterr().out
    assert "Rebuilt all tables from the archive" in out
    assert "Match 100: Mirage" in out


def test_report_repairs_a_selected_tracked_player_store(tmp_path, monkeypatch, capsys):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[accounts]\nmain = 42\n")
    seen = {}
    args = argparse.Namespace(
        parquet=str(players.PLAYERS_PARQUET_DIR),
        cmd="history",
        archive=str(tmp_path / "arc"),
    )
    monkeypatch.setattr(export, "schema_drift", lambda out, exclude: "players columns differ")

    def repair(rows, out_dir, exclude, archive_dir):
        seen.update(
            rows=rows,
            out_dir=out_dir,
            exclude=exclude,
            archive_dir=archive_dir,
        )

    monkeypatch.setattr(players, "write_player_tables", repair)

    _repair_players_store(args, cfg)

    assert seen == {
        "rows": [],
        "out_dir": players.PLAYERS_PARQUET_DIR,
        "exclude": set(),
        "archive_dir": str(tmp_path / "arc"),
    }
    assert "Rebuilt the tracked-player tables from the archive" in capsys.readouterr().out


def test_report_repairs_an_explicit_custom_tracked_player_store(tmp_path, monkeypatch, capsys):
    store = tmp_path / "custom-players"
    store.mkdir()
    schemas.conform(
        "downloads",
        [
            {
                "match_id": 500,
                "account_id": 99,
                "player": "pro",
                "hero_id": 52,
                "rank": None,
                "region": None,
                "downloaded_at": dt.datetime(2026, 7, 1, tzinfo=dt.UTC),
            }
        ],
    ).write_parquet(store / "downloads.parquet")
    args = argparse.Namespace(
        parquet=str(store),
        cmd="match",
        archive=str(tmp_path / "arc"),
        hero="Mirage",
    )
    seen = []
    monkeypatch.setattr(export, "schema_drift", lambda out, exclude: "players columns differ")
    monkeypatch.setattr(
        players,
        "write_player_tables",
        lambda rows, out_dir, exclude, archive_dir: seen.append(Path(out_dir)),
    )

    _repair_players_store(args, tmp_path / "config.toml")

    assert seen == [store]
    assert paths.tilde(store) in capsys.readouterr().out


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


def test_parser_resolves_tracked_player_names(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[accounts]\nmain = 42\n\n[players.Mirage]\nsomeplayer = 22\n")

    args = build_parser(cfg).parse_args(["damage", "--hero", "Mirage", "--account", "someplayer"])

    assert args.account == [22]


def test_parser_account_names_win_over_player_names(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("[accounts]\nmain = 42\n\n[players.Mirage]\nmain = 99\n")

    args = build_parser(cfg).parse_args(["history", "--account", "main"])

    assert args.account == [42]


def _store_setup(tmp_path, monkeypatch, downloaded=(22,)):
    main_store = tmp_path / "parquet"
    players_store = tmp_path / "parquet-players"
    players_store.mkdir()
    monkeypatch.setattr(export, "PARQUET_DIR", main_store)
    monkeypatch.setattr(players, "PLAYERS_PARQUET_DIR", players_store)

    if downloaded:
        pl.DataFrame(
            {
                "match_id": list(range(len(downloaded))),
                "account_id": list(downloaded),
                "player": ["someplayer"] * len(downloaded),
            }
        ).write_parquet(players_store / "downloads.parquet")

    cfg = tmp_path / "config.toml"
    cfg.write_text("[accounts]\nmain = 42\n\n[players.Mirage]\nsomeplayer = 22\n")

    return main_store, players_store, cfg


def test_resolve_store_reads_tracked_accounts_from_the_players_store(tmp_path, monkeypatch):
    main_store, players_store, cfg = _store_setup(tmp_path, monkeypatch)
    args = argparse.Namespace(parquet=str(main_store), account=[22])

    resolve_store(args, cfg)

    assert args.parquet == str(players_store)


def test_resolve_store_keeps_config_accounts_on_the_main_tables(tmp_path, monkeypatch):
    main_store, _, cfg = _store_setup(tmp_path, monkeypatch)
    args = argparse.Namespace(parquet=str(main_store), account=[42])

    resolve_store(args, cfg)

    assert args.parquet == str(main_store)


def test_resolve_store_keeps_a_mixed_list_on_the_main_tables(tmp_path, monkeypatch):
    main_store, _, cfg = _store_setup(tmp_path, monkeypatch)
    args = argparse.Namespace(parquet=str(main_store), account=[42, 22])

    resolve_store(args, cfg)

    assert args.parquet == str(main_store)


def test_resolve_store_ignores_accounts_missing_from_downloads(tmp_path, monkeypatch):
    main_store, _, cfg = _store_setup(tmp_path, monkeypatch)
    args = argparse.Namespace(parquet=str(main_store), account=[999])

    resolve_store(args, cfg)

    assert args.parquet == str(main_store)


def test_resolve_store_respects_an_explicit_parquet_path(tmp_path, monkeypatch):
    _, _, cfg = _store_setup(tmp_path, monkeypatch)
    elsewhere = tmp_path / "elsewhere"
    args = argparse.Namespace(parquet=str(elsewhere), account=[22])

    resolve_store(args, cfg)

    assert args.parquet == str(elsewhere)


def test_resolve_store_without_a_downloads_ledger(tmp_path, monkeypatch):
    main_store, _, cfg = _store_setup(tmp_path, monkeypatch, downloaded=())
    args = argparse.Namespace(parquet=str(main_store), account=[22])

    resolve_store(args, cfg)

    assert args.parquet == str(main_store)


def test_int_list_parses_commas_and_spaces():
    from deadlock_matches.cli.main import int_list

    assert int_list("900,901") == [900, 901]
    assert int_list("900 901") == [900, 901]


def test_int_list_rejects_non_numeric():
    from deadlock_matches.cli.main import int_list

    with pytest.raises(argparse.ArgumentTypeError, match="not a numeric id"):
        int_list("abc")


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

    args = build_parser(p).parse_args(["compare", "souls", "--hero", "Haze", "--account", "7,8"])

    assert args.account == [7, 8]


def test_compare_reports_are_subcommands(tmp_path):
    parser = build_parser(tmp_path / "config.toml")
    args = parser.parse_args(["compare", "damage", "--hero", "Mirage"])

    assert args.stat == "damage"

    with pytest.raises(SystemExit):
        parser.parse_args(["compare", "--hero", "Mirage"])


def test_mode_flags_default_and_select_alternatives(tmp_path):
    parser = build_parser(tmp_path / "config.toml")

    default = parser.parse_args(["download", "--hero", "Mirage"])
    standard = parser.parse_args(["download", "--hero", "Mirage", "--standard"])
    ranked = parser.parse_args(["download", "--hero", "Mirage", "--ranked"])
    placement = parser.parse_args(["download", "--hero", "Mirage", "--placement"])
    calibration_alias = parser.parse_args(["download", "--hero", "Mirage", "--calibration"])
    brawl = parser.parse_args(["download", "--hero", "Mirage", "--street-brawl"])
    private = parser.parse_args(["download", "--hero", "Mirage", "--private-lobby"])

    assert default.mode == (
        (extract.MATCH_MODE_STANDARD, extract.MATCH_MODE_RANKED),
        extract.GAME_MODE_NORMAL,
        True,
    )
    assert standard.mode == (extract.MATCH_MODE_STANDARD, extract.GAME_MODE_NORMAL, False)
    assert ranked.mode == (extract.MATCH_MODE_RANKED, extract.GAME_MODE_NORMAL, None)
    assert placement.mode == (extract.MATCH_MODE_PLACEMENT, extract.GAME_MODE_NORMAL, None)
    assert calibration_alias.mode == placement.mode
    assert brawl.mode == (extract.MATCH_MODE_STANDARD, extract.GAME_MODE_STREET_BRAWL, None)
    assert private.mode == (extract.MATCH_MODE_PRIVATE_LOBBY, extract.GAME_MODE_NORMAL, None)

    with pytest.raises(SystemExit):
        parser.parse_args(["download", "--hero", "Mirage", "--street-brawl", "--private-lobby"])


def test_help_sections_cover_every_command(tmp_path):
    from deadlock_matches.cli.main import COMMAND_HELP, SECTIONS

    parser = build_parser(tmp_path / "config.toml")
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    registered = set(sub.choices or [])
    sectioned = [name for _, names in SECTIONS for name in names]

    assert set(sectioned) == registered
    assert len(sectioned) == len(set(sectioned))
    assert set(COMMAND_HELP) == registered


def test_help_sweep_includes_nested_skill_commands(tmp_path, capsys):
    parser = build_parser(tmp_path / "config.toml")
    sub = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))

    commands = [
        [],
        ["compare", "souls"],
        ["compare", "damage"],
        ["compare", "healing"],
        ["compare", "combat"],
        ["compare", "movement"],
        ["skill"],
        ["skill", "path"],
        ["skill", "print"],
        ["skill", "install"],
    ]
    commands.extend([[name] for name in sub.choices])

    for command in commands:
        with pytest.raises(SystemExit) as exc:
            parser.parse_args([*command, "--help"])

        assert exc.value.code == 0

    out = capsys.readouterr().out

    assert "install or inspect the bundled agent skill" in out
    assert "--against" in out
    assert "--pool-since" in out
    assert "--milestones" in out
    assert "--step" in out
    assert "replace an existing deadlock-matches agent skill" in out


def test_schema_command_prints_dictionary(capsys):
    main(["schema", "damage"])

    out = capsys.readouterr().out

    for name in schemas.Damage.spec():
        assert name in out


def test_schema_command_points_at_the_views(capsys):
    main(["schema"])

    out = capsys.readouterr().out

    assert f"{len(registered_views())} metric views" in out
    assert "deadlock schema --views" in out
    assert out.index("metric views") < out.index("matches")


def test_schema_command_for_one_table_leaves_the_view_pointer_out(capsys):
    main(["schema", "players"])

    out = capsys.readouterr().out

    assert "metric views" not in out


def test_schema_command_prints_sample_rows(capsys, tmp_path):
    schemas.conform(
        "players",
        [
            {
                "match_id": i,
                "start_time": dt.datetime(2026, 6, 1, tzinfo=dt.UTC),
                "account_id": 42,
                "hero_id": 52,
                "team": 1,
                "player_slot": 0,
                "assigned_lane": 4,
                "won": True,
                "player_match_outcome": None,
                "player_rank_initial_display_rank": None,
                "player_rank_initial_flat_progress": None,
                "player_rank_final_flat_progress": None,
                "player_rank_desired_progress_change": None,
                "player_rank_initial_calibration_games": None,
                "player_rank_initial_demotion_protection_games": None,
                "player_rank_consumed_demotion_protection": None,
                "player_rank_initial_win_streak": None,
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
    assert "hero_id" in out
    assert "Mirage" not in out
    assert "shape: (5, 26)" in out


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


def test_schema_views_describes_what_summarize_accepts(capsys):
    main(["schema", "--views", "my_games"])

    out = capsys.readouterr().out

    assert "my_games  one row per match_id, account_id" in out
    assert "group by" in out
    assert "win_rate" in out
    assert "record_games" not in out

    main(["schema", "--views"])

    assert "record_games" in capsys.readouterr().out


def test_schema_views_and_sample_do_not_mix(capsys):
    main(["schema", "players", "--views", "--sample"])

    assert "drop --views to use it" in capsys.readouterr().out
