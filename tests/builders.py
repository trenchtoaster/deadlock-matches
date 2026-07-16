import datetime as dt
import zoneinfo

from deadlock_matches import export, schemas
from deadlock_matches.assets import history, store
from deadlock_matches.extract import pb

START = 1783000000


LOCAL_DAY = (
    dt.datetime.fromtimestamp(START, dt.UTC).astimezone(zoneinfo.ZoneInfo("America/Chicago")).date()
)


MYSTIC_SHOT = 395867183


ECHO_SHARD = 630839635


DUST_DEVIL = 1336069669


RIVAL = 555


def add_custom_stats(info, entries):
    for stat_id, (name, _) in enumerate(entries, start=1):
        reg = info.custom_user_stats.add()
        reg.name = name
        reg.id = stat_id

    snap = info.players[0].stats[-1]

    for stat_id, (_, value) in enumerate(entries, start=1):
        cs = snap.custom_user_stats.add()
        cs.id = stat_id
        cs.value = value


def build_match(match_id=100, account_id=42, level=None, max_health=None):
    info = pb.CMsgMatchMetaDataContents().match_info
    info.match_id = match_id
    info.start_time = START
    info.duration_s = 1800
    info.winning_team = pb.k_ECitadelLobbyTeam_Team1
    info.match_mode = pb.k_ECitadelMatchMode_Unranked

    a = info.players.add()
    a.account_id = account_id
    a.hero_id = 52
    a.team = pb.k_ECitadelLobbyTeam_Team1
    a.player_slot = 1

    for item_id, t in [(DUST_DEVIL, 60), (MYSTIC_SHOT, 300), (ECHO_SHARD, 900)]:
        it = a.items.add()
        it.item_id = item_id
        it.game_time_s = t

    if level is not None and max_health is not None:
        s = a.stats.add()
        s.time_stamp_s = 600
        s.level = level
        s.max_health = max_health

    for t, hit, miss, body, crit, dealt in [(180, 10, 10, 8, 2, 200), (600, 70, 30, 45, 15, 1500)]:
        s = a.stats.add()
        s.time_stamp_s = t
        s.net_worth = t * 10
        s.shots_hit = hit
        s.shots_missed = miss
        s.hero_bullets_hit = body
        s.hero_bullets_hit_crit = crit
        s.player_damage = dealt

    b = info.players.add()
    b.account_id = 43
    b.hero_id = 1
    b.team = pb.k_ECitadelLobbyTeam_Team0
    b.player_slot = 2

    it = b.items.add()
    it.item_id = ECHO_SHARD
    it.game_time_s = 400

    s = b.stats.add()
    s.time_stamp_s = 180

    dm = info.damage_matrix
    for name, stat_type in [
        ("citadel_weapon_mirage", 0),
        ("Bullet", 0),
        ("mirage_tornado", 1),
        ("upgrade_crackshot", 0),
    ]:
        dm.source_details.source_name.append(name)
        dm.source_details.stat_type.append(stat_type)

    d = dm.damage_dealers.add()
    d.dealer_player_slot = 1

    gun = d.damage_sources.add()
    gun.source_details_index = 0
    hero_target = gun.damage_to_players.add()
    hero_target.target_player_slot = 2
    hero_target.damage.extend([50, 150])
    creep_target = gun.damage_to_players.add()
    creep_target.target_player_slot = 0
    creep_target.damage.extend([999])

    total = d.damage_sources.add()
    total.source_details_index = 1
    t = total.damage_to_players.add()
    t.target_player_slot = 2
    t.damage.extend([150])

    heal = d.damage_sources.add()
    heal.source_details_index = 2
    t = heal.damage_to_players.add()
    t.target_player_slot = 2
    t.damage.extend([30])

    shot = d.damage_sources.add()
    shot.source_details_index = 3
    t = shot.damage_to_players.add()
    t.target_player_slot = 2
    t.damage.extend([40, 90])

    return info


def build_day_match(match_id, day, *, won):
    info = build_match(match_id=match_id)
    info.start_time = START + day * 86400
    info.winning_team = 1 if won else 0

    return info


def build_abandon_match(match_id, *, leaver, abandon_s, won=True, not_scored=False):
    info = build_match(match_id=match_id)
    info.winning_team = 1 if won else 0
    info.not_scored = not_scored

    if leaver == "you":
        p = info.players[0]

    elif leaver == "enemy":
        p = info.players[1]

    else:
        p = info.players.add()
        p.account_id = 44
        p.hero_id = 3
        p.team = pb.k_ECitadelLobbyTeam_Team1
        p.player_slot = 3

    p.abandon_match_time_s = abandon_s

    return info


def build_rank_match(match_id=700):
    info = build_match(match_id=match_id)

    c = info.players.add()
    c.account_id = 44
    c.hero_id = 3
    c.team = pb.k_ECitadelLobbyTeam_Team1
    c.player_slot = 3

    s = c.stats.add()
    s.time_stamp_s = 600
    s.player_damage = 900

    return info


def build_movement_match(match_id=100):
    info = build_match(match_id=match_id)

    c = info.players.add()
    c.account_id = 44
    c.hero_id = 3
    c.team = pb.k_ECitadelLobbyTeam_Team1
    c.player_slot = 3

    d = info.players[0].death_details.add()
    d.game_time_s = 100
    d.time_to_kill_s = 2.0
    d.death_duration_s = 30
    d.killer_player_slot = 2
    d.death_pos.x = 500.0
    d.death_pos.y = 500.0
    d.death_pos.z = 0.0

    s = info.players[0].stats[-1]
    g = s.gold_sources.add()
    g.source = 2
    g.gold = 700

    mp = info.match_paths
    mp.interval_s = 1.0
    mp.x_resolution = 100
    mp.y_resolution = 100

    me = mp.paths.add()
    me.player_slot = 1
    me.x_max = 10000.0
    me.y_max = 10000.0
    me.x_pos.extend(range(10))
    me.y_pos.extend([0] * 10)
    me.health.extend([100] * 10)
    me.combat_type.extend([1, 1, 1, 1, 0, 0, 0, 0, 0, 0])
    me.move_type.extend([0, 4, 4, 3, 0, 7, 8, 7, 6, 0])

    for slot, pos in [(2, 5), (3, 90)]:
        p = mp.paths.add()
        p.player_slot = slot
        p.x_max = 10000.0
        p.y_max = 10000.0
        p.x_pos.extend([pos] * 120)
        p.y_pos.extend([pos] * 120)
        p.health.extend([100] * 120)
        p.combat_type.extend([0] * 120)
        p.move_type.extend([0] * 120)

    return info


def build_interval_match(match_id=500):
    info = build_match(match_id=match_id)
    info.duration_s = 1190

    a = info.players[0]
    del a.stats[:]

    rows = [
        (300, 3000, 1000, 500, 20, 2, 4, 1, 2, 300, 200, 0),
        (600, 5000, 1500, 900, 30, 5, 4, 1, 3, 300, 500, 150),
        (1180, 8000, 4000, 2000, 55, 9, 6, 4, 7, 1500, 900, 400),
    ]
    for t, worth, dealt, taken, creeps, neutrals, denies, kills, assists, obj, heal, prev in rows:
        s = a.stats.add()
        s.time_stamp_s = t
        s.net_worth = worth
        s.player_damage = dealt
        s.player_damage_taken = taken
        s.creep_kills = creeps
        s.neutral_kills = neutrals
        s.denies = denies
        s.kills = kills
        s.assists = assists
        s.boss_damage = obj
        s.player_healing = heal
        s.heal_prevented = prev

    for t in (250, 1100):
        d = a.death_details.add()
        d.game_time_s = t

    b = info.players[1]
    for t in (200, 950, 1150):
        d = b.death_details.add()
        d.game_time_s = t
        d.killer_player_slot = 1

    info.damage_matrix.sample_time_s.extend([300, 600, 1180])

    return info


def build_laning_match(match_id=800):
    info = build_match(match_id=match_id)
    info.players[0].assigned_lane = 1
    info.players[1].assigned_lane = 1

    for s, obj in zip(info.players[0].stats, (150, 800), strict=True):
        s.boss_damage = obj

    green = (
        (44, 3, pb.k_ECitadelLobbyTeam_Team1, 3),
        (45, 4, pb.k_ECitadelLobbyTeam_Team0, 4),
    )
    for account_id, hero_id, team, slot in green:
        p = info.players.add()
        p.account_id = account_id
        p.hero_id = hero_id
        p.team = team
        p.player_slot = slot
        p.assigned_lane = 6

        s = p.stats.add()
        s.time_stamp_s = 540
        s.net_worth = 4000

    d = info.players[0].death_details.add()
    d.game_time_s = 100
    d.killer_player_slot = 2

    d = info.players[1].death_details.add()
    d.game_time_s = 400
    d.killer_player_slot = 1

    d = info.players[2].death_details.add()
    d.game_time_s = 700
    d.killer_player_slot = 4

    return info


def build_lane_battle(
    match_id, *, won=True, day=0, mate_deaths=(), ally_abandon=None, not_scored=False
):
    info = build_laning_match(match_id=match_id)
    info.start_time = START + day * 86400
    info.winning_team = 1 if won else 0
    info.not_scored = not_scored

    mate = info.players[2]

    for t in mate_deaths:
        d = mate.death_details.add()
        d.game_time_s = t
        d.killer_player_slot = 4

    if ally_abandon is not None:
        mate.abandon_match_time_s = ally_abandon

    return info


def build_sold_match(match_id=300, *, rebuy=False):
    info = build_match(match_id=match_id)
    info.players[0].items[1].sold_time_s = 900

    if rebuy:
        it = info.players[0].items.add()
        it.item_id = MYSTIC_SHOT
        it.game_time_s = 1200

        for t, dealt in [(1000, 2000), (1500, 2600)]:
            s = info.players[0].stats.add()
            s.time_stamp_s = t
            s.player_damage = dealt

    return info


def build_upgrade_match(match_id=310):
    info = build_match(match_id=match_id)
    info.players[0].items[0].sold_time_s = 700

    consumed = info.players[0].items[1]
    consumed.sold_time_s = 900
    consumed.flags = 1

    return info


def build_double_upgrade_match(match_id=311):
    info = build_upgrade_match(match_id=match_id)

    it = info.players[0].items.add()
    it.item_id = RIVAL
    it.game_time_s = 900

    return info


def build_skip_upgrade_match(match_id=312):
    info = build_match(match_id=match_id)
    del info.players[0].items[1]

    consumed = info.players[0].items[0]
    consumed.sold_time_s = 900
    consumed.flags = 1

    return info


def build_chain_collision_match(match_id=313):
    info = build_match(match_id=match_id)
    info.players[0].items[1].game_time_s = 900

    it = info.players[0].items.add()
    it.item_id = RIVAL
    it.game_time_s = 900

    consumed = info.players[0].items[0]
    consumed.sold_time_s = 900
    consumed.flags = 1

    return info


def build_souls_match(match_id=100):
    info = build_match(match_id=match_id)
    snap = info.players[0].stats[-1]

    for source, gold, orbs in (
        (export.GoldSource.LANE_CREEPS, 2000, 500),
        (export.GoldSource.PLAYERS, 600, 0),
        (export.GoldSource.BOSSES, 800, 0),
        (export.GoldSource.TEAM_BONUS, 100, 0),
        (export.GoldSource.DENIES, 0, 0),
    ):
        gs = snap.gold_sources.add()
        gs.source = source
        gs.gold = gold
        gs.gold_orbs = orbs

    return info


def build_heal_match(match_id=100):
    info = build_match(match_id=match_id)
    dm = info.damage_matrix

    dm.source_details.source_name.append("upgrade_toxic_bullets")
    dm.source_details.stat_type.append(1)

    src = dm.damage_dealers[0].damage_sources.add()
    src.source_details_index = 4
    t = src.damage_to_players.add()
    t.target_player_slot = 1
    t.damage.extend([20, 50])

    dm.source_details.source_name.append("citadel_ability_dash")
    dm.source_details.stat_type.append(0)

    src = dm.damage_dealers[0].damage_sources.add()
    src.source_details_index = 5
    t = src.damage_to_players.add()
    t.target_player_slot = 2
    t.damage.extend([0, 0])

    dm.source_details.source_name.append("upgrade_toxic_bullets")
    dm.source_details.stat_type.append(2)

    src = dm.damage_dealers[0].damage_sources.add()
    src.source_details_index = 6
    t = src.damage_to_players.add()
    t.target_player_slot = 2
    t.damage.extend([10, 25])

    return info


def _write_item_history(parquet_dir, slots=None):
    """Write a small item_history table so delivery can resolve item slots."""
    if slots is None:
        slots = {"upgrade_crackshot": "weapon", "upgrade_toxic_bullets": "weapon"}

    rows = [
        {
            "item_id": 9000 + n,
            "name": class_name,
            "class_name": class_name,
            "cost": 500,
            "slot": slot,
            "tier": 1,
            "is_active": False,
            "description": None,
            "era_from": dt.datetime(2020, 1, 1, tzinfo=dt.UTC),
            "client_version": 1,
        }
        for n, (class_name, slot) in enumerate(slots.items())
    ]
    path = schemas.table_path("item_history", parquet_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    schemas.conform("item_history", rows).write_parquet(path)


def _write_effective_assets(parquet_dir):
    era = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    priced = [
        (DUST_DEVIL, "Dust Devil", "upgrade_dust", 500, 1),
        (MYSTIC_SHOT, "Mystic Shot", "upgrade_crackshot", 1250, 2),
        (ECHO_SHARD, "Echo Shard", "upgrade_echo", 3000, 3),
        (RIVAL, "Rival", "upgrade_rival", 2000, 3),
    ]
    rows = [
        {
            "item_id": item_id,
            "name": name,
            "class_name": class_name,
            "cost": cost,
            "slot": "spirit",
            "tier": tier,
            "is_active": False,
            "description": None,
            "era_from": era,
            "client_version": 100,
        }
        for item_id, name, class_name, cost, tier in priced
    ]
    comps = [
        {
            "item_id": item_id,
            "position": 0,
            "component_class_name": component,
            "era_from": era,
            "client_version": 100,
        }
        for item_id, component in (
            (ECHO_SHARD, "upgrade_crackshot"),
            (RIVAL, "upgrade_crackshot"),
            (MYSTIC_SHOT, "upgrade_dust"),
        )
    ]

    for table, records in (("item_history", rows), ("item_component_history", comps)):
        path = schemas.table_path(table, parquet_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        schemas.conform(table, records).write_parquet(path)


def _hero_rec(max_health, rs=500):
    return {
        "id": 52,
        "name": "Mirage",
        "class_name": "hero_mirage",
        "stats": {"max_health": max_health},
        "level_up": {"base_health_from_level": 10.0},
        "levels": [
            {
                "level": 1,
                "required_souls": 0,
                "standard_upgrade": False,
                "currencies": ["ability_unlocks"],
            },
            {
                "level": 2,
                "required_souls": rs,
                "standard_upgrade": True,
                "currencies": ["ability_points"],
            },
        ],
    }


def _seed_hero_history(tmp_path, monkeypatch, first, second):
    path = tmp_path / "hero_history.parquet"
    history.write(
        path,
        [
            {"from": "2026-01-01T00:00:00", "build": 100, "records": {"52": first}},
            {"from": "2026-02-01T00:00:00", "build": 200, "records": {"52": second}},
        ],
    )
    monkeypatch.setattr(store, "store_dir", lambda: tmp_path)
