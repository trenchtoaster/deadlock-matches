import argparse
import re

import pytest

from deadlock_matches import (
    extract,
)
from deadlock_matches.assets import (
    abilities,
    heroes,
)
from deadlock_matches.cli import cards
from deadlock_matches.cli.main import (
    main,
)


@pytest.fixture(autouse=True)
def no_installed_client(monkeypatch):
    monkeypatch.setattr(extract, "installed_client_version", lambda cache_dir=None: None)


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


def test_hero_card_as_of_shows_era_label(capsys, tmp_path):
    main(["hero", "Mirage", "--as-of", "2026-02-01"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "as of 2026-02-01" in out


def test_ability_card_as_of_shows_era_label(capsys, tmp_path):
    main(["ability", "Fire Scarabs", "--as-of", "2026-03-01"], config=tmp_path / "none.json")

    assert "as of 2026-03-01" in capsys.readouterr().out


def test_hero_card_changes_lists_patches(capsys, tmp_path):
    main(["hero", "Mirage", "--changes"], config=tmp_path / "none.json")

    out = capsys.readouterr().out

    assert "change history" in out
    assert "build" in out
