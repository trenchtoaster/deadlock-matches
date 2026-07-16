"""Laning window snapshots and lane results."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from deadlock_matches.assets import heroes
from deadlock_matches.queries.core import my_games, scan

if TYPE_CHECKING:
    from collections.abc import Sequence


LANING_STATS = {
    "net_worth": "souls",
    "player_damage": "damage",
    "player_damage_taken": "damage_taken",
    "boss_damage": "obj_damage",
    "player_healing": "healing",
    "heal_prevented": "heal_prevented",
    "creep_kills": "creeps",
    "neutral_kills": "neutrals",
    "denies": "denies",
}


def laning_stats(
    match_id: int,
    mark_s: int,
    parquet_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Snapshot every player in one match at the last sample inside a window.

    - stat columns read the last snapshot at or before mark_s per player, and
      snap_s says which sample that was
    - kills and deaths count death events inside the window instead, since the
      snapshot fields drift from the match screen
    - one row per player with hero, team, and lane joined
    """
    players = (
        scan("players", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("account_id", "hero", "team", "lane")
        .collect()
    )

    if players.is_empty():
        msg = f"match {match_id} not in the tables"
        raise ValueError(msg)

    snaps = (
        scan("stats", parquet_dir)
        .filter(pl.col("match_id") == match_id, pl.col("time_stamp_s") <= mark_s)
        .group_by("account_id")
        .agg(
            pl.col(list(LANING_STATS)).sort_by("time_stamp_s").last(),
            pl.col("time_stamp_s").max().alias("snap_s"),
        )
        .rename(LANING_STATS)
    )

    victims = (
        scan("deaths", parquet_dir)
        .filter(pl.col("match_id") == match_id, pl.col("game_time_s") <= mark_s)
        .group_by("account_id")
        .agg(pl.len().cast(pl.Int64).alias("deaths"))
    )

    killers = (
        scan("deaths", parquet_dir)
        .filter(
            pl.col("match_id") == match_id,
            pl.col("game_time_s") <= mark_s,
            pl.col("killer_account_id").is_not_null(),
        )
        .group_by(pl.col("killer_account_id").alias("account_id"))
        .agg(pl.len().cast(pl.Int64).alias("kills"))
    )

    return (
        players.lazy()
        .join(snaps, on="account_id", how="left")
        .join(killers, on="account_id", how="left")
        .join(victims, on="account_id", how="left")
        .with_columns(pl.col(*LANING_STATS.values(), "kills", "deaths").fill_null(0))
        .sort("team", "lane", "account_id")
        .collect()
    )


def lane_records(
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    tz: str | None = None,
    days: int | None = None,
    since: str | dt.date | None = None,
    hero: str | None = None,
    mark_s: int = 540,
) -> pl.DataFrame:
    """Take one row per scored match with the lane result at a laning mark.

    - lane_net = net worth of the own side of the assigned lane minus the
      enemy side, both read from the last stats snapshot at or before mark_s
    - my_early = the deaths of the player inside the window
    - worst_early = the most deaths any single teammate had inside the window
    - ally_left = a teammate abandoned at some point in the match
    - days, since, and hero filter like record_games, not scored games and
      matches where any laner has no stats snapshot before the mark stay out
    """
    lf = my_games(parquet_dir, accounts, tz).filter(pl.col("not_scored").not_())

    if hero is not None:
        hero_id = heroes.hero_id_by_name(hero)

        if hero_id is None:
            msg = f"Unknown hero {hero!r}"
            raise ValueError(msg)

        lf = lf.filter(pl.col("hero_id") == hero_id)

    if since is not None:
        since = dt.date.fromisoformat(since) if isinstance(since, str) else since
        lf = lf.filter(pl.col("day") >= since)

    mine = lf.unique(subset="match_id").select(
        "match_id", "account_id", "team", "lane", "day", "won"
    )

    if days is not None:
        mine = mine.filter(pl.col("day").rank("dense", descending=True) <= days)

    sides = mine.select(
        "match_id",
        pl.col("account_id").alias("my_account"),
        pl.col("team").alias("my_team"),
        pl.col("lane").alias("my_lane"),
    )

    lobby = (
        scan("players", parquet_dir)
        .join(mine.select("match_id"), on="match_id", how="semi")
        .select("match_id", "account_id", "team", "lane", "abandon_time_s")
    )

    snaps = (
        scan("stats", parquet_dir)
        .join(mine.select("match_id"), on="match_id", how="semi")
        .filter(pl.col("time_stamp_s") <= mark_s)
        .group_by("match_id", "account_id")
        .agg(pl.col("net_worth").sort_by("time_stamp_s").last())
    )

    lanes = (
        lobby.join(snaps, on=["match_id", "account_id"], how="left")
        .join(sides, on="match_id")
        .filter(pl.col("lane") == pl.col("my_lane"))
        .group_by("match_id")
        .agg(
            lane_net=pl.col("net_worth").filter(pl.col("team") == pl.col("my_team")).sum()
            - pl.col("net_worth").filter(pl.col("team") != pl.col("my_team")).sum(),
            laners=pl.len(),
            sampled=pl.col("net_worth").is_not_null().sum(),
        )
        .filter(pl.col("laners") == pl.col("sampled"))
        .drop("laners", "sampled")
    )

    early = (
        scan("deaths", parquet_dir)
        .join(mine.select("match_id"), on="match_id", how="semi")
        .filter(pl.col("game_time_s") <= mark_s)
        .group_by("match_id", "account_id")
        .agg(early_deaths=pl.len().cast(pl.Int64))
    )

    own = (
        sides.select("match_id", pl.col("my_account").alias("account_id"))
        .join(early, on=["match_id", "account_id"], how="left")
        .select("match_id", my_early=pl.col("early_deaths").fill_null(0))
    )

    mates = (
        lobby.join(sides, on="match_id")
        .filter(
            pl.col("team") == pl.col("my_team"),
            pl.col("account_id") != pl.col("my_account"),
        )
        .join(early, on=["match_id", "account_id"], how="left")
        .group_by("match_id")
        .agg(
            worst_early=pl.col("early_deaths").fill_null(0).max(),
            ally_left=pl.col("abandon_time_s").is_not_null().any(),
        )
    )

    return (
        mine.select("match_id", "day", "won", "lane")
        .join(lanes, on="match_id")
        .join(own, on="match_id")
        .join(mates, on="match_id", how="left")
        .with_columns(
            pl.col("worst_early").fill_null(0),
            pl.col("ally_left").fill_null(value=False),
        )
        .sort("match_id")
        .collect()
    )
