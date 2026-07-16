import tomllib

import pytest

from deadlock_matches import config
from deadlock_matches.cli.main import main


def test_config_accounts_rejects_list_form(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("accounts = [42, 43]")

    with pytest.raises(SystemExit, match=r"\[accounts\] table"):
        config.config_accounts(p)


def test_config_accounts_missing_file(tmp_path):
    assert config.config_accounts(tmp_path / "test.json") is None


def test_config_accounts_empty_list(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("accounts = []")

    assert config.config_accounts(p) is None


def test_config_accounts_table_form(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[accounts]\nmain = 42\n"old alt" = 43\n')

    assert config.config_accounts(p) == [42, 43]


def test_config_accounts_empty_table(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[accounts]")

    assert config.config_accounts(p) is None


def test_config_account_names_table_form(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[accounts]\nmain = 42\n"old alt" = 43\n')

    assert config.config_account_names(p) == {"main": 42, "old alt": 43}


def test_config_account_names_rejects_list_form(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("accounts = [42, 43]")

    with pytest.raises(SystemExit, match=r"\[accounts\] table"):
        config.config_account_names(p)


def test_config_account_names_missing_file(tmp_path):
    assert config.config_account_names(tmp_path / "test.json") == {}


def test_format_accounts_swaps_in_names(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[accounts]\nmain = 42\n")

    assert config.format_accounts([42, 99], p) == "main, 99"


def test_format_accounts_swaps_in_tracked_player_names(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[accounts]\nmain = 42\n\n[players.Mirage]\nsomeplayer = 22\n")

    assert config.format_accounts([42, 22, 7], p) == "main, someplayer, 7"


def test_format_accounts_account_names_win_over_player_names(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[accounts]\nmain = 42\n\n[players.Mirage]\nsomeplayer = 42\n")

    assert config.format_accounts([42], p) == "main"


def test_config_player_names_flattens_every_hero(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[players.Mirage]\nsomeplayer = 22\n\n[players."Grey Talon"]\nladderer = 11\n')

    assert config.config_player_names(p) == {"someplayer": 22, "ladderer": 11}


def test_config_player_names_missing_file(tmp_path):
    assert config.config_player_names(tmp_path / "test.json") == {}


def test_config_players_case_insensitive(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[players.Mirage]\nsomeplayer = 111222333\n")

    assert config.config_players("mirage", p) == {"someplayer": 111222333}


def test_config_syntax_error_exits_with_line(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("[players.Grey Talon]\nsomeplayer = 1\n")

    with pytest.raises(SystemExit, match=r"not valid TOML.*line 1"):
        config.config_players("Grey Talon", p)


def test_config_players_quoted_hero_name(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[players."Grey Talon"]\nsomeplayer = 111222333\n')

    assert config.config_players("grey talon", p) == {"someplayer": 111222333}


def test_config_players_missing(tmp_path):
    assert config.config_players("Mirage", tmp_path / "test.json") == {}

    p = tmp_path / "config.toml"
    p.write_text("accounts = [1]")

    assert config.config_players("Mirage", p) == {}


def test_config_players_all_reads_every_hero(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[players."Mirage"]\nsomeplayer = 111\n\n[players."Grey Talon"]\nother = 222\n')

    assert config.config_players_all(p) == {
        "Mirage": {"someplayer": 111},
        "Grey Talon": {"other": 222},
    }


def test_find_config_uses_the_user_config_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text("[accounts]\nmain = 42\n")
    monkeypatch.setattr(config.paths, "config_dir", lambda: tmp_path / "cfg")

    target = tmp_path / "cfg" / "deadlock-matches" / "config.toml"

    assert config.find_config() == target
    assert not target.exists()


def test_ensure_config_writes_to_the_user_config_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config.paths, "config_dir", lambda: tmp_path / "cfg")

    config.ensure_config()

    target = tmp_path / "cfg" / "deadlock-matches" / "config.toml"

    assert target.exists()
    assert "[accounts]" in target.read_text(encoding="utf-8")


def test_ensure_config_writes_starter(tmp_path):
    p = tmp_path / "config.toml"
    config.ensure_config(p)
    raw = p.read_text(encoding="utf-8")
    cfg = tomllib.loads(raw)

    assert cfg["accounts"] == {}
    assert cfg["exclude"] == ["movement"]
    assert cfg["timezone"]
    assert "#" in raw


def test_ensure_config_leaves_existing_file(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("accounts = [42]")
    config.ensure_config(p)

    assert p.read_text() == "accounts = [42]"


def test_config_timezone_reads_config(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('timezone = "America/Chicago"')

    assert config.config_timezone(p) == "America/Chicago"


def test_config_timezone_detects_when_missing(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("accounts = [42]")

    tz = config.config_timezone(p)

    assert tz
    assert p.read_text(encoding="utf-8") == "accounts = [42]"


def test_main_with_an_explicit_config_writes_no_starter(tmp_path):
    custom = tmp_path / "custom.toml"
    main(["hero", "Mirage"], config=custom)

    assert not custom.exists()
