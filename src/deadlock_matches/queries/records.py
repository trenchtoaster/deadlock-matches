"""Winrate records over local day windows."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import polars.selectors as cs

from deadlock_matches import config
from deadlock_matches.assets import heroes
from deadlock_matches.assets import skill_rating as sr
from deadlock_matches.queries.core import my_games, scan

if TYPE_CHECKING:
    from collections.abc import Sequence


def daily_record(
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    tz: str | None = None,
    days: int | None = None,
    since: str | dt.date | None = None,
    hero: str | None = None,
    by: str = "day",
    games: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Per local day W/L record with net wins and a running total.

    days keeps only the last N days of games, None keeps everything. since
    keeps only days on or after that date (YYYY-MM-DD or YYYYMMDD, like 2026-07-01). hero filters to
    one hero. by rolls the days into week or month buckets, where a
    week starts on Monday. games takes a precomputed record_games frame
    instead of scanning again.

    - unscored matches stay out of every count, unscored_record has those
    - abandons counts the games where anyone abandoned
    - lobby is the average lobby rating label, averaged in subrank steps
    - subrank_sum and rated_games are the raw pieces, for an overall average
    """
    if by not in ("day", "week", "month"):
        msg = f"Unknown bucket {by!r}, use day, week, or month"
        raise ValueError(msg)

    if games is None:
        games = record_games(parquet_dir, accounts, tz, days, since, hero)

    games = _scored(games)

    abandoned_ids = (
        scan("players", parquet_dir)
        .filter(
            pl.col("abandon_time_s").is_not_null(),
            pl.col("match_id").is_in(games.get_column("match_id").implode()),
        )
        .select("match_id")
        .unique()
        .collect()
        .to_series()
    )

    daily = (
        games.with_columns(pl.col("match_id").is_in(abandoned_ids.implode()).alias("abandoned"))
        .group_by("day")
        .agg(
            pl.len().cast(pl.Int32).alias("games"),
            pl.col("won").sum().cast(pl.Int32).alias("wins"),
            (pl.col("mvp_rank") == 1).sum().cast(pl.Int32).alias("mvps"),
            (pl.col("mvp_rank") >= 2).sum().cast(pl.Int32).alias("key_players"),
            pl.col("abandoned").sum().cast(pl.Int32).alias("abandons"),
            pl.col("lobby_subrank").sum().alias("subrank_sum"),
            pl.col("lobby_subrank").count().cast(pl.Int32).alias("rated_games"),
        )
        .sort("day")
    )

    if by != "day":
        every = "1w" if by == "week" else "1mo"
        daily = (
            daily.group_by(pl.col("day").dt.truncate(every))
            .agg(cs.exclude("day").sum())
            .sort("day")
        )

    return (
        daily.with_columns((pl.col("games") - pl.col("wins")).alias("losses"))
        .with_columns(
            (pl.col("wins") / pl.col("games") * 100).alias("win_rate"),
            (pl.col("wins") - pl.col("losses")).alias("net"),
            pl.when(pl.col("rated_games") > 0)
            .then(pl.col("subrank_sum") / pl.col("rated_games"))
            .alias("_mean_subrank"),
        )
        .with_columns(
            pl.col("net").cum_sum().alias("cum_net"),
            _subrank_label("_mean_subrank").alias("lobby"),
        )
        .drop("_mean_subrank")
    )


def _scored(games: pl.DataFrame) -> pl.DataFrame:
    """Keep only the matches Valve scored, the winrate table leaves the rest out."""
    return games.filter(~pl.col("not_scored").fill_null(value=False))


def _subrank(column: str) -> pl.Expr:
    """Badge level column as a linear subrank count, skill_rating.subrank_index as an expression."""
    return (pl.col(column) // 10) * 6 + pl.col(column) % 10


def _subrank_label(column: str) -> pl.Expr:
    """Rating label for a mean subrank column, back to a badge then through skill_rating."""
    tier = (pl.col(column).round(0).cast(pl.Int64) - 1) // 6
    badge = tier * 10 + pl.col(column).round(0).cast(pl.Int64) - tier * 6

    mapping = {
        tier * 10 + level: sr.label(tier * 10 + level)
        for tier in sr.tier_map()
        for level in range(7)
    }

    return badge.replace_strict(mapping, default=None, return_dtype=pl.String)


def record_games(
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    tz: str | None = None,
    days: int | None = None,
    since: str | dt.date | None = None,
    hero: str | None = None,
) -> pl.DataFrame:
    """Take one row per match in the winrate window.

    days keeps only the last N days that had games, None keeps everything.
    The result feeds daily_record, abandon_record, and unscored_record
    through their games parameter.
    """
    lf = my_games(parquet_dir, accounts, tz)

    if hero is not None:
        hero_id = heroes.hero_id_by_name(hero)

        if hero_id is None:
            msg = f"Unknown hero {hero!r}"
            raise ValueError(msg)

        lf = lf.filter(pl.col("hero_id") == hero_id)

    if since is not None:
        since = dt.date.fromisoformat(since) if isinstance(since, str) else since
        lf = lf.filter(pl.col("day") >= since)

    if days is not None:
        lf = lf.filter(pl.col("day").rank("dense", descending=True) <= days)

    return (
        lf.unique(subset="match_id")
        .select(
            "match_id",
            "team",
            "day",
            "won",
            "mvp_rank",
            "not_scored",
            pl.mean_horizontal(
                _subrank("average_badge_team0"), _subrank("average_badge_team1")
            ).alias("lobby_subrank"),
        )
        .collect()
    )


def abandon_record(
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    tz: str | None = None,
    days: int | None = None,
    since: str | dt.date | None = None,
    hero: str | None = None,
    games: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Take one row per scored match in the winrate window where someone abandoned.

    - same filters as daily_record, unscored matches stay out of both
    - games takes a precomputed record_games frame instead of scanning again
    - you/ally/enemy flag who left: you = one of your accounts, ally = a
      teammate, enemy = someone on the other team
    - returned = the leaver dealt growing damage between samples after the
      abandon time, the only evidence that needs a player at the controls.
      Buys auto-fire from the queued build while the player is gone, deaths
      happen to an idle hero, so neither counts
    """
    accounts = config.config_accounts() if accounts is None else list(accounts)

    if not accounts:
        msg = "no accounts: pass accounts= or fill in accounts in config.toml"
        raise ValueError(msg)

    if games is None:
        games = record_games(parquet_dir, accounts, tz, days, since, hero)

    games = _scored(games)

    leaver_rows = (
        scan("players", parquet_dir)
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
        .group_by("match_id", pl.col("dealer_account_id").alias("account_id"), "time_stamp_s")
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
    games: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Take one row per unscored match the winrate table left out, same window filters.

    Match history still shows the result, the flag most likely means no
    rating change. games takes a precomputed record_games frame instead of
    scanning again.
    """
    if games is None:
        games = record_games(parquet_dir, accounts, tz, days, since, hero)

    return (
        games.filter(pl.col("not_scored").fill_null(value=False))
        .select("match_id", "day", "won")
        .sort("day", "match_id")
    )
