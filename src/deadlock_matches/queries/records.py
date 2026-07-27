"""Winrate records over local day windows."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from deadlock_matches import config
from deadlock_matches.queries.core import (
    INHERIT,
    ModeArg,
    hero_filter,
    my_games,
    player_rows,
    scan,
    skill_rating,
)
from deadlock_matches.queries.semantic import (
    Dimension,
    Measure,
    MetricView,
    Window,
    summarize,
    try_divide,
    view,
    view_frame,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


_SCORED = ~pl.col("not_scored").fill_null(value=False)


def daily_record(
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    tz: str | None = None,
    days: int | None = None,
    since: str | dt.date | None = None,
    hero: str | None = None,
    by: str = "day",
    games: pl.DataFrame | pl.LazyFrame | None = None,
) -> pl.DataFrame:
    """Build the per local day W/L record with net wins and a running total.

    - days keeps only the last N days of games, None keeps everything
    - since keeps only days on or after that date (YYYY-MM-DD or YYYYMMDD,
      like 2026-07-01)
    - hero filters to one hero
    - by rolls the days into week or month buckets, where a week starts on
      Monday
    - games takes a precomputed record_games frame instead of scanning again
    - unscored matches stay out of every count, unscored_record has those
    - abandons counts the games where anyone abandoned
    - win_rate is a proportion, not a percent, like the measure it comes from
    - lobby is the average lobby rating label, averaged in subrank steps
    - subrank_sum and rated_games are the raw pieces, for an overall average
    """
    if by not in ("day", "week", "month"):
        msg = f"Unknown bucket {by!r}, use day, week, or month"
        raise ValueError(msg)

    if games is None:
        games = view_frame(record_games(accounts, tz, days, since, hero), parquet_dir=parquet_dir)

    if isinstance(games, pl.LazyFrame):
        games = games.collect()

    games = _scored(games)

    abandoned_ids = (
        player_rows(parquet_dir)
        .filter(
            pl.col("abandon_time_s").is_not_null(),
            pl.col("match_id").is_in(games.get_column("match_id").implode()),
        )
        .select("match_id")
        .unique()
        .collect()
        .to_series()
    )

    dimension = RECORD_GAMES_DIMENSIONS[by].expr.alias(by)
    abandons = (
        games.lazy()
        .with_columns(dimension)
        .group_by(by)
        .agg(
            pl.col("match_id").is_in(abandoned_ids.implode()).sum().cast(pl.Int32).alias("abandons")
        )
    )
    daily = summarize(
        record_games,
        by=by,
        measures=(
            "games",
            "wins",
            "losses",
            "net",
            "cum_net",
            "win_rate",
            "mvps",
            "key_players",
            "subrank_sum",
            "rated_games",
            "lobby_badge",
        ),
        lf=games.lazy(),
    )
    result = (
        daily.join(abandons, on=by, how="left")
        .sort(by)
        .with_columns(
            pl.col(
                "games",
                "wins",
                "losses",
                "net",
                "cum_net",
                "mvps",
                "key_players",
                "rated_games",
            ).cast(pl.Int32),
            pl.col("abandons").fill_null(0).cast(pl.Int32),
        )
        .with_columns(skill_rating("lobby_badge").alias("lobby"))
        .drop("lobby_badge")
    )

    if by != "day":
        result = result.rename({by: "day"})

    return result.select(
        "day",
        "games",
        "wins",
        "mvps",
        "key_players",
        "abandons",
        "subrank_sum",
        "rated_games",
        "losses",
        "win_rate",
        "net",
        "cum_net",
        "lobby",
    ).collect()


def _scored(games: pl.DataFrame) -> pl.DataFrame:
    """Keep only the matches Valve scored.

    - the winrate table leaves the rest out
    """
    return games.filter(_SCORED)


def _subrank(column: str) -> pl.Expr:
    """Turn a badge level column into a linear subrank count.

    - the expression form of skill_rating.subrank_index
    """
    return (pl.col(column) // 10) * 6 + pl.col(column) % 10


def badge_from_subrank(subrank: pl.Expr) -> pl.Expr:
    """Round a mean subrank back to a badge level.

    - the expression form of skill_rating.badge_from_subrank
    """
    index = subrank.round(0).cast(pl.Int64)
    tier = (index - 1) // 6

    return (
        pl.when(index.is_null())
        .then(pl.lit(None, dtype=pl.Int64))
        .when(index > 0)
        .then(tier * 10 + index - tier * 6)
        .otherwise(0)
    )


RECORD_GAMES_DIMENSIONS = {
    "day": Dimension(pl.col("day"), comment="Local date, not the UTC date."),
    "week": Dimension(
        pl.col("day").dt.truncate("1w"),
        comment="Local week beginning Monday.",
    ),
    "month": Dimension(
        pl.col("day").dt.truncate("1mo"),
        comment="Local calendar month, represented by its first day.",
    ),
    "won": Dimension(pl.col("won")),
    "scored": Dimension(_SCORED, comment="False for the matches Valve left unscored."),
    "team": Dimension(pl.col("team")),
}

_SCORED_SUBRANK = pl.when(_SCORED).then(pl.col("lobby_subrank"))

RECORD_GAMES_MEASURES = {
    "games": Measure(pl.len(), "count", comment="Every game, scored or not.", missing="zero"),
    "scored_games": Measure(
        _SCORED.sum(), "count", comment="The win rate denominator.", missing="zero"
    ),
    "wins": Measure((pl.col("won") & _SCORED).sum(), "count", direction="maximize", missing="zero"),
    "losses": Measure(
        (~pl.col("won") & _SCORED).sum(), "count", direction="minimize", missing="zero"
    ),
    "net": Measure(
        lambda measure: measure["wins"].cast(pl.Int64) - measure["losses"].cast(pl.Int64),
        "count",
        comment="Wins minus losses.",
        direction="maximize",
        missing="zero",
    ),
    "cum_net": Measure(
        lambda measure: measure["net"],
        "count",
        comment="Net wins accumulated down the buckets, the running total the winrate table prints.",
        window=Window(order=("day", "week", "month"), range="cumulative"),
        direction="maximize",
    ),
    "win_rate": Measure(
        lambda measure: try_divide(measure["wins"], measure["scored_games"]),
        "proportion",
        comment="Wins over scored games as a proportion, never the mean of per-group rates.",
        synonyms=("winrate",),
        direction="maximize",
    ),
    "mvps": Measure(
        ((pl.col("mvp_rank") == 1) & _SCORED).sum(),
        "count",
        comment="MVP awards in scored games.",
        direction="maximize",
        missing="zero",
    ),
    "key_players": Measure(
        ((pl.col("mvp_rank") >= 2) & _SCORED).sum(),
        "count",
        comment="Key Player awards in scored games.",
        direction="maximize",
        missing="zero",
    ),
    "subrank_sum": Measure(
        _SCORED_SUBRANK.sum(),
        "subrank",
        comment="Additive lobby subrank total over scored games for recomputing an overall lobby average.",
        missing="zero",
    ),
    "rated_games": Measure(
        _SCORED_SUBRANK.count(),
        "count",
        comment="Scored games that carried a lobby badge average.",
        missing="zero",
    ),
    "lobby_subrank": Measure(
        lambda measure: try_divide(measure["subrank_sum"], measure["rated_games"]),
        "subrank",
        comment="Mean lobby subrank over scored games, a linear count. Badge levels skip 7-9, so average these, not badges.",
    ),
    "lobby_badge": Measure(
        lambda measure: badge_from_subrank(measure["lobby_subrank"]),
        "badge",
        comment="The mean scored-game lobby subrank rounded back to a badge level, ready for skill_rating.",
    ),
}


@view(
    grain=("match_id",),
    dimensions=RECORD_GAMES_DIMENSIONS,
    measures=RECORD_GAMES_MEASURES,
)
def record_games(
    accounts: Sequence[int] | None = None,
    tz: str | None = None,
    days: int | None = None,
    since: str | dt.date | None = None,
    hero: str | None = None,
    match_mode: ModeArg = INHERIT,
    game_mode: ModeArg = INHERIT,
) -> MetricView:
    """One row per match in the winrate window.

    - days keeps only the last N days that had games, None keeps everything
    - the result feeds daily_record, abandon_record, and unscored_record
      through their games parameter
    - match_mode and game_mode carry the my_games behaviour, so only ordinary
      matchmaking games count unless mode_context says otherwise
    """
    return MetricView(
        source=lambda: _record_game_rows(accounts, tz, days, since, hero, match_mode, game_mode)
    )


def _record_game_rows(
    accounts: Sequence[int] | None,
    tz: str | None,
    days: int | None,
    since: str | dt.date | None,
    hero: str | None,
    match_mode: ModeArg = INHERIT,
    game_mode: ModeArg = INHERIT,
) -> pl.LazyFrame:
    """Take the one row per match the winrate window keeps.

    - the result is already deduplicated
    """
    lf = view_frame(my_games(accounts, tz, match_mode, game_mode))

    if hero is not None:
        lf = lf.filter(hero_filter(hero))

    if since is not None:
        since = dt.date.fromisoformat(since) if isinstance(since, str) else since
        lf = lf.filter(pl.col("day") >= since)

    if days is not None:
        lf = lf.filter(pl.col("day").rank("dense", descending=True) <= days)

    return lf.unique(subset="match_id").select(
        "match_id",
        "team",
        "day",
        "won",
        "mvp_rank",
        pl.col("matches.not_scored").alias("not_scored"),
        pl.mean_horizontal(
            _subrank("matches.average_badge_team0"), _subrank("matches.average_badge_team1")
        ).alias("lobby_subrank"),
    )


def abandon_record(
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    tz: str | None = None,
    days: int | None = None,
    since: str | dt.date | None = None,
    hero: str | None = None,
    games: pl.DataFrame | pl.LazyFrame | None = None,
) -> pl.DataFrame:
    """Take one row per scored match in the winrate window where someone abandoned.

    - same filters as daily_record, unscored matches stay out of both
    - games takes a precomputed record_games frame instead of scanning again
    - you/ally/enemy flag who left: you = one of your accounts, ally = a
      teammate, enemy = someone on the other team
    - returned = the leaver dealt growing damage between samples after the
      abandon time, the only evidence that needs a player at the controls
    - buys auto-fire from the queued build while the player is gone and
      deaths happen to an idle hero, so neither counts
    """
    accounts = config.config_accounts() if accounts is None else list(accounts)

    if not accounts:
        msg = "no accounts: pass accounts= or fill in accounts in config.toml"
        raise ValueError(msg)

    if games is None:
        games = view_frame(record_games(accounts, tz, days, since, hero), parquet_dir=parquet_dir)

    if isinstance(games, pl.LazyFrame):
        games = games.collect()

    games = _scored(games)

    leaver_rows = (
        player_rows(parquet_dir)
        .filter(
            pl.col("abandon_time_s").is_not_null(),
            pl.col("match_id").is_in(games.get_column("match_id").implode()),
        )
        .select("match_id", "account_id", pl.col("team").alias("leaver_team"), "abandon_time_s")
        .collect()
    )

    match_ids = leaver_rows.get_column("match_id")

    damage_grew = (
        scan("damage_sources", parquet_dir)
        .filter(pl.col("match_id").is_in(match_ids.implode()))
        .group_by("match_id", "account_id", "time_stamp_s")
        .agg(pl.col("damage").sum())
        .join(leaver_rows.lazy(), on=["match_id", "account_id"])
        .filter(pl.col("time_stamp_s") > pl.col("abandon_time_s"))
        .group_by("match_id", "account_id")
        .agg((pl.col("damage").max() > pl.col("damage").min()).alias("damage_grew"))
    )

    leavers = (
        leaver_rows.lazy()
        .join(damage_grew, on=["match_id", "account_id"], how="left")
        .with_columns(
            pl.col("damage_grew").fill_null(value=False).alias("returned"),
            pl.col("account_id").is_in(accounts).alias("is_you"),
        )
        .collect()
    )

    joined = games.select("match_id", "day", "won", "team").join(
        leavers, on="match_id", how="inner"
    )

    return (
        joined.group_by("match_id")
        .agg(
            pl.col("day").first(),
            pl.col("won").first(),
            pl.col("is_you").any().alias("you"),
            (~pl.col("is_you") & (pl.col("leaver_team") == pl.col("team"))).any().alias("ally"),
            (pl.col("leaver_team") != pl.col("team")).any().alias("enemy"),
            pl.col("returned").any(),
        )
        .sort("day", "match_id")
    )


def unscored_record(
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    tz: str | None = None,
    days: int | None = None,
    since: str | dt.date | None = None,
    hero: str | None = None,
    games: pl.DataFrame | pl.LazyFrame | None = None,
) -> pl.DataFrame:
    """Take one row per unscored match the winrate table left out.

    - the same window filters as daily_record apply
    - match history still shows the result, so the flag most likely means
      no rating change
    - games takes a precomputed record_games frame instead of scanning again
    """
    if games is None:
        games = view_frame(record_games(accounts, tz, days, since, hero), parquet_dir=parquet_dir)

    if isinstance(games, pl.LazyFrame):
        games = games.collect()

    return (
        games.filter(pl.col("not_scored").fill_null(value=False))
        .select("match_id", "day", "won")
        .sort("day", "match_id")
    )
