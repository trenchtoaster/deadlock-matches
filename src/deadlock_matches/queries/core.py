"""Shared table scans, account defaults, and era joins."""

from __future__ import annotations

import contextlib
import contextvars
import datetime as dt
import functools
import operator
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import polars as pl

from deadlock_matches import config, export, extract, schemas
from deadlock_matches.assets import heroes
from deadlock_matches.assets import skill_rating as sr
from deadlock_matches.queries.labels import (
    game_mode_name,
    hero_name,
    lane_name,
    match_mode_name,
    with_hero_name,
    with_lane_name,
)
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

INHERIT: Literal["inherit"] = "inherit"

type ModeArg = int | Sequence[int] | Literal["inherit"] | None
type RankedArg = bool | Literal["inherit"] | None

RANKED_MODES = (extract.MATCH_MODE_STANDARD, extract.MATCH_MODE_RANKED)

type Modes = tuple[int | Sequence[int] | None, int | Sequence[int] | None, bool | None]

RANKED_PLAY: Modes = (RANKED_MODES, extract.GAME_MODE_NORMAL, True)

_AMBIENT_MODES: contextvars.ContextVar[Modes] = contextvars.ContextVar(
    "deadlock_modes", default=RANKED_PLAY
)


@contextlib.contextmanager
def mode_context(
    match_mode: int | Sequence[int] | None = RANKED_MODES,
    game_mode: int | Sequence[int] | None = extract.GAME_MODE_NORMAL,
    *,
    ranked: bool | None = True,
) -> Iterator[None]:
    """Make one queue the default for every view inside the block.

    - a report picks its games this way instead of every helper growing three
      more arguments
    - the standing default is ranked play across both queue eras
    - build 6652 moved ranked play from match_mode 1 to match_mode 4, so a
      single match mode covers only one side of 2026-07-30
    - match_mode and game_mode each take one mode or several
    - ranked True keeps ranked play and False keeps the unranked queue build
      6652 introduced
    - None on any argument lifts that part of the filter
    """
    token = _AMBIENT_MODES.set((match_mode, game_mode, ranked))

    try:
        yield
    finally:
        _AMBIENT_MODES.reset(token)


def _resolved_modes(match_mode: ModeArg, game_mode: ModeArg, ranked: RankedArg) -> Modes:
    """Fall back to the ambient modes for whichever argument was left to inherit."""
    ambient_match, ambient_game, ambient_ranked = _AMBIENT_MODES.get()

    return (
        ambient_match if match_mode == INHERIT else match_mode,
        ambient_game if game_mode == INHERIT else game_mode,
        ambient_ranked if ranked == INHERIT else ranked,
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

    - parquet_dir defaults to whatever parquet_dir_context set, then to the
      standard export directory, here and in every query below
    - an asset table missing from parquet_dir is read from the standard
      export directory instead, so secondary stores like parquet-players
      share one copy
    """
    if table not in schemas.TABLES:
        known = ", ".join(schemas.TABLES)
        msg = f"Unknown table {table!r}, tables: {known}"
        raise ValueError(msg)

    parquet_dir = _resolved_parquet_dir(parquet_dir)

    if schemas.is_partitioned(table):
        directory = schemas.partition_dir(table, parquet_dir)

        if directory.is_dir():
            return pl.scan_parquet(str(directory / "**/*.parquet"), hive_partitioning=True)

    path = schemas.table_path(table, parquet_dir)

    if table in schemas.ASSET_TABLES and not path.exists():
        path = schemas.table_path(table, export.PARQUET_DIR)

    return pl.scan_parquet(path)


def table_exists(table: str, parquet_dir: str | Path | None = None) -> bool:
    """Check whether a table is on disk.

    - counts a month-partitioned directory or a single parquet file
    - asset tables fall back to the standard export directory like scan
    """
    if table not in schemas.TABLES:
        known = ", ".join(schemas.TABLES)
        msg = f"Unknown table {table!r}, tables: {known}"
        raise ValueError(msg)

    parquet_dir = _resolved_parquet_dir(parquet_dir)

    if schemas.is_partitioned(table):
        directory = schemas.partition_dir(table, parquet_dir)

        if directory.is_dir() and next(directory.glob("month=*/*.parquet"), None) is not None:
            return True

    if schemas.table_path(table, parquet_dir).exists():
        return True

    return table in schemas.ASSET_TABLES and schemas.table_path(table, export.PARQUET_DIR).exists()


def player_rows(parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Read players with hero, lane, and starting Ranked badge labels derived from ids."""
    rows = with_lane_name(with_hero_name(scan("players", parquet_dir)))

    return rows.with_columns(skill_rating_asof("player_rank_initial_display_rank").alias("rank"))


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
    """Filter to one hero by name.

    - a typo raises instead of quietly returning nothing
    """
    hero_id = heroes.hero_id_by_name(name)

    if hero_id is None:
        msg = f"Unknown hero {name!r}"
        raise ValueError(msg)

    return pl.col("hero_id") == hero_id


SCORED = ~pl.col("matches.not_scored").fill_null(value=False) & (
    pl.col("player_match_outcome").is_null()
    | (pl.col("player_match_outcome") != extract.pb.k_EPlayerMatchOutcome_NotScored)
)

MY_GAMES_DIMENSIONS = {
    "account": Dimension(pl.col("account_id")),
    "hero": Dimension(hero_name(), resolve=hero_filter),
    "match_mode": Dimension(
        match_mode_name("matches.match_mode"),
        comment="Standard, Ranked, New Player Placement, or Private Lobby. "
        "Views keep ranked play unless match_mode= says otherwise. Ranked play "
        "spans Standard before build 6652 and Ranked after it.",
    ),
    "game_mode": Dimension(
        game_mode_name("matches.game_mode"),
        comment="Normal or Street Brawl, which is a different map and ruleset "
        "carrying the same match mode. Views keep Normal alone.",
    ),
    "assigned_lane": Dimension(
        pl.col("assigned_lane"),
        comment="Raw engine id, use lane for the readable color.",
    ),
    "lane": Dimension(
        lane_name(),
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


def mode_filter(
    match_mode: ModeArg = INHERIT,
    game_mode: ModeArg = INHERIT,
    ranked: RankedArg = INHERIT,
    *,
    prefix: str = "matches.",
) -> pl.Expr | None:
    """Build the mode filter every report over your own games starts from.

    - every argument inherits from mode_context, which stands at ranked play
      across both queue eras
    - match_mode and game_mode each take one mode or several
    - Street Brawl runs a different map and ruleset while still carrying
      match_mode 1, so game_mode has to be pinned separately
    - ranked reads ranked_type, which build 6652 started recording. It is null
      on every earlier game, when match_mode 1 was itself the ranked queue, so
      null counts as ranked
    - None on any side lifts that part of the filter
    - prefix names the joined match-column namespace; use an empty prefix
      after joining a raw matches frame
    """
    match_mode, game_mode, ranked = _resolved_modes(match_mode, game_mode, ranked)
    clauses = []

    for column, selected in (("match_mode", match_mode), ("game_mode", game_mode)):
        if selected is None:
            continue

        modes = (selected,) if isinstance(selected, int) else tuple(selected)
        clauses.append(pl.col(f"{prefix}{column}").is_in(modes))

    if ranked is not None:
        unranked = pl.col(f"{prefix}ranked_type").fill_null(extract.RANKED_TYPE_RANKED) == (
            extract.RANKED_TYPE_UNRANKED
        )
        clauses.append(~unranked if ranked else unranked)

    if not clauses:
        return None

    return functools.reduce(operator.and_, clauses)


def mode_label(
    match_mode: ModeArg = INHERIT,
    game_mode: ModeArg = INHERIT,
    ranked: RankedArg = INHERIT,
) -> str:
    """Name the queue a mode selection reads, the way the game names it.

    - the counterpart to mode_filter, which lets an empty result name the
      queue that came back empty
    - every argument inherits from mode_context like the filter does
    - ranked play reads as Ranked across both queue eras, since its match mode
      is a pair rather than the single mode each explicit selection pins
    - a fully lifted selection has no queue to name and reads as empty
    """
    match_mode, game_mode, ranked = _resolved_modes(match_mode, game_mode, ranked)

    if isinstance(match_mode, int):
        if match_mode == extract.MATCH_MODE_RANKED:
            return "Ranked"

        if match_mode == extract.MATCH_MODE_PLACEMENT:
            return "New Player Placement"

        if match_mode == extract.MATCH_MODE_PRIVATE_LOBBY:
            return "Private Lobby"

        if game_mode == extract.GAME_MODE_STREET_BRAWL:
            return "Street Brawl"

        return "Standard"

    if ranked:
        return "Ranked"

    return ""


def _played_matches(
    accounts: Sequence[int] | None,
    tz: str | None,
    match_mode: ModeArg = INHERIT,
    game_mode: ModeArg = INHERIT,
    ranked: RankedArg = INHERIT,
) -> MetricView:
    """Join player rows to their match and carry the local start time.

    - the timezone lands inside an expression, so the local start has to be
      built where the parameter is known, and everything derived from it
      then reads one column
    - the mode arguments inherit from mode_context, which stands at
      ranked play
    """
    zone = config.config_timezone() if tz is None else tz
    modes = mode_filter(match_mode, game_mode, ranked)
    accounts_filter = pl.col("account_id").is_in(_resolved_accounts(accounts))

    return MetricView(
        source="players",
        joins=(Join("matches", using="match_id"),),
        filter=accounts_filter if modes is None else accounts_filter & modes,
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
    match_mode: ModeArg = INHERIT,
    game_mode: ModeArg = INHERIT,
    ranked: RankedArg = INHERIT,
) -> MetricView:
    """One row per match the player appeared in, joined to match details.

    - grouping by day or week uses the local date, not the UTC date
    - accounts (Steam32 account IDs) and tz default to config.toml and
      the detected zone
    - ranked play across both queue eras is the default, so the unranked
      Standard queue, Street Brawl, and private lobbies stay out of every
      rate built on this view
    - the mode arguments inherit from mode_context unless passed
    - game_mode=extract.GAME_MODE_STREET_BRAWL gives the brawl games alone
    - None on any argument lifts that part of the filter
    """
    return MetricView(source=_played_matches(accounts, tz, match_mode, game_mode, ranked))


def _local_day(frame: pl.LazyFrame, tz: str | None) -> pl.LazyFrame:
    """Add start_local/day columns in the given zone from the start_time column."""
    tz = config.config_timezone() if tz is None else tz

    return frame.with_columns(
        pl.col("start_time").dt.convert_time_zone(tz).alias("start_local")
    ).with_columns(pl.col("start_local").dt.date().alias("day"))


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


def skill_rating_asof(column: str, at: str = "start_time") -> pl.Expr:
    """Skill rating labels for a badge level column, resolved at a datetime column.

    - each row takes the rank names in effect at its own time, so a
      historical badge keeps the name its era used
    - no committed rank history falls back to skill_rating
    """
    eras = sr.era_labels()

    if not eras:
        return skill_rating(column)

    def mapped(labels: dict[int, str]) -> pl.Expr:
        return pl.col(column).replace_strict(labels, default=None, return_dtype=pl.String)

    expr = mapped(eras[0][1])

    for start, labels in eras[1:]:
        expr = pl.when(pl.col(at) >= start).then(mapped(labels)).otherwise(expr)

    return expr
