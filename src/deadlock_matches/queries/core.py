"""Shared table scans, account defaults, and era joins."""

from __future__ import annotations

import contextlib
import contextvars
import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from deadlock_matches import config, export, schemas
from deadlock_matches.assets import heroes
from deadlock_matches.assets import skill_rating as sr
from deadlock_matches.queries.labels import hero_name, with_hero_name
from deadlock_matches.queries.semantic import (
    Dimension,
    Join,
    Measure,
    MetricView,
    try_divide,
    view,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence


_ERA_SENTINEL = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)

_AMBIENT_PARQUET_DIR: contextvars.ContextVar[str | Path | None] = contextvars.ContextVar(
    "deadlock_parquet_dir", default=None
)


@contextlib.contextmanager
def parquet_dir_context(parquet_dir: str | Path | None) -> Iterator[None]:
    """Make one export directory the default for every scan inside the block.

    - a metric view picks its files this way, because the directory decides
      which files a source reads rather than landing inside an expression
    - None leaves whatever directory is already in effect alone
    """
    if parquet_dir is None:
        yield
        return

    token = _AMBIENT_PARQUET_DIR.set(parquet_dir)

    try:
        yield
    finally:
        _AMBIENT_PARQUET_DIR.reset(token)


def _resolved_parquet_dir(parquet_dir: str | Path | None) -> str | Path:
    """Fall back to the ambient directory, then to the standard export directory."""
    if parquet_dir is not None:
        return parquet_dir

    ambient = _AMBIENT_PARQUET_DIR.get()

    return export.PARQUET_DIR if ambient is None else ambient


def scan(table: str, parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Lazily scan one exported table by name (one of schemas.TABLES).

    parquet_dir defaults to whatever parquet_dir_context set, then to the
    standard export directory, here and in every query below. An asset table
    missing from parquet_dir is read from the standard export directory
    instead, so secondary stores like parquet-players share one copy.
    """
    if table not in schemas.TABLES:
        known = ", ".join(schemas.TABLES)
        msg = f"Unknown table {table!r}, tables: {known}"
        raise ValueError(msg)

    parquet_dir = _resolved_parquet_dir(parquet_dir)

    if schemas.is_partitioned(table):
        directory = schemas.partition_dir(table, parquet_dir)

        if directory.is_dir():
            return pl.scan_parquet(str(directory / "*.parquet"))

    path = schemas.table_path(table, parquet_dir)

    if table in schemas.ASSET_TABLES and not path.exists():
        path = schemas.table_path(table, export.PARQUET_DIR)

    return pl.scan_parquet(path)


def table_exists(table: str, parquet_dir: str | Path | None = None) -> bool:
    """Whether a table is on disk, as a month-partitioned directory or a single parquet file.

    Asset tables fall back to the standard export directory like scan.
    """
    if table not in schemas.TABLES:
        known = ", ".join(schemas.TABLES)
        msg = f"Unknown table {table!r}, tables: {known}"
        raise ValueError(msg)

    parquet_dir = _resolved_parquet_dir(parquet_dir)

    if schemas.is_partitioned(table):
        directory = schemas.partition_dir(table, parquet_dir)

        if directory.is_dir() and next(directory.glob("*.parquet"), None) is not None:
            return True

    if schemas.table_path(table, parquet_dir).exists():
        return True

    return table in schemas.ASSET_TABLES and schemas.table_path(table, export.PARQUET_DIR).exists()


def player_rows(parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Read players with the current hero display name derived from hero_id."""
    return with_hero_name(scan("players", parquet_dir))


def _asof_era_join(
    left: pl.LazyFrame,
    right: pl.LazyFrame,
    by: str | Sequence[str],
    on: str = "start_time",
) -> pl.LazyFrame:
    """Join right onto left by the era live at the time of each left row.

    - right carries an era_from datetime column and the join key(s) in by
    - backward as-of on era_from <= left[on], grouped by the key(s)
    - rows older than the first era fall back to the earliest era, matching record_asof
    """
    by_cols = [by] if isinstance(by, str) else list(by)
    prepared = right.with_columns(
        pl.when(pl.col("era_from") == pl.col("era_from").min().over(by_cols))
        .then(pl.lit(_ERA_SENTINEL))
        .otherwise(pl.col("era_from"))
        .alias("_join_from")
    ).sort("_join_from")

    return (
        left.sort(on)
        .join_asof(
            prepared,
            left_on=on,
            right_on="_join_from",
            by=by_cols,
            strategy="backward",
            check_sortedness=False,
        )
        .drop("_join_from")
    )


def asset_asof(
    left: pl.LazyFrame,
    table: str,
    by: str,
    on: str = "start_time",
    parquet_dir: str | Path | None = None,
) -> pl.LazyFrame:
    """Join a versioned asset table onto left rows by the era live at their time.

    - backward as-of on era_from <= left[on], grouped by the asset key
    - rows older than the first era fall back to the earliest era, matching record_asof
    """
    return _asof_era_join(left, scan(table, parquet_dir), by, on)


def hero_filter(name: str) -> pl.Expr:
    """Filter to one hero by name, raising on a typo instead of returning nothing."""
    hero_id = heroes.hero_id_by_name(name)

    if hero_id is None:
        msg = f"Unknown hero {name!r}"
        raise ValueError(msg)

    return pl.col("hero_id") == hero_id


SCORED = ~pl.col("matches.not_scored").fill_null(value=False)

MY_GAMES_DIMENSIONS = {
    "account": Dimension(pl.col("account_id")),
    "hero": Dimension(hero_name(), resolve=hero_filter),
    "match_mode": Dimension(pl.col("matches.match_mode"), comment="1 is ranked."),
    "assigned_lane": Dimension(
        pl.col("assigned_lane"),
        comment="Raw engine id, use lane for the readable color.",
    ),
    "lane": Dimension(
        pl.col("lane"),
        comment="Lane color, the same for both teams where left and right flip.",
    ),
    "day": Dimension(pl.col("start_local").dt.date(), comment="Local date, not the UTC date."),
    "week": Dimension(pl.col("start_local").dt.strftime("%G-W%V")),
    "month": Dimension(pl.col("start_local").dt.strftime("%Y-%m")),
    "won": Dimension(pl.col("won")),
    "scored": Dimension(SCORED, comment="False for the matches Valve left unscored."),
}

MY_GAMES_MEASURES = {
    "games": Measure(pl.len(), "count", comment="Every game, scored or not.", missing="zero"),
    "scored_games": Measure(
        SCORED.sum(), "count", comment="The win rate denominator.", missing="zero"
    ),
    "wins": Measure(
        (pl.col("won") & SCORED).sum(),
        "count",
        comment="Wins in scored games, an unscored win is not counted.",
        direction="maximize",
        missing="zero",
    ),
    "losses": Measure(
        (~pl.col("won") & SCORED).sum(),
        "count",
        direction="minimize",
        missing="zero",
    ),
    "win_rate": Measure(
        lambda measure: try_divide(measure["wins"], measure["scored_games"]),
        "proportion",
        comment="Wins over scored games as a proportion, never the mean of per-group rates.",
        synonyms=("winrate",),
        direction="maximize",
    ),
    "kills": Measure(pl.col("kills").sum(), "count", direction="maximize", missing="zero"),
    "deaths": Measure(pl.col("deaths").sum(), "count", direction="minimize", missing="zero"),
    "assists": Measure(pl.col("assists").sum(), "count", direction="maximize", missing="zero"),
    "kda": Measure(
        lambda measure: try_divide(measure["kills"] + measure["assists"], measure["deaths"]),
        "ratio",
        comment="Kills plus assists over deaths, pooled across the group.",
        direction="maximize",
    ),
    "last_hits": Measure(pl.col("last_hits").sum(), "count", direction="maximize", missing="zero"),
    "denies": Measure(pl.col("denies").sum(), "count", direction="maximize", missing="zero"),
    "net_worth": Measure(
        pl.col("net_worth").sum(),
        "souls",
        comment="Final net worth summed, not gross souls earned, souls_by_source has those.",
        direction="maximize",
        missing="zero",
    ),
    "net_worth_per_game": Measure(
        lambda measure: try_divide(measure["net_worth"], measure["games"]),
        "souls",
        direction="maximize",
    ),
}


def _played_matches(accounts: Sequence[int] | None, tz: str | None) -> MetricView:
    """Player rows joined to their match, carrying the local start time.

    - the timezone lands inside an expression, so the local start has to be
      built where the parameter is known, and everything derived from it
      then reads one column
    """
    zone = config.config_timezone() if tz is None else tz

    return MetricView(
        source="players",
        joins=(Join("matches", using="match_id"),),
        filter=pl.col("account_id").is_in(_resolved_accounts(accounts)),
        dimensions={
            "start_local": Dimension(
                pl.col("matches.start_time").dt.convert_time_zone(zone),
                comment="Match start in the local zone, not UTC.",
            )
        },
    )


@view(
    grain=("match_id", "account_id"),
    dimensions=MY_GAMES_DIMENSIONS,
    measures=MY_GAMES_MEASURES,
)
def my_games(
    accounts: Sequence[int] | None = None,
    tz: str | None = None,
) -> MetricView:
    """One row per match the player appeared in, joined to match details.

    - grouping by day or week uses the local date, not the UTC date
    - accounts (Steam32 account IDs) and tz default to config.toml and
      the detected zone
    """
    return MetricView(source=_played_matches(accounts, tz))


def _local_day(frame: pl.LazyFrame, parquet_dir: str | Path | None, tz: str | None) -> pl.LazyFrame:
    """Join match start_time and add start_local/day columns in the given zone."""
    tz = config.config_timezone() if tz is None else tz

    return (
        frame.join(scan("matches", parquet_dir).select("match_id", "start_time"), on="match_id")
        .with_columns(pl.col("start_time").dt.convert_time_zone(tz).alias("start_local"))
        .with_columns(pl.col("start_local").dt.date().alias("day"))
    )


def _resolved_accounts(accounts: Sequence[int] | None) -> list[int]:
    """Resolve the accounts argument to config.toml when omitted."""
    resolved = config.config_accounts() if accounts is None else list(accounts)

    if not resolved:
        msg = "no accounts: pass accounts= or fill in accounts in config.toml"
        raise ValueError(msg)

    return resolved


def skill_rating(column: str) -> pl.Expr:
    """Skill rating labels for a badge level column.

    - the badge encoding and label text come from skill_rating.label
    """
    mapping = {
        tier * 10 + level: sr.label(tier * 10 + level)
        for tier in sr.tier_map()
        for level in range(7)
    }

    return pl.col(column).replace_strict(mapping, default=None, return_dtype=pl.String)
