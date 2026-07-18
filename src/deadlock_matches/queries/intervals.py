"""Interval gains and cumulative marks over the compare stats."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from deadlock_matches.queries.core import scan
from deadlock_matches.queries.delivery import damage_category, hero_damage, with_delivery

if TYPE_CHECKING:
    from collections.abc import Sequence


SOUL_COMPOSITES = {
    "farm": ("troopers", "jungle", "breakables", "treasure", "denies"),
    "troopers": ("troopers",),
    "jungle": ("jungle",),
    "breakables": ("breakables",),
    "rift_urn": ("treasure",),
    "deny_souls": ("denies",),
    "combat": ("players", "assists"),
    "objectives": ("bosses",),
    "catch_up": ("team_bonus",),
    "other": ("trophy_collector", "cultist_sacrifice", "assassinate", "goose_egg"),
}


COMPARE_STATS = (
    "souls",
    "farm",
    "troopers",
    "jungle",
    "breakables",
    "combat",
    "objectives",
    "catch_up",
    "other",
    "kills",
    "deaths",
    "assists",
    "damage",
    "damage_taken",
    "obj_damage",
    "healing",
    "heal_prevented",
    "creeps",
    "neutrals",
    "denies",
)


_KEYS = ["match_id", "account_id"]


def _bucket(column: str, interval_s: int) -> pl.Expr:
    """Assign a time column to its interval number, matching match_intervals."""
    return ((pl.col(column) - 1) // interval_s).clip(0).cast(pl.Int64).alias("interval")


def _interval_grid(
    games: pl.LazyFrame, interval_s: int, parquet_dir: str | Path | None
) -> pl.LazyFrame:
    """Lay out one row per full interval per game."""
    return (
        games.select(_KEYS)
        .unique()
        .join(scan("matches", parquet_dir).select("match_id", "duration_s"), on="match_id")
        .select(
            *_KEYS,
            pl.int_ranges(0, pl.col("duration_s") // interval_s).alias("interval"),
        )
        .explode("interval", empty_as_null=False)
    )


def _column_gains(
    games: pl.LazyFrame, column: str, interval_s: int, parquet_dir: str | Path | None
) -> pl.LazyFrame:
    """Diff one cumulative stats column into per interval gains per game."""
    cumulative = (
        scan("stats", parquet_dir)
        .join(games.select(_KEYS).unique(), on=_KEYS)
        .select(*_KEYS, _bucket("time_stamp_s", interval_s), pl.col(column).alias("value"))
        .group_by(*_KEYS, "interval")
        .agg(pl.col("value").max())
    )

    return (
        _interval_grid(games, interval_s, parquet_dir)
        .join(cumulative, on=[*_KEYS, "interval"], how="left")
        .sort(*_KEYS, "interval")
        .with_columns(pl.col("value").forward_fill().over(_KEYS).fill_null(0))
        .with_columns(
            (pl.col("value") - pl.col("value").shift(1).over(_KEYS).fill_null(0)).alias("gain")
        )
        .select(*_KEYS, "interval", "gain")
    )


def _source_gains(
    games: pl.LazyFrame,
    sources: Sequence[str],
    interval_s: int,
    parquet_dir: str | Path | None,
) -> pl.LazyFrame:
    """Diff a set of soul sources into per interval gains per game.

    Each source samples on its own clock, so every source forward-fills
    separately before the gains are summed.
    """
    per_source = (
        scan("soul_sources", parquet_dir)
        .join(games.select(_KEYS).unique(), on=_KEYS)
        .filter(pl.col("source_name").is_in(list(sources)))
        .select(
            *_KEYS,
            "source_name",
            _bucket("time_stamp_s", interval_s),
            (pl.col("souls") + pl.col("souls_orbs")).alias("value"),
        )
        .group_by(*_KEYS, "source_name", "interval")
        .agg(pl.col("value").max())
    )

    return (
        _interval_grid(games, interval_s, parquet_dir)
        .join(pl.LazyFrame({"source_name": list(sources)}), how="cross")
        .join(per_source, on=[*_KEYS, "source_name", "interval"], how="left")
        .sort(*_KEYS, "source_name", "interval")
        .with_columns(pl.col("value").forward_fill().over([*_KEYS, "source_name"]).fill_null(0))
        .with_columns(
            (
                pl.col("value")
                - pl.col("value").shift(1).over([*_KEYS, "source_name"]).fill_null(0)
            ).alias("gain")
        )
        .group_by(*_KEYS, "interval")
        .agg(pl.col("gain").sum())
    )


def _event_gains(
    games: pl.LazyFrame, interval_s: int, parquet_dir: str | Path | None, *, kills: bool
) -> pl.LazyFrame:
    """Count deaths table rows per interval per game, as victim or as killer."""
    deaths = scan("deaths", parquet_dir)

    if kills:
        deaths = (
            deaths.drop("account_id")
            .drop_nulls("killer_account_id")
            .rename({"killer_account_id": "account_id"})
        )

    events = (
        deaths.join(games.select(_KEYS).unique(), on=_KEYS)
        .select(*_KEYS, _bucket("game_time_s", interval_s))
        .group_by(*_KEYS, "interval")
        .agg(pl.len().cast(pl.Int64).alias("gain"))
    )

    return (
        _interval_grid(games, interval_s, parquet_dir)
        .join(events, on=[*_KEYS, "interval"], how="left")
        .with_columns(pl.col("gain").fill_null(0))
        .select(*_KEYS, "interval", "gain")
    )


def compare_intervals(
    games: pl.LazyFrame,
    stat: str,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
) -> pl.LazyFrame:
    """Split every given game into per interval gains of one compare stat.

    - full intervals only, so a game contributes exactly while it lasts
    - same bucket rule as match_intervals: a gain lands in the interval
      holding the sample that recorded it
    - kills and deaths count deaths table rows, snapshot counts drift
    - soul composites (farm, combat, ...) sum their sources, each source
      forward-filled on its own clock
    """
    if stat in ("kills", "deaths"):
        return _event_gains(games, interval_s, parquet_dir, kills=stat == "kills")

    if stat in INTERVAL_STATS:
        return _column_gains(games, INTERVAL_STATS[stat], interval_s, parquet_dir)

    if stat in SOUL_COMPOSITES:
        return _source_gains(games, SOUL_COMPOSITES[stat], interval_s, parquet_dir)

    known = ", ".join(COMPARE_STATS)
    msg = f"Unknown compare stat {stat!r}, one of: {known}"
    raise ValueError(msg)


def game_totals(
    games: pl.LazyFrame, stat: str, parquet_dir: str | Path | None = None
) -> pl.LazyFrame:
    """Total one compare stat over each whole game, one row per game."""
    with_duration = (
        games.select(_KEYS)
        .unique()
        .join(scan("matches", parquet_dir).select("match_id", "duration_s"), on="match_id")
    )

    if stat in ("kills", "deaths"):
        deaths = scan("deaths", parquet_dir)

        if stat == "kills":
            deaths = (
                deaths.drop("account_id")
                .drop_nulls("killer_account_id")
                .rename({"killer_account_id": "account_id"})
            )

        totals = (
            deaths.join(games.select(_KEYS).unique(), on=_KEYS)
            .group_by(_KEYS)
            .agg(pl.len().cast(pl.Int64).alias("total"))
        )

    elif stat in INTERVAL_STATS:
        totals = (
            scan("stats", parquet_dir)
            .join(games.select(_KEYS).unique(), on=_KEYS)
            .group_by(_KEYS)
            .agg(pl.col(INTERVAL_STATS[stat]).max().alias("total"))
        )

    elif stat in SOUL_COMPOSITES:
        totals = (
            scan("soul_sources", parquet_dir)
            .join(games.select(_KEYS).unique(), on=_KEYS)
            .filter(pl.col("source_name").is_in(list(SOUL_COMPOSITES[stat])))
            .group_by(*_KEYS, "source_name")
            .agg((pl.col("souls") + pl.col("souls_orbs")).max().alias("total"))
            .group_by(_KEYS)
            .agg(pl.col("total").sum())
        )

    else:
        known = ", ".join(COMPARE_STATS)
        msg = f"Unknown compare stat {stat!r}, one of: {known}"
        raise ValueError(msg)

    return (
        with_duration.join(totals, on=_KEYS, how="left")
        .with_columns(pl.col("total").fill_null(0))
        .filter(pl.col("duration_s") > 0)
        .select(*_KEYS, "total", "duration_s")
    )


def game_rates(
    games: pl.LazyFrame, stat: str, parquet_dir: str | Path | None = None
) -> pl.LazyFrame:
    """Compute the whole game rate per minute of one compare stat, one row per game."""
    return game_totals(games, stat, parquet_dir).select(
        *_KEYS, (pl.col("total") * 60 / pl.col("duration_s")).alias("rate")
    )


def cumulative_at(
    games: pl.LazyFrame,
    stat: str,
    marks_s: Sequence[int],
    parquet_dir: str | Path | None = None,
) -> pl.LazyFrame:
    """Read the cumulative value of one compare stat at each mark, per game.

    - the value is the last recorded sample at or before the mark
    - only games that reach a mark contribute rows for it
    """
    marks = pl.LazyFrame({"mark_s": sorted(set(marks_s))}, schema={"mark_s": pl.Int64})
    reached = (
        games.select(_KEYS)
        .unique()
        .join(scan("matches", parquet_dir).select("match_id", "duration_s"), on="match_id")
        .join(marks, how="cross")
        .filter(pl.col("duration_s") >= pl.col("mark_s"))
        .select(*_KEYS, "mark_s")
    )

    if stat in INTERVAL_STATS:
        values = (
            scan("stats", parquet_dir)
            .join(games.select(_KEYS).unique(), on=_KEYS)
            .select(*_KEYS, "time_stamp_s", pl.col(INTERVAL_STATS[stat]).alias("value"))
            .join(marks, how="cross")
            .filter(pl.col("time_stamp_s") <= pl.col("mark_s"))
            .group_by(*_KEYS, "mark_s")
            .agg(pl.col("value").max())
        )

    elif stat in SOUL_COMPOSITES:
        values = (
            scan("soul_sources", parquet_dir)
            .join(games.select(_KEYS).unique(), on=_KEYS)
            .filter(pl.col("source_name").is_in(list(SOUL_COMPOSITES[stat])))
            .select(
                *_KEYS,
                "source_name",
                "time_stamp_s",
                (pl.col("souls") + pl.col("souls_orbs")).alias("value"),
            )
            .join(marks, how="cross")
            .filter(pl.col("time_stamp_s") <= pl.col("mark_s"))
            .group_by(*_KEYS, "source_name", "mark_s")
            .agg(pl.col("value").max())
            .group_by(*_KEYS, "mark_s")
            .agg(pl.col("value").sum())
        )

    else:
        known = ", ".join(k for k in COMPARE_STATS if k not in ("kills", "deaths"))
        msg = f"Unknown cumulative stat {stat!r}, one of: {known}"
        raise ValueError(msg)

    return (
        reached.join(values, on=[*_KEYS, "mark_s"], how="left")
        .with_columns(pl.col("value").fill_null(0))
        .select(*_KEYS, "mark_s", "value")
    )


def cumulative_stat_target_times(
    games: pl.LazyFrame,
    targets: Sequence[int],
    stat: str = "souls",
    parquet_dir: str | Path | None = None,
) -> pl.LazyFrame:
    """Return when each game first crosses each target.

    - times are linearly interpolated between cumulative stat snapshots
    - targets that a game never reaches are left out
    """
    if stat not in INTERVAL_STATS:
        known = ", ".join(INTERVAL_STATS)
        msg = f"Unknown cumulative target stat {stat!r}, one of: {known}"
        raise ValueError(msg)

    target_frame = pl.LazyFrame(
        {"target": sorted(set(targets))},
        schema={"target": pl.Int64},
    )
    value = pl.col(INTERVAL_STATS[stat]).alias("value")

    samples = (
        scan("stats", parquet_dir)
        .join(games.select(_KEYS).unique(), on=_KEYS)
        .select(*_KEYS, "time_stamp_s", value)
        .sort(*_KEYS, "time_stamp_s")
        .with_columns(
            pl.col("time_stamp_s").shift().over(_KEYS).fill_null(0).alias("prev_t"),
            pl.col("value").shift().over(_KEYS).fill_null(0).alias("prev_v"),
        )
    )

    span = pl.col("value") - pl.col("prev_v")
    frac = pl.when(span > 0).then((pl.col("target") - pl.col("prev_v")) / span).otherwise(0)
    target_time_s = pl.col("prev_t") + frac * (pl.col("time_stamp_s") - pl.col("prev_t"))

    return (
        samples.join(target_frame, how="cross")
        .filter(pl.col("value") >= pl.col("target"), pl.col("prev_v") < pl.col("target"))
        .with_columns(target_time_s.alias("target_time_s"))
        .group_by(*_KEYS, "target")
        .agg(pl.col("target_time_s").min())
        .select(*_KEYS, "target", "target_time_s")
    )


INTERVAL_STATS = {
    "souls": "net_worth",
    "assists": "assists",
    "damage": "player_damage",
    "damage_taken": "player_damage_taken",
    "obj_damage": "boss_damage",
    "healing": "player_healing",
    "heal_prevented": "heal_prevented",
    "creeps": "creep_kills",
    "neutrals": "neutral_kills",
    "denies": "denies",
}


INTERVAL_COLUMNS = (
    "souls",
    "kills",
    "deaths",
    "assists",
    "damage",
    "damage_taken",
    "obj_damage",
    "healing",
    "heal_prevented",
    "creeps",
    "neutrals",
    "denies",
)


def match_intervals(
    match_id: int,
    account_id: int,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Split the match for one player into intervals of stat gains.

    - snapshots are cumulative, so the gain in an interval is its last snapshot
      minus the last snapshot of the interval before it
    - intervals without a snapshot inherit the previous values and show zero gains
    - coverage ends at the last snapshot, and the last interval ends at the
      match end, so it can be shorter than the rest
    - kills and deaths are counted from the deaths table, since the snapshot
      fields drift from the match screen
    - souls_min is the souls gained per minute inside the interval
    """
    duration = (
        scan("matches", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("duration_s")
        .collect()
    )

    if duration.is_empty():
        msg = f"match {match_id} not in the tables"
        raise ValueError(msg)

    fields = list(INTERVAL_STATS.values())
    snaps = (
        scan("stats", parquet_dir)
        .filter(pl.col("match_id") == match_id, pl.col("account_id") == account_id)
        .select("time_stamp_s", *fields)
        .collect()
    )

    if snaps.is_empty():
        msg = f"account {account_id} has no snapshots in match {match_id}"
        raise ValueError(msg)

    duration_s = int(duration.item())
    bucket = ((pl.col("time_stamp_s") - 1) // interval_s).clip(0).cast(pl.Int64).alias("interval")
    cumulative = snaps.with_columns(bucket).group_by("interval").agg(pl.col(fields).max())

    mine = pl.col("account_id") == account_id
    killed = (pl.col("killer_account_id") == account_id).fill_null(value=False)
    events = (
        scan("deaths", parquet_dir)
        .filter(pl.col("match_id") == match_id, mine | killed)
        .select(
            ((pl.col("game_time_s") - 1) // interval_s).clip(0).cast(pl.Int64).alias("interval"),
            killed.alias("kill"),
            mine.alias("death"),
        )
        .group_by("interval")
        .agg(
            pl.col("kill").sum().cast(pl.Int64).alias("kills"),
            pl.col("death").sum().cast(pl.Int64).alias("deaths"),
        )
        .collect()
    )

    n = cumulative.select(pl.col("interval").max()).item() + 1
    gains = (
        pl.DataFrame({"interval": range(n)}, schema={"interval": pl.Int64})
        .join(cumulative, on="interval", how="left")
        .sort("interval")
        .with_columns(pl.col(fields).fill_null(strategy="forward").fill_null(0))
        .with_columns(pl.col(f) - pl.col(f).shift(1).fill_null(0) for f in fields)
        .join(events, on="interval", how="left")
        .with_columns(pl.col("kills", "deaths").fill_null(0))
        .sort("interval")
    )

    return (
        gains.rename({raw: name for name, raw in INTERVAL_STATS.items() if raw != name})
        .with_columns(
            (pl.col("interval") * interval_s).alias("start_s"),
            ((pl.col("interval") + 1) * interval_s).clip(upper_bound=duration_s).alias("end_s"),
        )
        .with_columns(
            (pl.col("souls") * 60 / (pl.col("end_s") - pl.col("start_s"))).alias("souls_min")
        )
        .select("start_s", "end_s", *INTERVAL_COLUMNS, "souls_min")
    )


def damage_intervals(
    match_id: int,
    account_id: int,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
    stat: str = "damage",
) -> pl.DataFrame:
    """Split the damage to heroes for one player into per source gains per interval.

    - detail rows only, the match screen totals are excluded
    - samples in damage_sources are sparse (about every three minutes), so a
      gain lands in the interval holding the sample that recorded it
    - one row per source per interval, sources ordered by match total, a
      source with nothing but zero samples never appears
    - delivery comes along for gun/ability/item grouping
    """
    duration = (
        scan("matches", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("duration_s")
        .collect()
    )

    if duration.is_empty():
        msg = f"match {match_id} not in the tables"
        raise ValueError(msg)

    rows = scan("damage_sources", parquet_dir).filter(
        pl.col("match_id") == match_id,
        pl.col("dealer_account_id") == account_id,
        pl.col("stat") == stat,
        pl.col("vs_heroes"),
        damage_category() != "total",
        pl.col("damage") != 0,
    )
    samples = (
        with_delivery(rows, parquet_dir)
        .select("source_name", "delivery", "time_stamp_s", "damage")
        .collect()
    )

    if samples.is_empty():
        msg = f"account {account_id} has no {stat} to heroes in match {match_id}"
        raise ValueError(msg)

    duration_s = int(duration.item())
    bucket = ((pl.col("time_stamp_s") - 1) // interval_s).clip(0).cast(pl.Int64).alias("interval")
    cumulative = (
        samples.with_columns(bucket).group_by("source_name", "interval").agg(pl.col("damage").max())
    )

    n = cumulative.select(pl.col("interval").max()).item() + 1
    grid = (
        samples.select("source_name", "delivery")
        .unique()
        .join(pl.DataFrame({"interval": range(n)}, schema={"interval": pl.Int64}), how="cross")
    )

    gains = (
        grid.join(cumulative, on=["source_name", "interval"], how="left")
        .sort("source_name", "interval")
        .with_columns(
            pl.col("damage").fill_null(strategy="forward").fill_null(0).over("source_name")
        )
        .with_columns(pl.col("damage") - pl.col("damage").shift(1).fill_null(0).over("source_name"))
        .with_columns(pl.col("damage").sum().over("source_name").alias("total"))
    )

    return (
        gains.with_columns(
            (pl.col("interval") * interval_s).alias("start_s"),
            ((pl.col("interval") + 1) * interval_s).clip(upper_bound=duration_s).alias("end_s"),
        )
        .sort(["total", "source_name", "interval"], descending=[True, False, False])
        .select("source_name", "delivery", "start_s", "end_s", "damage", "total")
    )


def enemy_damage_intervals(
    match_id: int,
    account_id: int,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
    *,
    dealt: bool = False,
) -> pl.DataFrame:
    """Split the damage exchanged with each enemy hero into gains per interval.

    - the damage every enemy dealt to this player, or with dealt=True the
      damage this player dealt to each enemy
    - detail rows between hero dealers and hero targets only
    - samples in damage_targets are sparse (about every three minutes), so each
      source forward fills on its own clock before the per enemy sum
    - one row per enemy per interval, enemies ordered by match total
    """
    duration = (
        scan("matches", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("duration_s")
        .collect()
    )

    if duration.is_empty():
        msg = f"match {match_id} not in the tables"
        raise ValueError(msg)

    mine = "dealer_account_id" if dealt else "target_account_id"
    other = "target_account_id" if dealt else "dealer_account_id"
    samples = (
        scan("damage_targets", parquet_dir)
        .filter(
            pl.col("match_id") == match_id,
            pl.col(mine) == account_id,
            pl.col(other).is_not_null(),
            pl.col("stat") == "damage",
            damage_category() != "total",
        )
        .select(pl.col(other).alias("enemy_account_id"), "source_class", "time_stamp_s", "damage")
        .collect()
    )

    if samples.is_empty():
        direction = "dealt to" if dealt else "taken from"
        msg = f"account {account_id} has no damage {direction} heroes in match {match_id}"
        raise ValueError(msg)

    duration_s = int(duration.item())
    bucket = ((pl.col("time_stamp_s") - 1) // interval_s).clip(0).cast(pl.Int64).alias("interval")
    keys = ["enemy_account_id", "source_class"]
    cumulative = (
        samples.with_columns(bucket).group_by(*keys, "interval").agg(pl.col("damage").max())
    )

    n = cumulative.select(pl.col("interval").max()).item() + 1
    grid = (
        samples.select(keys)
        .unique()
        .join(pl.DataFrame({"interval": range(n)}, schema={"interval": pl.Int64}), how="cross")
    )

    gains = (
        grid.join(cumulative, on=[*keys, "interval"], how="left")
        .sort(*keys, "interval")
        .with_columns(pl.col("damage").fill_null(strategy="forward").fill_null(0).over(keys))
        .with_columns(pl.col("damage") - pl.col("damage").shift(1).fill_null(0).over(keys))
        .group_by("enemy_account_id", "interval")
        .agg(pl.col("damage").sum())
        .with_columns(pl.col("damage").sum().over("enemy_account_id").alias("total"))
    )

    in_match = (
        scan("players", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select(pl.col("account_id").alias("enemy_account_id"), pl.col("hero").alias("enemy"))
        .collect()
    )

    return (
        gains.join(in_match, on="enemy_account_id", how="left")
        .with_columns(
            (pl.col("interval") * interval_s).alias("start_s"),
            ((pl.col("interval") + 1) * interval_s).clip(upper_bound=duration_s).alias("end_s"),
        )
        .sort(["total", "enemy", "interval"], descending=[True, False, False])
        .select("enemy", "enemy_account_id", "start_s", "end_s", "damage", "total")
    )


def enemy_damage_totals(
    games: pl.DataFrame | pl.LazyFrame,
    parquet_dir: str | Path | None = None,
    *,
    dealt: bool = False,
) -> pl.LazyFrame:
    """Total the damage exchanged with each enemy hero for multiple players, one row per enemy.

    - the whole-game twin of enemy_damage_intervals: reads the final-total
      `damage` table, never the cumulative `damage_targets` snapshots, so a
      plain sum is safe
    - the damage every enemy dealt to each player, or with dealt=True the
      damage each player dealt to every enemy, hero dealers and targets only
    - games needs match_id and account_id columns, anything else is ignored,
      and player games without matching rows contribute nothing
    """
    keys = ["match_id", "account_id"]
    wanted = games.lazy().select(keys).unique()

    mine = "dealer_account_id" if dealt else "target_account_id"
    other = "target_account_id" if dealt else "dealer_account_id"

    totals = (
        scan("damage", parquet_dir)
        .filter(
            pl.col("stat") == "damage",
            damage_category() != "total",
            pl.col(other).is_not_null(),
            pl.col("damage") != 0,
        )
        .select(
            "match_id",
            pl.col(mine).alias("account_id"),
            pl.col(other).alias("enemy_account_id"),
            "damage",
        )
        .join(wanted, on=keys)
        .group_by(*keys, "enemy_account_id")
        .agg(pl.col("damage").sum())
    )

    enemies = scan("players", parquet_dir).select(
        "match_id",
        pl.col("account_id").alias("enemy_account_id"),
        pl.col("hero").alias("enemy"),
    )

    return (
        totals.join(enemies, on=["match_id", "enemy_account_id"], how="left")
        .sort([*keys, "damage"], descending=[False, False, True])
        .select(*keys, "enemy_account_id", "enemy", "damage")
    )


def soul_intervals(
    match_id: int,
    account_id: int,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Split the souls for one player into per source gains per interval.

    - value is souls + souls_orbs, the in game per source number
    - soul_sources samples about every three minutes, so a gain lands in the
      interval holding the sample that recorded it
    - one row per source per interval, sources with any souls, ordered by total
    """
    duration = (
        scan("matches", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("duration_s")
        .collect()
    )

    if duration.is_empty():
        msg = f"match {match_id} not in the tables"
        raise ValueError(msg)

    samples = (
        scan("soul_sources", parquet_dir)
        .filter(pl.col("match_id") == match_id, pl.col("account_id") == account_id)
        .select(
            "source_name", "time_stamp_s", (pl.col("souls") + pl.col("souls_orbs")).alias("souls")
        )
        .collect()
    )

    if samples.is_empty():
        msg = f"account {account_id} has no soul sources in match {match_id}"
        raise ValueError(msg)

    duration_s = int(duration.item())
    bucket = ((pl.col("time_stamp_s") - 1) // interval_s).clip(0).cast(pl.Int64).alias("interval")
    cumulative = (
        samples.with_columns(bucket).group_by("source_name", "interval").agg(pl.col("souls").max())
    )

    n = cumulative.select(pl.col("interval").max()).item() + 1
    grid = (
        samples.select("source_name")
        .unique()
        .join(pl.DataFrame({"interval": range(n)}, schema={"interval": pl.Int64}), how="cross")
    )

    gains = (
        grid.join(cumulative, on=["source_name", "interval"], how="left")
        .sort("source_name", "interval")
        .with_columns(
            pl.col("souls").fill_null(strategy="forward").fill_null(0).over("source_name")
        )
        .with_columns(pl.col("souls") - pl.col("souls").shift(1).fill_null(0).over("source_name"))
        .with_columns(pl.col("souls").sum().over("source_name").alias("total"))
    )

    return (
        gains.with_columns(
            (pl.col("interval") * interval_s).alias("start_s"),
            ((pl.col("interval") + 1) * interval_s).clip(upper_bound=duration_s).alias("end_s"),
        )
        .filter(pl.col("total") > 0)
        .sort(["total", "source_name", "interval"], descending=[True, False, False])
        .select("source_name", "start_s", "end_s", "souls", "total")
    )


def source_intervals(
    games: pl.DataFrame | pl.LazyFrame,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
    stat: str = "damage",
) -> pl.LazyFrame:
    """Split damage or healing by source and interval for multiple players.

    - the many-game version of damage_intervals, same semantics per player:
      detail rows on hero targets only, zero samples dropped, a gain lands
      in the interval holding the sample that recorded it, forward fill
      carries the cumulative value of a source across intervals without a
      sample
    - games needs match_id and account_id columns, anything else is ignored,
      and player games without matching rows just contribute nothing
    - full marks intervals that run the whole interval_s, the last interval
      ends at the match end so it can be shorter
    """
    keys = ["match_id", "account_id"]
    wanted = games.lazy().select(keys).unique()
    bucket = ((pl.col("time_stamp_s") - 1) // interval_s).clip(0).cast(pl.Int64).alias("interval")
    rows = (
        scan("damage_sources", parquet_dir)
        .rename({"dealer_account_id": "account_id"})
        .join(wanted, on=keys)
        .filter(
            pl.col("stat") == stat,
            pl.col("vs_heroes"),
            damage_category() != "total",
            pl.col("damage") != 0,
        )
    )
    samples = (
        with_delivery(rows, parquet_dir)
        .with_columns(bucket)
        .group_by(*keys, "source_name", "delivery", "interval")
        .agg(pl.col("damage").max())
    )

    sources = samples.select(*keys, "source_name", "delivery").unique()
    spans = samples.group_by(keys).agg(pl.col("interval").max().alias("n"))
    grid = (
        sources.join(spans, on=keys)
        .with_columns(pl.int_ranges(0, pl.col("n") + 1).alias("interval"))
        .explode("interval", empty_as_null=False)
        .drop("n")
    )
    durations = scan("matches", parquet_dir).select("match_id", "duration_s")

    return (
        grid.join(samples, on=[*keys, "source_name", "delivery", "interval"], how="left")
        .sort(*keys, "source_name", "interval")
        .with_columns(
            pl.col("damage").fill_null(strategy="forward").fill_null(0).over(*keys, "source_name")
        )
        .with_columns(
            pl.col("damage") - pl.col("damage").shift(1).fill_null(0).over(*keys, "source_name")
        )
        .with_columns(pl.col("damage").sum().over(*keys, "source_name").alias("total"))
        .join(durations, on="match_id")
        .with_columns(
            (pl.col("interval") * interval_s).alias("start_s"),
            ((pl.col("interval") + 1) * interval_s)
            .clip(upper_bound=pl.col("duration_s"))
            .alias("end_s"),
        )
        .with_columns((pl.col("end_s") - pl.col("start_s") == interval_s).alias("full"))
        .sort(
            [*keys, "total", "source_name", "interval"],
            descending=[False, False, True, False, False],
        )
        .select(*keys, "source_name", "delivery", "start_s", "end_s", "full", "damage", "total")
    )


def source_totals(
    games: pl.DataFrame | pl.LazyFrame,
    parquet_dir: str | Path | None = None,
    stat: str = "damage",
) -> pl.LazyFrame:
    """Total damage or healing by source for multiple players, one row per source.

    - the whole-game twin of source_intervals: reads the final-total `damage`
      table, never the cumulative `damage_sources` snapshots, so a plain sum
      is safe
    - detail rows on hero targets only, screen `total` rows and zero rows
      dropped, delivery carried through for gun/ability/item grouping
    - games needs match_id and account_id columns, anything else is ignored,
      and player games without matching rows contribute nothing
    """
    keys = ["match_id", "account_id"]
    wanted = games.lazy().select(keys).unique()
    detail = hero_damage(stat, parquet_dir).rename({"dealer_account_id": "account_id"})

    return (
        detail.join(wanted, on=keys)
        .group_by(*keys, "source_name", "delivery")
        .agg(pl.col("damage").sum())
        .sort([*keys, "damage"], descending=[False, False, True])
        .select(*keys, "source_name", "delivery", "damage")
    )


def team_intervals(
    match_id: int,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Split a match into intervals of souls gained per team, with the running lead.

    - the cumulative net worth of each player carries forward through intervals
      without a snapshot, so a gap for one player never dents the team total
    - lead is the team 0 total minus the team 1 total at the interval end
    """
    duration = (
        scan("matches", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("duration_s")
        .collect()
    )

    if duration.is_empty():
        msg = f"match {match_id} not in the tables"
        raise ValueError(msg)

    snaps = (
        scan("stats", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("account_id", "time_stamp_s", "net_worth")
        .collect()
    )

    if snaps.is_empty():
        msg = f"match {match_id} has no snapshots"
        raise ValueError(msg)

    duration_s = int(duration.item())
    bucket = ((pl.col("time_stamp_s") - 1) // interval_s).clip(0).cast(pl.Int64).alias("interval")
    cumulative = (
        snaps.with_columns(bucket).group_by("account_id", "interval").agg(pl.col("net_worth").max())
    )

    n = cumulative.select(pl.col("interval").max()).item() + 1
    grid = (
        cumulative.select("account_id")
        .unique()
        .join(pl.DataFrame({"interval": range(n)}, schema={"interval": pl.Int64}), how="cross")
    )
    filled = (
        grid.join(cumulative, on=["account_id", "interval"], how="left")
        .sort("account_id", "interval")
        .with_columns(
            pl.col("net_worth").fill_null(strategy="forward").fill_null(0).over("account_id")
        )
    )

    teams = (
        scan("players", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("account_id", "team")
        .collect()
    )

    return (
        filled.join(teams, on="account_id")
        .group_by("interval", "team")
        .agg(pl.col("net_worth").sum())
        .pivot(on="team", index="interval", values="net_worth")
        .rename({"0": "total_team0", "1": "total_team1"})
        .sort("interval")
        .with_columns(
            (pl.col("total_team0") - pl.col("total_team0").shift(1).fill_null(0)).alias(
                "souls_team0"
            ),
            (pl.col("total_team1") - pl.col("total_team1").shift(1).fill_null(0)).alias(
                "souls_team1"
            ),
            (pl.col("total_team0") - pl.col("total_team1")).alias("lead"),
            (pl.col("interval") * interval_s).alias("start_s"),
            ((pl.col("interval") + 1) * interval_s).clip(upper_bound=duration_s).alias("end_s"),
        )
        .select("start_s", "end_s", "souls_team0", "souls_team1", "lead")
    )
