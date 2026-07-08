import tomllib

import pytest

from deadlock_matches import config


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
