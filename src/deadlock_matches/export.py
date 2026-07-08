"""Export the match archive to parquet tables for dataframe analysis.

- the .bin archive stays the source of truth, tables are derived and fully rebuilt
- protobuf gold_* fields come out as souls_* (the game calls the currency souls)
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

from deadlock_matches import abilities, extract, heroes, items, paths, schemas, timeline

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable

    from deadlock_matches.extract import MatchInfo

PARQUET_DIR = paths.data_dir() / "deadlock-matches/parquet"

SOURCE_NAMES = {
    timeline.GoldSource.PLAYERS: "players",
    timeline.GoldSource.LANE_CREEPS: "troopers",
    timeline.GoldSource.NEUTRALS: "jungle",
    timeline.GoldSource.BOSSES: "bosses",
    timeline.GoldSource.TREASURE: "treasure",
    timeline.GoldSource.ASSISTS: "assists",
    timeline.GoldSource.DENIES: "denies",
    timeline.GoldSource.TEAM_BONUS: "team_bonus",
    timeline.GoldSource.ABILITY_ASSASSINATE: "assassinate",
    timeline.GoldSource.ITEM_TROPHY_COLLECTOR: "trophy_collector",
    timeline.GoldSource.ITEM_CULTIST_SACRIFICE: "cultist_sacrifice",
    timeline.GoldSource.BREAKABLE: "breakables",
    timeline.GoldSource.ITEM_GOOSE_EGG: "goose_egg",
}

LANE_NAMES = {1: "yellow", 4: "blue", 6: "green"}

OBJECTIVE_LANES = {1: "yellow", 3: "blue", 4: "green"}

OBJECTIVE_NAMES = {
    0: "Weakened Patron",
    9: "Patron",
    10: "Shrine",
    11: "Shrine",
}
OBJECTIVE_NAMES.update(dict.fromkeys((1, 2, 3, 4), "Guardian"))
OBJECTIVE_NAMES.update({i + 4: "Walker" for i in (1, 2, 3, 4)})
OBJECTIVE_NAMES.update({i + 11: "Base Guardians" for i in (1, 2, 3, 4)})

OBJECTIVE_LANE_IDS = {i: i for i in (1, 2, 3, 4)}
OBJECTIVE_LANE_IDS.update({i + 4: i for i in (1, 2, 3, 4)})
OBJECTIVE_LANE_IDS.update({i + 11: i for i in (1, 2, 3, 4)})


def _stat_type_names() -> dict[int, str]:
    """Readable names for the damage matrix EStatType enum (0 -> damage, 1 -> healing, ...)."""
    desc: Any = extract.pb.CMsgMatchPlayerDamageMatrix.DESCRIPTOR
    enum = desc.enum_types_by_name["EStatType"]
    return {
        v.number: re.sub(r"(?<!^)(?=[A-Z])", "_", v.name.removeprefix("k_eType_")).lower()
        for v in enum.values
    }


STAT_NAMES = _stat_type_names()


def _path_enum_names(enum_name: str, prefix: str) -> dict[int, str]:
    """Readable names for a CMsgMatchPlayerPathsData enum (k_eMoveType_AirDash -> air_dash)."""
    desc: Any = extract.pb.CMsgMatchPlayerPathsData.DESCRIPTOR
    enum = desc.enum_types_by_name[enum_name]

    return {
        v.number: re.sub(
            r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])",
            "_",
            v.name.removeprefix(prefix),
        ).lower()
        for v in enum.values
    }


COMBAT_NAMES = _path_enum_names("ECombatType", "k_eCombatType_")
MOVE_NAMES = _path_enum_names("EMoveType", "k_eMoveType_")


def _to_length(values: Any, n: int) -> list:
    """Cut the array to exactly n entries, filling with None when it is shorter."""
    out = list(values[:n])
    out.extend([None] * (n - len(out)))

    return out


def _movement_frame(info: MatchInfo, account_id: int, path: Any) -> pl.DataFrame:
    """One movement row per second for one player, with the quantized track decoded to world units."""
    mp = info.match_paths
    sx = (path.x_max - path.x_min) / mp.x_resolution if mp.x_resolution else 0.0
    sy = (path.y_max - path.y_min) / mp.y_resolution if mp.y_resolution else 0.0
    interval = mp.interval_s or 1.0
    n = min(len(path.x_pos), int(info.duration_s / interval) + 1)

    return pl.DataFrame(
        {
            "x_pos": list(path.x_pos[:n]),
            "y_pos": list(path.y_pos[:n]),
            "health_percent": _to_length(path.health, n),
            "combat_raw": _to_length(path.combat_type, n),
            "move_raw": _to_length(path.move_type, n),
        }
    ).select(
        match_id=pl.lit(info.match_id),
        account_id=pl.lit(account_id),
        game_time_s=(pl.int_range(pl.len()) * interval).round(0).cast(pl.Int64),
        x=path.x_min + pl.col("x_pos") * sx,
        y=path.y_min + pl.col("y_pos") * sy,
        health_percent=pl.col("health_percent"),
        combat_type=pl.col("combat_raw")
        .cast(pl.String)
        .replace({str(k): v for k, v in COMBAT_NAMES.items()}),
        move_type=pl.col("move_raw")
        .cast(pl.String)
        .replace({str(k): v for k, v in MOVE_NAMES.items()}),
    )


TOTAL_RE = re.compile(r"^[A-Z][A-Za-z]*$")

BULLET_PROC_OVERRIDES = {
    "upgrade_ethereal_bullets",
    "upgrade_quick_silver",
    "upgrade_siphon_bullets",
}


def _damage_category(class_name: str) -> str:
    """Bucket a damage source as gun, item, ability, or a match screen total.

    The matrix carries both. "Bullet" duplicates the citadel_weapon_* gun row and
    "Ability" overlaps the individual ability rows, so never sum totals with details.
    """
    if class_name.startswith("citadel_weapon"):
        return "gun"

    if class_name.startswith("upgrade_"):
        return "item"

    if TOTAL_RE.match(class_name):
        return "total"

    return "ability"


def _delivery(class_name: str, by_class: dict[str, items.Item] | None = None) -> str | None:
    """Damage group of a detail row, None for totals rows.

    - gun = the gun itself (body shots + headshots)
    - gun_proc = item procs that only fire when a shot lands (Mystic Shot,
      Headhunter, Toxic), even when the damage counts as spirit
    - ability = the kit itself
    - spirit_proc = spirit items with their own damage lines (Scourge, Escalating Exposure)
    - BULLET_PROC_OVERRIDES: bullet-proc items the shop files outside the weapon
      slot (Magnum, Quicksilver, Siphon) still count as gun_proc
    - by_class: item lookup to use, defaults to the bundled current snapshot
    """
    cat = _damage_category(class_name)

    if cat == "total":
        return None

    if cat == "gun":
        return "gun"

    if cat == "item":
        if class_name in BULLET_PROC_OVERRIDES:
            return "gun_proc"

        if by_class is None:
            item = items.item_by_class_name(class_name)
        else:
            item = by_class.get(class_name)

        return "gun_proc" if item and item.slot == "weapon" else "spirit_proc"

    return "ability"


def build_tables(
    infos: Iterable[MatchInfo],
    assets_history: Path | None = None,
    exclude: Collection[str] = (),
) -> dict[str, pl.DataFrame]:
    """Build the parquet tables from MatchInfo messages.

    - builds matches, players, stats, soul_sources, item_events, damage,
      damage_sources, mid_boss, objectives, and deaths
    - item_events.attribution: 'proc' = has its own damage lines (Scourge, Escalating Exposure),
      'stat' = never shows up as a source, value hides in other rows (Boundless Spirit, Echo Shard)
    - empirical over the batch, not a hardcoded list
    - item cost/tier/slot resolve against the dated assets snapshot in effect at
      match time (item_events.assets_date), so rebuilds don't reprice history
    - exclude skips tables by name (the exclude list in config.toml), which
      keeps the big per-second movement table out of the rebuild

    assets_history is the dated snapshot folder, defaults to the standard data directory.
    """
    infos = list(infos)

    proc_classes = {
        info.damage_matrix.source_details.source_name[i]
        for info in infos
        for i, st in enumerate(info.damage_matrix.source_details.stat_type)
        if st == 0 and info.damage_matrix.source_details.source_name[i].startswith("upgrade_")
    }

    matches: list[dict] = []
    players: list[dict] = []
    stats: list[dict] = []
    sources: list[dict] = []
    item_events: list[dict] = []
    damage: list[dict] = []
    damage_sources: list[dict] = []
    mid_boss: list[dict] = []
    objectives: list[dict] = []
    tracks: list[pl.DataFrame] = []
    deaths: list[dict] = []

    for info in infos:
        start_time = dt.datetime.fromtimestamp(info.start_time, dt.UTC)
        snapshot, snapshot_day = items.snapshot_asof(start_time, assets_history)
        assets_date = dt.date.fromisoformat(snapshot_day) if snapshot_day else None
        im = items.item_map(snapshot)
        by_class = {i.class_name: i for i in im.values() if i.class_name}

        matches.append(
            {
                "match_id": info.match_id,
                "start_time": start_time,
                "duration_s": info.duration_s,
                "winning_team": info.winning_team,
                "match_mode": info.match_mode,
                "game_mode": info.game_mode,
                "average_badge_team0": (
                    info.average_badge_team0 if info.HasField("average_badge_team0") else None
                ),
                "average_badge_team1": (
                    info.average_badge_team1 if info.HasField("average_badge_team1") else None
                ),
            }
        )

        slot_to_account = {p.player_slot: p.account_id for p in info.players}
        path_by_slot = {p.player_slot: p for p in info.match_paths.paths}

        mid_boss.extend(
            {
                "match_id": info.match_id,
                "destroyed_time_s": m.destroyed_time_s,
                "team_killed": m.team_killed,
                "team_claimed": m.team_claimed,
            }
            for m in info.mid_boss
        )

        objectives.extend(
            {
                "match_id": info.match_id,
                "team": o.team,
                "objective_id": o.team_objective_id,
                "objective": OBJECTIVE_NAMES.get(o.team_objective_id),
                "lane": OBJECTIVE_LANES.get(OBJECTIVE_LANE_IDS.get(o.team_objective_id, 0)),
                "destroyed_time_s": o.destroyed_time_s or None,
                "first_damage_time_s": o.first_damage_time_s or None,
                "player_damage": o.player_damage,
                "creep_damage": o.creep_damage,
            }
            for o in info.objectives
        )

        for p in info.players:
            players.append(
                {
                    "match_id": info.match_id,
                    "account_id": p.account_id,
                    "hero_id": p.hero_id,
                    "hero": heroes.hero_name(p.hero_id),
                    "team": p.team,
                    "player_slot": p.player_slot,
                    "assigned_lane": p.assigned_lane,
                    "lane": LANE_NAMES.get(p.assigned_lane),
                    "won": p.team == info.winning_team,
                    "kills": p.kills,
                    "deaths": p.deaths,
                    "assists": p.assists,
                    "net_worth": p.net_worth,
                    "last_hits": p.last_hits,
                    "denies": p.denies,
                    "mvp_rank": p.mvp_rank,
                }
            )

            for s in p.stats:
                stats.append(
                    {
                        "match_id": info.match_id,
                        "account_id": p.account_id,
                        **{schemas.souls(f): getattr(s, f) for f in schemas.STAT_FIELDS},
                    }
                )
                sources.extend(
                    {
                        "match_id": info.match_id,
                        "account_id": p.account_id,
                        "time_stamp_s": s.time_stamp_s,
                        "source": g.source,
                        "source_name": SOURCE_NAMES.get(g.source, str(g.source)),
                        "souls": g.gold,
                        "souls_orbs": g.gold_orbs,
                    }
                    for g in s.gold_sources
                )

            track = path_by_slot.get(p.player_slot)
            if "movement" not in exclude and track is not None:
                tracks.append(_movement_frame(info, p.account_id, track))

            deaths.extend(
                {
                    "match_id": info.match_id,
                    "account_id": p.account_id,
                    "game_time_s": d.game_time_s,
                    "time_to_kill_s": d.time_to_kill_s,
                    "death_duration_s": d.death_duration_s,
                    "killer_account_id": slot_to_account.get(d.killer_player_slot),
                    "x": d.death_pos.x if d.HasField("death_pos") else None,
                    "y": d.death_pos.y if d.HasField("death_pos") else None,
                    "z": d.death_pos.z if d.HasField("death_pos") else None,
                    "killer_x": d.killer_pos.x if d.HasField("killer_pos") else None,
                    "killer_y": d.killer_pos.y if d.HasField("killer_pos") else None,
                    "killer_z": d.killer_pos.z if d.HasField("killer_pos") else None,
                }
                for d in p.death_details
            )

            for it in p.items:
                item = im.get(it.item_id)

                item_events.append(
                    {
                        "match_id": info.match_id,
                        "account_id": p.account_id,
                        "game_time_s": it.game_time_s,
                        "item_id": it.item_id,
                        "item": item.name if item else None,
                        "cost": item.cost if item else None,
                        "slot": item.slot if item else None,
                        "tier": item.tier if item else None,
                        "sold_time_s": it.sold_time_s,
                        "flags": it.flags,
                        "attribution": (
                            "proc" if item and item.class_name in proc_classes else "stat"
                        ),
                        "assets_date": assets_date,
                    }
                )
        details = info.damage_matrix.source_details
        sample_times = list(info.damage_matrix.sample_time_s)
        cumulative: dict[tuple[int, int, bool], dict[int, int]] = {}

        for d in info.damage_matrix.damage_dealers:
            for src in d.damage_sources:
                i = src.source_details_index

                for t in src.damage_to_players:
                    if not t.damage:
                        continue

                    damage.append(
                        {
                            "match_id": info.match_id,
                            "dealer_account_id": slot_to_account.get(d.dealer_player_slot),
                            "target_account_id": slot_to_account.get(t.target_player_slot),
                            "target_player_slot": t.target_player_slot,
                            "source_name": abilities.label(details.source_name[i]),
                            "source_class": details.source_name[i],
                            "category": _damage_category(details.source_name[i]),
                            "delivery": _delivery(details.source_name[i], by_class),
                            "stat": STAT_NAMES.get(details.stat_type[i], str(details.stat_type[i])),
                            "damage": t.damage[-1],
                        }
                    )

                    if not sample_times:
                        continue

                    vs_heroes = slot_to_account.get(t.target_player_slot) is not None
                    values = t.damage[-len(sample_times) :]
                    acc = cumulative.setdefault((d.dealer_player_slot, i, vs_heroes), {})

                    for ts, v in zip(sample_times[-len(values) :], values, strict=True):
                        acc[ts] = acc.get(ts, 0) + v

        for (slot, i, vs_heroes), acc in cumulative.items():
            source = details.source_name[i]

            damage_sources.extend(
                {
                    "match_id": info.match_id,
                    "dealer_account_id": slot_to_account.get(slot),
                    "source_name": abilities.label(source),
                    "source_class": source,
                    "category": _damage_category(source),
                    "delivery": _delivery(source, by_class),
                    "stat": STAT_NAMES.get(details.stat_type[i], str(details.stat_type[i])),
                    "vs_heroes": vs_heroes,
                    "time_stamp_s": ts,
                    "damage": v,
                }
                for ts, v in sorted(acc.items())
            )

    tables = {
        "matches": schemas.conform("matches", matches),
        "players": schemas.conform("players", players),
        "stats": schemas.conform("stats", stats),
        "soul_sources": schemas.conform("soul_sources", sources),
        "item_events": schemas.conform("item_events", item_events),
        "damage": schemas.conform("damage", damage),
        "damage_sources": schemas.conform("damage_sources", damage_sources),
        "mid_boss": schemas.conform("mid_boss", mid_boss),
        "objectives": schemas.conform("objectives", objectives),
        "deaths": schemas.conform("deaths", deaths),
    }

    if "movement" not in exclude:
        tables["movement"] = schemas.conform("movement", pl.concat(tracks) if tracks else [])

    return {name: df for name, df in tables.items() if name not in exclude}


def export_all(
    archive_dir: str | Path | None = None,
    out_dir: str | Path | None = None,
    assets_history: Path | None = None,
    exclude: Collection[str] = (),
) -> dict[str, int]:
    """Rebuild every parquet table from the archived .bin matches.

    - all three directories default to the standard locations (the match
      archive, PARQUET_DIR, and the dated assets history)
    - excluded tables are skipped AND their leftover parquet files removed,
      so an old copy never goes stale next to fresh tables
    """
    archive_dir = extract.ARCHIVE_DIR if archive_dir is None else Path(archive_dir)
    out_dir = PARQUET_DIR if out_dir is None else Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    infos = []
    for path in sorted(archive_dir.glob("*.bin")):
        try:
            infos.append(extract.load(path))
        except ValueError:
            continue

    counts = {}
    for name, df in build_tables(infos, assets_history, exclude).items():
        df.write_parquet(out_dir / f"{name}.parquet")
        counts[name] = len(df)

    for name in exclude:
        (out_dir / f"{name}.parquet").unlink(missing_ok=True)

    return counts
