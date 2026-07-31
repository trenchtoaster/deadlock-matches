"""Export the match archive to parquet tables for dataframe analysis.

- the .bin archive stays the source of truth, tables are derived and fully rebuilt
- protobuf gold_* fields come out as souls_* (the game calls the currency souls)
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

from deadlock_matches import (
    extract,
    paths,
    schemas,
)
from deadlock_matches.assets import history, items, store, unnest

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Iterator

    from deadlock_matches.extract import MatchInfo

PARQUET_DIR = paths.data_dir() / "deadlock-matches/parquet"

EXPORT_LOGIC_VERSION = 2
PROGRESS_EVERY = 50


def read_stamp(out_dir: str | Path) -> dict[str, Any]:
    """Read the export stamp, empty before the first stamped export."""
    path = Path(out_dir) / "export_stamp.json"

    if not path.is_file():
        return {}

    return json.loads(path.read_text(encoding="utf-8"))


def update_stamp(out_dir: str | Path, **fields: Any) -> None:
    """Merge fields into the export stamp file."""
    path = Path(out_dir) / "export_stamp.json"
    data = read_stamp(out_dir)
    data.update(fields)
    path.write_text(json.dumps(data), encoding="utf-8")


def item_horizon() -> str | None:
    """Return the newest committed item era start, None without history.

    Matches that start past this time bake the newest known era instead of
    their own, so they need a re-export once the history catches up.
    """
    eras = history.eras(store.read_path("item_history.parquet"))

    if not eras:
        return None

    return eras[-1][0]


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


def _movement_frame(
    info: MatchInfo, start_time: dt.datetime, player: Any, path: Any
) -> pl.DataFrame:
    """Build one movement row per second for one player, converting the stored path to world units."""
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
        },
        schema_overrides={
            "health_percent": pl.Int64,
            "combat_raw": pl.Int64,
            "move_raw": pl.Int64,
        },
    ).select(
        match_id=pl.lit(info.match_id),
        start_time=pl.lit(start_time),
        account_id=pl.lit(player.account_id),
        hero_id=pl.lit(player.hero_id),
        game_time_s=(pl.int_range(pl.len()) * interval).round(0).cast(pl.Int64),
        x=path.x_min + pl.col("x_pos") * sx,
        y=path.y_min + pl.col("y_pos") * sy,
        health_percent=pl.col("health_percent"),
        combat_type=pl.col("combat_raw").replace_strict(
            COMBAT_NAMES, default=pl.col("combat_raw").cast(pl.String), return_dtype=pl.String
        ),
        move_type=pl.col("move_raw").replace_strict(
            MOVE_NAMES, default=pl.col("move_raw").cast(pl.String), return_dtype=pl.String
        ),
    )


def _movement_intervals_frame(frame: pl.DataFrame) -> pl.DataFrame:
    """Aggregate per second movement data for one player to per minute counts.

    - keeps alive seconds only
    - distance skips zipline seconds, teleports, and gaps between alive seconds
    - the counts sum to the same numbers at any coarser interval
    """
    contiguous = pl.col("game_time_s") - pl.col("prev_time") == 1
    walking = (pl.col("move_type") != "ziplining") & (pl.col("prev_move") != "ziplining")

    return (
        frame.filter(pl.col("health_percent") > 0)
        .sort("game_time_s")
        .with_columns(
            pl.col("game_time_s").shift(1).alias("prev_time"),
            pl.col("move_type").shift(1).alias("prev_move"),
            pl.col("x").shift(1).alias("prev_x"),
            pl.col("y").shift(1).alias("prev_y"),
        )
        .with_columns(
            ((pl.col("x") - pl.col("prev_x")) ** 2 + (pl.col("y") - pl.col("prev_y")) ** 2)
            .sqrt()
            .alias("step")
        )
        .with_columns(
            pl.when(contiguous & walking & (pl.col("step") < 2500))
            .then(pl.col("step"))
            .alias("step")
        )
        .group_by(
            "match_id",
            "start_time",
            "account_id",
            "hero_id",
            (pl.col("game_time_s") // 60 * 60).alias("start_s"),
        )
        .agg(
            pl.len().alias("alive_s"),
            pl.col("step").is_not_null().sum().alias("moving_s"),
            (pl.col("step") < 40).sum().alias("stationary_s"),
            (pl.col("move_type") == "slide").sum().alias("slide_s"),
            (pl.col("move_type") == "in_air").sum().alias("in_air_s"),
            (pl.col("move_type") == "ziplining").sum().alias("zipline_s"),
            (pl.col("combat_type") == "player").sum().alias("combat_s"),
            ((pl.col("move_type") == "ground_dash") & (pl.col("prev_move") != "ground_dash"))
            .sum()
            .alias("dashes"),
            ((pl.col("move_type") == "air_dash") & (pl.col("prev_move") != "air_dash"))
            .sum()
            .alias("air_dashes"),
            pl.col("step").sum().alias("distance"),
        )
        .sort("start_s")
    )


def build_tables(
    infos: Iterable[MatchInfo],
    exclude: Collection[str] = (),
) -> dict[str, pl.DataFrame]:
    """Build the parquet tables from MatchInfo messages.

    - builds matches, players, stats, soul_sources, item_events, accolades,
      buffs, stacks, custom_stats, damage, damage_sources, damage_targets,
      mid_boss, objectives, and deaths
    - item cost/tier/slot resolve against the committed item history era live at
      match time, so rebuilds price each match on its own patch
    - proc vs stat attribution is derived at read time from damage, see queries.item_attribution
    - exclude skips tables by name (the exclude list in config.toml), which
      keeps the big per-second movement table out of the rebuild
    - movement_intervals holds per minute counts from the same data and
      still builds when movement itself is excluded
    """
    infos = list(infos)
    matches: list[dict] = []
    players: list[dict] = []
    hero_xp_rewards: list[dict] = []
    stats: list[dict] = []
    sources: list[dict] = []
    item_events: list[dict] = []
    accolade_rows: list[dict] = []
    buff_rows: list[dict] = []
    stack_rows: list[dict] = []
    custom_rows: list[dict] = []
    damage: list[dict] = []
    damage_sources: list[dict] = []
    damage_targets: list[dict] = []
    mid_boss: list[dict] = []
    objectives: list[dict] = []
    tracks: list[pl.DataFrame] = []
    track_intervals: list[pl.DataFrame] = []
    deaths: list[dict] = []

    for info in infos:
        start_time = dt.datetime.fromtimestamp(info.start_time, dt.UTC)
        im = items.item_map_asof(start_time)

        matches.append(
            {
                "match_id": info.match_id,
                "start_time": start_time,
                "duration_s": info.duration_s,
                "winning_team": info.winning_team,
                "match_mode": info.match_mode,
                "game_mode": info.game_mode,
                "ranked_type": info.ranked_type if info.HasField("ranked_type") else None,
                "rank_interval": info.rank_interval if info.HasField("rank_interval") else None,
                "average_badge_team0": (
                    info.average_badge_team0 if info.HasField("average_badge_team0") else None
                ),
                "average_badge_team1": (
                    info.average_badge_team1 if info.HasField("average_badge_team1") else None
                ),
                "not_scored": info.not_scored,
            }
        )

        slot_to_account = {p.player_slot: p.account_id for p in info.players}
        hero_by_slot = {p.player_slot: p.hero_id for p in info.players}
        hero_by_account = {p.account_id: p.hero_id for p in info.players}
        path_by_slot = {p.player_slot: p for p in info.match_paths.paths}

        mid_boss.extend(
            {
                "match_id": info.match_id,
                "start_time": start_time,
                "destroyed_time_s": m.destroyed_time_s,
                "team_killed": m.team_killed,
                "team_claimed": m.team_claimed,
            }
            for m in info.mid_boss
        )

        objectives.extend(
            {
                "match_id": info.match_id,
                "start_time": start_time,
                "team": o.team,
                "objective_id": o.team_objective_id,
                "destroyed_time_s": o.destroyed_time_s or None,
                "first_damage_time_s": o.first_damage_time_s or None,
                "player_damage": o.player_damage,
                "player_spirit_damage": o.player_spirit_damage,
                "creep_damage": o.creep_damage,
            }
            for o in info.objectives
        )

        for p in info.players:
            player_outcome = p.player_match_outcome if p.HasField("player_match_outcome") else None
            rank = p.player_rank_data if p.HasField("player_rank_data") else None
            players.append(
                {
                    "match_id": info.match_id,
                    "start_time": start_time,
                    "account_id": p.account_id,
                    "hero_id": p.hero_id,
                    "team": p.team,
                    "player_slot": p.player_slot,
                    "assigned_lane": p.assigned_lane,
                    "won": (
                        player_outcome == extract.pb.k_EPlayerMatchOutcome_Win
                        if player_outcome not in (None, extract.pb.k_EPlayerMatchOutcome_Invalid)
                        else p.team == info.winning_team
                    ),
                    "player_match_outcome": player_outcome,
                    "player_rank_initial_display_rank": (
                        rank.initial_display_rank
                        if rank is not None and rank.HasField("initial_display_rank")
                        else None
                    ),
                    "player_rank_initial_flat_progress": (
                        rank.initial_flat_progress
                        if rank is not None and rank.HasField("initial_flat_progress")
                        else None
                    ),
                    "player_rank_final_flat_progress": (
                        rank.final_flat_progress
                        if rank is not None and rank.HasField("final_flat_progress")
                        else None
                    ),
                    "player_rank_desired_progress_change": (
                        rank.desired_progress_change
                        if rank is not None and rank.HasField("desired_progress_change")
                        else None
                    ),
                    "player_rank_initial_calibration_games": (
                        rank.initial_calibration_games
                        if rank is not None and rank.HasField("initial_calibration_games")
                        else None
                    ),
                    "player_rank_initial_demotion_protection_games": (
                        rank.initial_demotion_protection_games
                        if rank is not None and rank.HasField("initial_demotion_protection_games")
                        else None
                    ),
                    "player_rank_consumed_demotion_protection": (
                        rank.consumed_demotion_protection
                        if rank is not None and rank.HasField("consumed_demotion_protection")
                        else None
                    ),
                    "player_rank_initial_win_streak": (
                        rank.initial_win_streak
                        if rank is not None and rank.HasField("initial_win_streak")
                        else None
                    ),
                    "kills": p.kills,
                    "deaths": p.deaths,
                    "assists": p.assists,
                    "net_worth": p.net_worth,
                    "last_hits": p.last_hits,
                    "denies": p.denies,
                    "mvp_rank": p.mvp_rank,
                    "party": extract.player_party(p),
                    "abandon_time_s": p.abandon_match_time_s or None,
                }
            )

            hero_xp_rewards.extend(
                {
                    "match_id": info.match_id,
                    "start_time": start_time,
                    "account_id": p.account_id,
                    "hero_id": reward.xp_grant.hero_id,
                    "xp_grant": reward.xp_grant.xp_grant,
                    "reason": reward.xp_grant.reason,
                }
                for reward in p.hero_xp_rewards
                if reward.HasField("xp_grant")
            )

            for s in p.stats:
                stats.append(
                    {
                        "match_id": info.match_id,
                        "start_time": start_time,
                        "account_id": p.account_id,
                        "hero_id": p.hero_id,
                        **{schemas.souls(f): getattr(s, f) for f in schemas.STAT_FIELDS},
                    }
                )
                sources.extend(
                    {
                        "match_id": info.match_id,
                        "start_time": start_time,
                        "account_id": p.account_id,
                        "hero_id": p.hero_id,
                        "time_stamp_s": s.time_stamp_s,
                        "source": g.source,
                        "souls": g.gold,
                        "souls_orbs": g.gold_orbs,
                    }
                    for g in s.gold_sources
                )

            track = path_by_slot.get(p.player_slot)
            want_track = "movement" not in exclude
            want_intervals = "movement_intervals" not in exclude

            if track is not None and (want_track or want_intervals):
                frame = _movement_frame(info, start_time, p, track)

                if want_track:
                    tracks.append(frame)

                if want_intervals:
                    track_intervals.append(_movement_intervals_frame(frame))

            deaths.extend(
                {
                    "match_id": info.match_id,
                    "start_time": start_time,
                    "account_id": p.account_id,
                    "hero_id": p.hero_id,
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
                        "start_time": start_time,
                        "account_id": p.account_id,
                        "hero_id": p.hero_id,
                        "game_time_s": it.game_time_s,
                        "item_id": it.item_id,
                        "item": item.name if item else None,
                        "cost": item.cost if item else None,
                        "slot": item.slot if item else None,
                        "tier": item.tier if item else None,
                        "sold_time_s": it.sold_time_s,
                        "flags": it.flags,
                        "imbued_ability_id": it.imbued_ability_id or None,
                    }
                )

            accolade_rows.extend(
                {
                    "match_id": info.match_id,
                    "start_time": start_time,
                    "account_id": p.account_id,
                    "hero_id": p.hero_id,
                    "accolade_id": a.accolade_id,
                    "value": a.accolade_stat_value,
                    "threshold": a.accolade_threshold_achieved,
                }
                for a in p.accolades
            )

            buff_rows.extend(
                {
                    "match_id": info.match_id,
                    "start_time": start_time,
                    "account_id": p.account_id,
                    "hero_id": p.hero_id,
                    "type": b.type,
                    "count": b.value,
                    "permanent": b.is_permanent,
                }
                for b in p.power_up_buffs
            )

            stack_rows.extend(
                {
                    "match_id": info.match_id,
                    "start_time": start_time,
                    "account_id": p.account_id,
                    "hero_id": p.hero_id,
                    "ability_id": st.ability_id,
                    "value": st.ability_value,
                }
                for st in p.ability_stats
            )
        for account_id, named in extract.custom_stats(info).items():
            custom_rows.extend(
                {
                    "match_id": info.match_id,
                    "start_time": start_time,
                    "account_id": account_id,
                    "hero_id": hero_by_account.get(account_id),
                    "time_stamp_s": time_stamp_s,
                    "group": group,
                    "stat": stat,
                    "value": value,
                }
                for time_stamp_s, group, stat, value in named
            )

        details = info.damage_matrix.source_details
        sample_times = list(info.damage_matrix.sample_time_s)
        cumulative: dict[tuple[int, int, bool], dict[int, int]] = {}
        per_target: dict[tuple[int, int, int], dict[int, int]] = {}

        for d in info.damage_matrix.damage_dealers:
            for src in d.damage_sources:
                i = src.source_details_index

                for t in src.damage_to_players:
                    if not t.damage:
                        continue

                    damage.append(
                        {
                            "match_id": info.match_id,
                            "start_time": start_time,
                            "account_id": slot_to_account.get(d.dealer_player_slot),
                            "hero_id": hero_by_slot.get(d.dealer_player_slot),
                            "target_account_id": slot_to_account.get(t.target_player_slot),
                            "target_player_slot": t.target_player_slot,
                            "source_class": details.source_name[i],
                            "stat": STAT_NAMES.get(details.stat_type[i], str(details.stat_type[i])),
                            "damage": t.damage[-1],
                        }
                    )

                    if not sample_times:
                        continue

                    vs_heroes = slot_to_account.get(t.target_player_slot) is not None
                    values = t.damage[-len(sample_times) :]
                    acc = cumulative.setdefault((d.dealer_player_slot, i, vs_heroes), {})
                    tacc = (
                        per_target.setdefault((d.dealer_player_slot, i, t.target_player_slot), {})
                        if vs_heroes
                        else None
                    )

                    for ts, v in zip(sample_times[-len(values) :], values, strict=True):
                        acc[ts] = acc.get(ts, 0) + v

                        if tacc is not None:
                            tacc[ts] = tacc.get(ts, 0) + v

        for (slot, i, vs_heroes), acc in cumulative.items():
            source = details.source_name[i]

            damage_sources.extend(
                {
                    "match_id": info.match_id,
                    "start_time": start_time,
                    "account_id": slot_to_account.get(slot),
                    "hero_id": hero_by_slot.get(slot),
                    "source_class": source,
                    "stat": STAT_NAMES.get(details.stat_type[i], str(details.stat_type[i])),
                    "vs_heroes": vs_heroes,
                    "time_stamp_s": ts,
                    "damage": v,
                }
                for ts, v in sorted(acc.items())
            )

        for (slot, i, target_slot), acc in per_target.items():
            source = details.source_name[i]

            damage_targets.extend(
                {
                    "match_id": info.match_id,
                    "start_time": start_time,
                    "account_id": slot_to_account.get(slot),
                    "hero_id": hero_by_slot.get(slot),
                    "target_account_id": slot_to_account.get(target_slot),
                    "source_class": source,
                    "stat": STAT_NAMES.get(details.stat_type[i], str(details.stat_type[i])),
                    "time_stamp_s": ts,
                    "damage": v,
                }
                for ts, v in sorted(acc.items())
            )

    tables = {
        "matches": schemas.conform("matches", matches),
        "players": schemas.conform("players", players),
        "hero_xp_rewards": schemas.conform("hero_xp_rewards", hero_xp_rewards),
        "stats": schemas.conform("stats", stats),
        "soul_sources": schemas.conform("soul_sources", sources),
        "item_events": schemas.conform("item_events", item_events),
        "accolades": schemas.conform("accolades", accolade_rows),
        "buffs": schemas.conform("buffs", buff_rows),
        "stacks": schemas.conform("stacks", stack_rows),
        "custom_stats": schemas.conform("custom_stats", custom_rows),
        "damage": schemas.conform("damage", damage),
        "damage_sources": schemas.conform("damage_sources", damage_sources),
        "damage_targets": schemas.conform("damage_targets", damage_targets),
        "mid_boss": schemas.conform("mid_boss", mid_boss),
        "objectives": schemas.conform("objectives", objectives),
        "deaths": schemas.conform("deaths", deaths),
    }

    if "movement" not in exclude:
        tables["movement"] = schemas.conform("movement", pl.concat(tracks) if tracks else [])

    if "movement_intervals" not in exclude:
        tables["movement_intervals"] = schemas.conform(
            "movement_intervals", pl.concat(track_intervals) if track_intervals else []
        )

    return {name: df for name, df in tables.items() if name not in exclude}


@dataclass
class ExportResult:
    """Row counts per table plus how many matches were decoded and skipped."""

    counts: dict[str, int] = field(default_factory=dict)
    decoded: int = 0
    skipped: int = 0
    rebuilt: str | None = None


def _match_month(info: MatchInfo) -> str:
    """Partition key for a match: the UTC month it started in as YYYY-MM."""
    started = dt.datetime.fromtimestamp(info.start_time, dt.UTC)

    return started.strftime("%Y-%m")


def _archive_paths(archive_dir: Path) -> list[Path]:
    """Archived .bin files in ascending match_id order (match ids climb with start time).

    - one body per match
    - a body with a real salt wins over a salt 0 placeholder
    """
    return extract.archived_match_paths(archive_dir)


def _archive_paths_with_progress(archive_paths: list[Path]) -> Iterator[Path]:
    """Yield archive paths while reporting durable full-rebuild progress."""
    total = len(archive_paths)

    for completed, path in enumerate(archive_paths, start=1):
        yield path

        if completed % PROGRESS_EVERY == 0 or completed == total:
            percent = completed / total * 100
            print(
                f"  Archive progress: {completed:,}/{total:,} ({percent:.0f}%)",
                file=sys.stderr,
                flush=True,
            )


def _decode_matches(paths: Iterable[Path]) -> Iterator[MatchInfo]:
    """Decode the given archive files in order and skip any that fail to parse."""
    for path in paths:
        try:
            yield extract.load(path)

        except ValueError:
            continue


def _select_infos(
    infos: Iterable[MatchInfo],
    accounts: Collection[int] | None,
    dropped: list[int] | None = None,
) -> Iterator[MatchInfo]:
    """Yield the matches a listed account played in.

    - None yields every match
    - dropped collects the match ids the account filter removed
    """
    account_ids = set(accounts) if accounts else None

    for info in infos:
        if account_ids is None or any(p.account_id in account_ids for p in info.players):
            yield info
        elif dropped is not None:
            dropped.append(info.match_id)


def skipped_match_ids(out_dir: str | Path, accounts: Collection[int] | None) -> set[int]:
    """Return the archived match ids the account filter dropped on earlier exports.

    - recorded per account set, a changed config starts over so new accounts
      pick up matches that were skipped before
    """
    path = Path(out_dir) / "skipped_matches.json"

    if not path.is_file():
        return set()

    data = json.loads(path.read_text(encoding="utf-8"))

    if data.get("accounts") != sorted(accounts or []):
        return set()

    return set(data.get("match_ids", []))


def stored_accounts(out_dir: str | Path) -> list[int] | None:
    """Return the account filter recorded by an existing main export.

    - an empty list is a real value: the store was intentionally unfiltered
    - None means the store predates the marker or the marker cannot be trusted
    """
    path = Path(out_dir) / "skipped_matches.json"

    if not path.is_file():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    if not isinstance(data, dict):
        return None

    accounts = data.get("accounts")

    if not isinstance(accounts, list) or any(type(account) is not int for account in accounts):
        return None

    return accounts


def _write_skipped(
    out_dir: str | Path, accounts: Collection[int] | None, match_ids: set[int]
) -> None:
    """Record the match ids the account filter dropped so they are not decoded again."""
    path = Path(out_dir) / "skipped_matches.json"
    data = {"accounts": sorted(accounts or []), "match_ids": sorted(match_ids)}
    path.write_text(json.dumps(data), encoding="utf-8")


def exported_match_ids(out_dir: Path) -> set[int]:
    """Match ids already written to the matches table. Empty before the table exists."""
    from deadlock_matches import queries

    if not queries.table_exists("matches", out_dir):
        return set()

    exported = queries.scan("matches", out_dir).select("match_id").collect()

    return set(exported.to_series().to_list())


def schema_drift(out_dir: Path, exclude: Collection[str] = ()) -> str | None:
    """Compare parquet columns to schemas.py to identify mismatches.

    - read schemas from parquet footers
    - a missing table directory counts as a mismatch
    - a month file sitting flat in the table directory is the pre-hive layout
      and counts as a mismatch too
    """
    if not (out_dir / "matches").is_dir():
        return None

    for name in sorted(schemas.PARTITIONED):
        if name in exclude:
            continue

        directory = out_dir / name

        if not directory.is_dir():
            return f"the {name} table is missing"

        if next(directory.glob("*.parquet"), None) is not None:
            return f"the {name} table is on the flat month layout"

        expected = set(schemas.TABLES[name])

        for month_file in sorted(directory.glob("month=*/*.parquet")):
            month = month_file.parent.name.removeprefix("month=")

            if set(pl.read_parquet_schema(month_file)) != expected:
                return f"{name} {month} columns differ from schemas.py"

    return None


def drop_only_drift(out_dir: Path, exclude: Collection[str] = ()) -> bool:
    """Whether the drift is only columns schemas.py stopped storing.

    - every table has to be on disk already, a missing one needs a real decode
    - every column the schema still asks for has to be in the footer, a new one needs a decode too
    - the pre-hive flat month layout needs a full rebuild, not a reshape
    """
    for name in sorted(schemas.PARTITIONED):
        if name in exclude:
            continue

        directory = out_dir / name

        if not directory.is_dir():
            return False

        if next(directory.glob("*.parquet"), None) is not None:
            return False

        expected = set(schemas.TABLES[name])

        for month_file in sorted(directory.glob("month=*/*.parquet")):
            if not expected <= set(pl.read_parquet_schema(month_file)):
                return False

    return True


def reshape_partitions(out_dir: Path, exclude: Collection[str] = ()) -> int:
    """Drop the columns the schema no longer stores and return how many files changed.

    - decodes nothing, so it only fits the drift drop_only_drift accepts
    - writes a temp file and renames it, so a crash mid-write leaves the old file intact
    """
    rewritten = 0

    for name in sorted(schemas.PARTITIONED):
        if name in exclude:
            continue

        directory = out_dir / name

        if not directory.is_dir():
            continue

        expected = set(schemas.TABLES[name])

        for month_file in sorted(directory.glob("month=*/*.parquet")):
            if set(pl.read_parquet_schema(month_file)) == expected:
                continue

            tmp = month_file.with_name(f"{month_file.name}.tmp")
            _reshape_to_schema(name, pl.read_parquet(month_file)).write_parquet(tmp)
            tmp.replace(month_file)
            rewritten += 1

    return rewritten


def _new_archive_paths(archive_dir: Path, exported: set[int]) -> list[Path]:
    """Archive files in ascending id order whose match_id is not already in the tables."""
    fresh = []

    for path in _archive_paths(archive_dir):
        match_id = int(path.name.split("_")[0])

        if match_id not in exported:
            fresh.append(path)

    return fresh


def write_partitioned(name: str, df: pl.DataFrame, month: str, out_dir: Path) -> int:
    """Merge one month of rows into out_dir/<name>/month=<month>/data.parquet and return the rows merged in.

    - scans the existing month file, drops the match_ids in the batch, streams the concat to disk
    - a schema drift in the batch or the existing file raises before anything is touched
    - writes a temp file and renames it, so a crash mid-write leaves the old file intact
    - match_id is the identity, so re-running the same batch leaves the content unchanged
    """
    directory = out_dir / name / f"month={month}"
    directory.mkdir(parents=True, exist_ok=True)

    target = directory / "data.parquet"
    expected = set(schemas.TABLES[name])
    drifted = f"{name} {month} columns drifted from schemas.py, run a full rebuild"

    if set(df.columns) != expected:
        raise ValueError(drifted)

    tmp = directory / "data.parquet.tmp"

    if target.exists():
        existing = pl.scan_parquet(target)

        if set(existing.collect_schema().names()) != expected:
            raise ValueError(drifted)

        batch_ids = df.get_column("match_id").unique().to_list()
        preserved = existing.filter(~pl.col("match_id").is_in(batch_ids))
        pl.concat([preserved, df.lazy()], how="vertical").sink_parquet(tmp)

    else:
        df.write_parquet(tmp)

    Path(tmp).replace(target)

    return len(df)


def _flush_month(
    batch: list[MatchInfo],
    month: str,
    out_dir: Path,
    exclude: Collection[str],
    counts: dict[str, int],
) -> None:
    """Build one month of matches and merge each table into its month partition."""
    for name, df in build_tables(batch, exclude).items():
        written = write_partitioned(name, df, month, out_dir)
        counts[name] = counts.get(name, 0) + written


FLUSH_MATCHES = 50


def export_infos(
    infos: Iterable[MatchInfo],
    out_dir: Path,
    exclude: Collection[str],
) -> dict[str, int]:
    """Build and write tables in bounded batches so memory never scales with the archive.

    - infos must arrive so a month is contiguous and ascending match_id order does that
    - a batch flushes when the month changes or it reaches FLUSH_MATCHES matches,
      whichever comes first; merging by match_id makes the split flushes land in
      the same month file
    """
    counts: dict[str, int] = {}
    current_month: str | None = None
    batch: list[MatchInfo] = []

    for info in infos:
        month = _match_month(info)

        if current_month is not None and (month != current_month or len(batch) >= FLUSH_MATCHES):
            _flush_month(batch, current_month, out_dir, exclude, counts)
            batch = []

        current_month = month
        batch.append(info)

    if batch and current_month is not None:
        _flush_month(batch, current_month, out_dir, exclude, counts)

    return counts


def clear_partition(name: str, out_dir: Path) -> None:
    """Remove the month directory of a table and any legacy single file before a full rebuild."""
    directory = out_dir / name

    if directory.is_dir():
        shutil.rmtree(directory)

    (out_dir / f"{name}.parquet").unlink(missing_ok=True)


def _carry_forward(name: str, out_dir: Path, staging: Path, decoded: Collection[int]) -> None:
    """Copy the old partitions of one table into staging, reshaped and minus the freshly decoded ids.

    - a match whose body could not be decoded keeps its old row so nothing is dropped
    - genuinely new columns fill with null for those carried rows
    """
    old = out_dir / name

    if not old.is_dir():
        return

    keep = list(decoded)

    for month_file in sorted(old.glob("month=*/*.parquet")):
        month = month_file.parent.name.removeprefix("month=")
        rows = pl.read_parquet(month_file).filter(~pl.col("match_id").is_in(keep))

        if not rows.is_empty():
            write_partitioned(name, _reshape_to_schema(name, rows), month, staging)


def _swap_into_place(staged: Path, target: Path) -> None:
    """Replace target with staged through a backup so the live table is only ever a rename away.

    - the old table moves to a sibling backup, staged moves into place, then the backup is dropped
    - a failed move restores the backup so the table is never left missing
    """
    backup = target.parent / f"{target.name}.backup"

    if backup.exists():
        shutil.rmtree(backup)

    if target.is_dir():
        target.replace(backup)

    try:
        staged.replace(target)

    except OSError:
        if backup.is_dir():
            backup.replace(target)

        raise

    if backup.is_dir():
        shutil.rmtree(backup)


def _restore_backups(out_dir: Path) -> None:
    """Recover any table left as a .backup by a crash midway through a previous swap."""
    for name in sorted(schemas.PARTITIONED):
        backup = out_dir / f"{name}.backup"

        if not backup.is_dir():
            continue

        target = out_dir / name

        if target.is_dir():
            shutil.rmtree(backup)

        else:
            backup.replace(target)


def _fill_missing_tables(out_dir: Path, exclude: Collection[str]) -> None:
    """Write an empty partition for any table still missing, so a missing directory stops reading as drift."""
    matches_dir = out_dir / "matches"

    if not matches_dir.is_dir():
        return

    months = sorted(
        d.name.removeprefix("month=") for d in matches_dir.glob("month=*") if d.is_dir()
    )

    if not months:
        return

    for name in sorted(schemas.PARTITIONED):
        if name in exclude or (out_dir / name).is_dir():
            continue

        write_partitioned(name, schemas.conform(name, []), months[0], out_dir)


def rebuild_drifted_partitions(
    infos: Iterable[MatchInfo], out_dir: Path, exclude: Collection[str]
) -> None:
    """Rebuild the drifted partitions without ever leaving live tables destroyed.

    - decodes the wanted bodies into a staging directory first
    - carries any match that could not be decoded forward from the old partitions
    - swaps each table into place through a backup once staging holds the replacement
    - a table newly required by the schema but absent everywhere becomes an empty partition
    """
    _restore_backups(out_dir)

    staging = out_dir.parent / f"{out_dir.name}.rebuild"

    if staging.exists():
        shutil.rmtree(staging)

    staging.mkdir(parents=True)

    try:
        export_infos(infos, staging, exclude)
        decoded = exported_match_ids(staging)

        for name in sorted(schemas.PARTITIONED):
            if name in exclude:
                continue

            _carry_forward(name, out_dir, staging, decoded)

            staged = staging / name

            if staged.is_dir():
                _swap_into_place(staged, out_dir / name)

        _fill_missing_tables(out_dir, exclude)

    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _reshape_to_schema(name: str, df: pl.DataFrame) -> pl.DataFrame:
    """Fit old rows to the current schema and drop columns we no longer support."""
    exprs = []

    for col, coldef in schemas.TABLES[name].items():
        if col in df.columns:
            exprs.append(pl.col(col).cast(coldef.dtype))

        else:
            exprs.append(pl.lit(None).cast(coldef.dtype).alias(col))

    return df.select(exprs)


def migrate_to_partitions(out_dir: Path, exclude: Collection[str] = ()) -> None:
    """Split a legacy single-file store into month partitions without decoding anything again.

    - reads the rows already on disk and writes them into the month partitions so nothing is lost
    - old columns we no longer support are dropped to match the current schema
    - the month for each row comes from the match start time in the matches table
    - the legacy single file is removed once its rows are written to the month partitions
    """
    matches_file = out_dir / "matches.parquet"

    if not matches_file.exists():
        return

    months = pl.read_parquet(matches_file).select(
        "match_id", pl.col("start_time").dt.strftime("%Y-%m").alias("_month")
    )

    for name in schemas.PARTITIONED:
        if name in exclude:
            continue

        legacy = out_dir / f"{name}.parquet"

        if not legacy.exists():
            continue

        tagged = pl.read_parquet(legacy).join(months, on="match_id", how="inner")

        for month in sorted(tagged.get_column("_month").unique().to_list()):
            part = _reshape_to_schema(name, tagged.filter(pl.col("_month") == month))
            write_partitioned(name, part, month, out_dir)

        legacy.unlink()


def refresh_asset_tables(out_dir: str | Path) -> None:
    """Rewrite the exported asset tables from the committed history."""
    _write_asset_tables(Path(out_dir), {})


def _write_asset_tables(out_dir: Path, counts: dict[str, int]) -> None:
    """Flatten the committed asset history into out_dir/assets and record row counts per table."""
    asset_dir = out_dir / "assets"
    asset_dir.mkdir(parents=True, exist_ok=True)

    for name, df in unnest.all_asset_tables().items():
        df.write_parquet(asset_dir / f"{name}.parquet")
        counts[name] = len(df)


def export_all(
    archive_dir: str | Path | None = None,
    out_dir: str | Path | None = None,
    exclude: Collection[str] = (),
    accounts: Collection[int] | None = None,
) -> ExportResult:
    """Rebuild every parquet table from scratch by streaming one month at a time.

    - both directories default to the standard locations (the match archive and PARQUET_DIR)
    - accounts keeps only matches a listed account played in
    - without it every archived match is exported
    - each built table is cleared first so a match dropped from the archive also leaves the tables
    - excluded tables are left untouched rather than deleted, so opting movement out keeps its history
    - the versioned asset tables flatten out of the committed history into out_dir/assets
    - reports archive progress every 50 files and says when asset tables are being written
    """
    archive_dir = extract.ARCHIVE_DIR if archive_dir is None else Path(archive_dir)
    out_dir = PARQUET_DIR if out_dir is None else Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    archive_paths = _archive_paths(archive_dir)
    total = len(archive_paths)
    print(f"Building the tables from the archive ({total:,} archived matches)", flush=True)

    for name in schemas.PARTITIONED:
        if name not in exclude:
            clear_partition(name, out_dir)

    dropped: list[int] = []
    progress_paths = _archive_paths_with_progress(archive_paths)
    infos = _select_infos(_decode_matches(progress_paths), accounts, dropped)
    counts = export_infos(infos, out_dir, exclude)

    print("Writing the asset reference tables", file=sys.stderr, flush=True)
    _write_skipped(out_dir, accounts, set(dropped))
    _write_asset_tables(out_dir, counts)
    update_stamp(out_dir, logic_version=EXPORT_LOGIC_VERSION, asset_horizon=item_horizon())

    return ExportResult(counts=counts, decoded=counts.get("matches", 0), skipped=0)


def reexport_matches(
    match_ids: Collection[int],
    archive_dir: str | Path | None = None,
    out_dir: str | Path | None = None,
    exclude: Collection[str] = (),
    accounts: Collection[int] | None = None,
) -> int:
    """Re-decode specific archived matches and rewrite their table rows in place.

    - write_partitioned replaces rows by match_id and leaves every other match alone
    - matches no longer in the archive are skipped
    """
    archive_dir = extract.ARCHIVE_DIR if archive_dir is None else Path(archive_dir)
    out_dir = PARQUET_DIR if out_dir is None else Path(out_dir)
    wanted = set(match_ids)
    paths_wanted = [p for p in _archive_paths(archive_dir) if int(p.name.split("_")[0]) in wanted]

    if not paths_wanted:
        return 0

    dropped: list[int] = []
    infos = _select_infos(_decode_matches(paths_wanted), accounts, dropped)
    counts = export_infos(infos, out_dir, exclude)

    return counts.get("matches", 0)


def is_legacy_layout(out_dir: Path) -> bool:
    """A pre-partition store where matches is still a single file instead of a month directory."""
    return (out_dir / "matches.parquet").exists() and not (out_dir / "matches").is_dir()


def export_new(
    archive_dir: str | Path | None = None,
    out_dir: str | Path | None = None,
    exclude: Collection[str] = (),
    accounts: Collection[int] | None = None,
) -> ExportResult:
    """Export only the matches not already in the tables and append them to their month partitions.

    - reads the exported match_ids from the matches table and an empty table means a full build
    - accounts keeps only matches a listed account played in
    - without it every archived match is exported
    - a legacy single-file store is re-laid-out into partitions first, without decoding anything
    - decodes only the .bin files whose match_id is new so processed matches are never re-read
    - old month partitions are left alone and only the months the new matches fall in are rewritten
    - a drift that only drops columns is reshaped in place, decoding nothing
    - any other drift rebuilds every table and puts the reason on the result
    """
    archive_dir = extract.ARCHIVE_DIR if archive_dir is None else Path(archive_dir)
    out_dir = PARQUET_DIR if out_dir is None else Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if is_legacy_layout(out_dir):
        migrate_to_partitions(out_dir, exclude)

    exported = exported_match_ids(out_dir)

    if not exported:
        return export_all(archive_dir, out_dir, exclude, accounts)

    drift = schema_drift(out_dir, exclude)

    if drift and drop_only_drift(out_dir, exclude):
        print("Dropping the columns the tables no longer store")
        reshape_partitions(out_dir, exclude)
        drift = schema_drift(out_dir, exclude)

    if drift:
        result = export_all(archive_dir, out_dir, exclude, accounts)
        result.rebuilt = drift

        return result

    stamp = read_stamp(out_dir)
    logic = stamp.get("logic_version")

    if logic is not None and logic != EXPORT_LOGIC_VERSION:
        result = export_all(archive_dir, out_dir, exclude, accounts)
        result.rebuilt = "the export logic changed"

        return result

    fresh_stamp = {"logic_version": EXPORT_LOGIC_VERSION}

    if "asset_horizon" not in stamp and (horizon := item_horizon()):
        fresh_stamp["asset_horizon"] = horizon

    if logic is None or "asset_horizon" not in stamp:
        update_stamp(out_dir, **fresh_stamp)

    skipped = skipped_match_ids(out_dir, accounts)
    paths = _new_archive_paths(archive_dir, exported | skipped)

    if not paths:
        return ExportResult(counts={}, decoded=0, skipped=len(exported))

    dropped: list[int] = []
    infos = _select_infos(_decode_matches(paths), accounts, dropped)
    counts = export_infos(infos, out_dir, exclude)

    if dropped:
        _write_skipped(out_dir, accounts, skipped | set(dropped))

    if not (out_dir / "assets").is_dir():
        _write_asset_tables(out_dir, counts)

    return ExportResult(counts=counts, decoded=counts.get("matches", 0), skipped=len(exported))
