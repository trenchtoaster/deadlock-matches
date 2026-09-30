import re
import shutil

import pytest
from cli_helpers import run_main, split_era_cache, write_cache_entry

from deadlock_matches import (
    export,
    extract,
    players,
    queries,
)
from deadlock_matches.cli import match as cli_match
from deadlock_matches.cli.main import (
    build_parser,
    main,
)


@pytest.fixture(autouse=True)
def no_installed_client(monkeypatch):
    monkeypatch.setattr(extract, "installed_client_version", lambda cache_dir=None: None)


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

    assert "Only fewer than 6 Ranked games" in capsys.readouterr().out


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
    assert "Damage taken by enemy" not in out
    assert "has no damage taken from heroes" not in out


def test_match_damage_flag_shows_damage_taken_per_enemy(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000), (600, 5000)],
        damage=[
            ("citadel_weapon_mirage_set", [500, 1200]),
            ("citadel_weapon_hero1", [300, 700], 0, 2, 1),
        ],
    )

    run_main(tmp_path, "match", "--account", "42", "--damage")

    out = capsys.readouterr().out

    assert "Damage dealt to enemy, 5-minute intervals" in out
    assert "Damage taken by enemy, 5-minute intervals" in out
    assert re.search(r"Infernus\s+500\s+700\s+1,200\s+100%", out)
    assert re.search(r"Infernus\s+300\s+400\s+700\s+100%", out)
    assert out.index("Damage dealt to enemy") < out.index("Damage taken by enemy")


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


def test_match_abilities_flag_works_for_unranked_game(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    dust_devil = 1336069669
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        ability_items=[(dust_devil, 60)],
        ranked_type=0,
    )

    run_main(tmp_path, "match", "100", "--account", "42", "--abilities")

    out = capsys.readouterr().out

    assert "Ability upgrades" in out
    assert re.search(r"1:00\s+1\s+1\s+0\s+unlock\s+Dust Devil\s+1", out)


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


def test_match_items_upgrade_note_follows_a_tier_skip(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    compress_cooldown = 380806748
    transcendent_cooldown = 915014646
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        item_events=[
            (compress_cooldown, 60, 300, 1),
            (transcendent_cooldown, 300, 0, 0),
        ],
    )

    run_main(tmp_path, "match", "--account", "42", "--items")

    out = capsys.readouterr().out

    assert re.search(
        r"1:00\s+1\s+Compress Cooldown\s+spirit\s+2\s+[\d,]+\s+"
        r"into Transcendent Cooldown at 5:00",
        out,
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
    assert "bullet resist" not in out
    assert "move speed" not in out
    assert "patch the match was played on" in out


def test_match_buffs_flag_prefers_recorded_pickup_values(capsys, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        corrupted_penalty_seed=77,
        buffs=[
            ("hp_permanent_pickup_lv2", 3, True, [(200, 25.0), (200, 25.0), (700, 25.0)]),
            ("cd_permanent_pickup", 1, True, [(650, 0.5)]),
            ("gun_powerup_pickup", 1, False),
        ],
    )
    monkeypatch.setattr(cli_match.statues, "statue_map_asof", lambda at: {})

    run_main(tmp_path, "match", "--account", "42", "--buffs")

    out = capsys.readouterr().out

    assert re.search(r"max health\s+0\s+3\s+0\s+3\s+\+75", out)
    assert re.search(r"cooldown reduction\s+1\s+0\s+0\s+1\s+\+0\.5%", out)
    assert "Statue pickups, 5-minute intervals" in out
    assert re.search(r"Buff\s+0-5m\s+5-10m\s+10-15m\s+15-20m\s+20-25m\s+25-30m\s+Total", out)
    assert re.search(r"max health\s+2\s+0\s+1\s+0\s+0\s+0\s+3\n", out)
    assert re.search(r"cooldown reduction\s+0\s+0\s+1\s+0\s+0\s+0\s+1\n", out)
    assert re.search(r"Total\s+2\s+0\s+2\s+0\s+0\s+0\s+4\n", out)
    assert out.index("  max health  ") < out.index("  cooldown reduction  ", out.index("Statue"))
    assert "Gained sums the stat each pickup recorded" in out
    assert "patch the match was played on" not in out


def test_match_buffs_flag_honors_the_interval(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        buffs=[("hp_permanent_pickup_lv2", 2, True, [(200, 20.0), (700, 20.0)])],
    )

    run_main(tmp_path, "match", "--account", "42", "--buffs", "--interval", "15")

    out = capsys.readouterr().out

    assert "Statue pickups, 15-minute intervals" in out
    assert re.search(r"Buff\s+0-15m\s+15-30m\s+Total", out)
    assert re.search(r"max health\s+2\s+0\s+2\n", out)


def test_match_buffs_flag_falls_back_to_the_catalog_for_a_missing_stat(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        buffs=[
            ("hp_permanent_pickup_lv2", 2, True, [(200, 25.0), (700, None)]),
            ("cd_permanent_pickup", 1, True, [(650, 0.6)]),
        ],
    )

    run_main(tmp_path, "match", "--account", "42", "--buffs")

    out = capsys.readouterr().out

    assert re.search(r"max health\s+0\s+2\s+0\s+2\s+\+40", out)
    assert re.search(r"cooldown reduction\s+1\s+0\s+0\s+1\s+\+0\.6%", out)
    assert re.search(r"max health\s+1\s+0\s+1\s+0\s+0\s+0\s+2\n", out)


def test_match_buffs_flag_skips_the_timeline_without_pickup_times(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        buffs=[("hp_permanent_pickup_lv2", 3, True)],
    )

    run_main(tmp_path, "match", "--account", "42", "--buffs")

    out = capsys.readouterr().out

    assert "Statue pickups" not in out
    assert "patch the match was played on" in out


def test_match_buffs_flag_labels_the_later_statue_families(capsys, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        buffs=[
            ("bulletresist_permanent_pickup", 1, True),
            ("bulletresist_permanent_pickup_lv2", 3, True),
            ("range_permanent_pickup_lv2", 2, True),
            ("movespeed_permanent_pickup_lv2", 1, True),
            ("movespeed_permanent_pickup_lv3", 1, True),
        ],
    )
    values = {
        "bulletresist_permanent_pickup": ("bullet_armor_damage_resist", 0.5),
        "bulletresist_permanent_pickup_lv2": ("bullet_armor_damage_resist", 0.75),
        "spiritresist_permanent_pickup": ("tech_resist", 0.5),
        "range_permanent_pickup_lv2": ("tech_range_percent", 0.5),
        "movespeed_permanent_pickup_lv2": ("movement_speed_max", 7.874),
        "movespeed_permanent_pickup_lv3": ("movement_speed_max", 11.811),
    }
    catalog = {
        name: cli_match.statues.Statue.from_record(
            {"id": 1, "class_name": name, "stat": stat, "value": value}
        )
        for name, (stat, value) in values.items()
    }
    monkeypatch.setattr(cli_match.statues, "statue_map_asof", lambda at: catalog)

    run_main(tmp_path, "match", "--account", "42", "--buffs")

    out = capsys.readouterr().out

    assert re.search(r"bullet resist\s+1\s+3\s+0\s+4\s+\+2\.75%", out)
    assert re.search(r"spirit resist\s+0\s+0\s+0\s+0\s+-", out)
    assert re.search(r"ability range\s+0\s+2\s+0\s+2\s+\+1%", out)
    assert re.search(r"move speed\s+0\s+1\s+1\s+2\s+\+0\.5 m/s", out)


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


def test_match_combat_flag_parry_line_points_at_melee(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        custom_stats=[("Parry Success", 4), ("Parry Miss", 2)],
        item_events=[(COUNTERSPELL, 884, 0, 0)],
        damage=[("ability_melee_inferno", [100, 400], 0, 2, 1)],
    )

    run_main(tmp_path, "match", "--account", "42", "--combat")

    out = capsys.readouterr().out

    assert "Parries 4 landed, 2 missed  (--melee for the lobby table)" in out
    assert "Melee damage taken" not in out
    assert "Counterspell bought" not in out


def test_match_melee_flag_ranks_players_and_lists_buys(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000)],
        custom_stats=[("Parry Success", 4), ("Parry Miss", 2)],
        item_events=[(COUNTERSPELL, 884, 0, 0)],
        damage=[
            ("ability_melee_mirage", [50, 300], 0, 1, 2),
            ("ability_melee_inferno", [100, 400], 0, 2, 1),
            ("upgrade_melee_charge", [10, 90], 0, 2, 1),
            ("citadel_weapon_hornet", [50, 900], 0, 2, 1),
        ],
    )

    run_main(tmp_path, "match", "--account", "42", "--melee")

    out = capsys.readouterr().out

    assert "Melee" in out
    assert re.search(r"Infernus\s+enemy\s+400\s+300\s+-\s+-", out)
    assert re.search(r"Mirage \*\s+ally\s+300\s+400\s+4\s+2", out)
    assert re.search(r"Melee taken by you\n\s+Infernus\s+400", out)
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
    assert "Unstable Rift comeback souls: 267" in out
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
    g = queries.GoldSource
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
    assert re.search(r"Waves\s+1,000\s+1,000\s+2,000\s+50%", out)
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
    assert "Deaths per enemy, 5-minute intervals" in out
    assert re.search(r"Enemy\s+0-5m\s+5-10m\s+10-15m\s+15-20m\s+20-25m\s+25-30m\s+Total", out)
    assert re.search(r"Infernus\s+-\s+-\s+1\s+-\s+-\s+-\s+1", out)
    assert re.search(r"not a player\s+-\s+1\s+-\s+-\s+-\s+-\s+1", out)
    assert re.search(r"Total\s+-\s+1\s+1\s+-\s+-\s+-\s+2", out)
    assert "Damage taken by enemy" not in out
    assert re.search(r"Time\s+Killed by\s+Killed in\s+Distance\s+Respawn", out)
    assert re.search(r"5:10\s+not a player\s+2.5s\s+-\s+20s", out)
    assert re.search(r"15:00\s+Infernus\s+2.5s\s+10m\s+20s", out)
    assert out.index("5:10") < out.index("15:00")


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

    assert "Kills per enemy, 5-minute intervals" in out
    assert re.search(r"Infernus\s+-\s+1\s+-\s+-\s+-\s+-\s+1", out)
    assert re.search(r"Total\s+-\s+1\s+-\s+-\s+-\s+-\s+1", out)
    assert "Damage dealt to enemy" not in out
    assert re.search(r"Time\s+Kill\s+Killed in\s+Distance\s+Respawn", out)
    assert re.search(r"6:40\s+Infernus\s+2.5s\s+10m\s+20s", out)
    assert "Killed by" not in out


def test_match_laning_lane_blocks(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(
        cache,
        match_id=100,
        stats=[(300, 3000, 400), (600, 5000, 900)],
        death_log=((1, 2, 310), (2, 1, 700)),
        objectives=True,
        lanes=True,
    )

    run_main(tmp_path, "match", "100", "--laning", "--account", "42")

    out = capsys.readouterr().out

    assert "Laning phase through 9:00 (stat columns read at the 5:00 snapshot)" in out
    assert re.search(
        r"Yellow \(your lane\)\n\s+Lane\s+Souls\s+Kills\s+Deaths\s+Damage\s+Taken"
        r"\s+Obj damage\s+Healing",
        out,
    )
    assert re.search(r"Team\s+3,000", out)
    assert "Yours" not in out
    assert re.search(r"\* Mirage\s+3,000\s+0\s+1\s+0\s+0\s+400", out)
    assert re.search(r"Infernus\s+1,500\s+1\s+0\s+0\s+0\s+0", out)
    assert re.search(r"Net\s+\+1,500\s+-1\s+\+1\s+\+0\s+\+0\s+\+400", out)
    assert re.search(r"5:10\s+- Infernus kills Mirage", out)
    assert "Mirage kills Infernus" not in out
    assert re.search(r"6:40\s+\+ enemy Guardian falls", out)
    assert out.index("Infernus kills Mirage") < out.index("enemy Guardian falls")


def test_match_laning_without_lanes(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "match", "100", "--laning", "6", "--account", "42")

    assert "No lane assignments in this match" in capsys.readouterr().out


def test_match_rebuilds_a_missing_deaths_table_before_reading(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)])

    run_main(tmp_path, "history")
    capsys.readouterr()
    shutil.rmtree(tmp_path / "pq" / "deaths")

    run_main(tmp_path, "match", "100", "--deaths", "--account", "42")

    out = capsys.readouterr().out

    assert "Rebuilt all tables from the archive (the deaths table is missing)" in out
    assert "No deaths in this match" in out


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
    monkeypatch.setattr(players, "PLAYERS_PARQUET_DIR", store)

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


def test_match_teams_timeline_splits_ten_minute_brackets(capsys, tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)], objectives=True)
    monkeypatch.setattr(
        cli_match,
        "_objective_events",
        lambda row, args: [(500, "a"), (580, "b"), (700, "c"), (1900, "d")],
    )

    run_main(tmp_path, "match", "--account", "42", "--teams")

    out = capsys.readouterr().out

    assert "    8:20  a\n    9:40  b\n\n   11:40  c\n\n   31:40  d" in out


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


def test_match_without_an_id_picks_the_latest_across_the_split(capsys, tmp_path):
    split_era_cache(tmp_path)

    run_main(tmp_path, "match", "--account", "42")

    out = capsys.readouterr().out

    assert "Match 102" in out


def test_match_standard_flag_picks_the_latest_unranked_game(capsys, tmp_path):
    split_era_cache(tmp_path)

    run_main(tmp_path, "match", "--account", "42", "--standard")

    out = capsys.readouterr().out

    assert "Match 101" in out


def test_match_lobby_average_uses_the_era_names(capsys, tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    write_cache_entry(cache, match_id=100, stats=[(300, 3000)], badges=(63, 61))

    run_main(tmp_path, "match", "--account", "42")

    assert "Lobby average: The Hidden King Emissary III, The Archmother Emissary I" in (
        capsys.readouterr().out
    )
