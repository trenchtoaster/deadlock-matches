import re

import pytest

from deadlock_matches import (
    extract,
)
from deadlock_matches.cli import meta as cli_meta
from deadlock_matches.cli.main import (
    main,
)


@pytest.fixture(autouse=True)
def no_installed_client(monkeypatch):
    monkeypatch.setattr(extract, "installed_client_version", lambda cache_dir=None: None)


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
