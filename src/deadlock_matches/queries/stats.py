"""Final snapshots, hidden stat counters, melee, and death context."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import polars.selectors as cs

from deadlock_matches.assets import heroes
from deadlock_matches.queries.core import _local_day, my_games, scan, table_exists
from deadlock_matches.queries.delivery import damage_category

if TYPE_CHECKING:
    from collections.abc import Sequence


def _final_custom_values(frame: pl.LazyFrame) -> pl.LazyFrame:
    """Keep the last snapshot value of every custom stat."""
    return frame.group_by("match_id", "account_id", "group", "stat").agg(
        pl.col("value").sort_by("time_stamp_s").last()
    )


def custom_stat_totals(
    accounts: Sequence[int],
    matches: Sequence[int],
    parquet_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Sum and average the final custom stat values across the given games.

    - one row per group and stat with the window total and the per game mean
    - reads the custom_stats table alone, no hero or day joins
    """
    finals = _final_custom_values(
        scan("custom_stats", parquet_dir).filter(
            pl.col("account_id").is_in(list(accounts)),
            pl.col("match_id").is_in(list(matches)),
        )
    )

    return (
        finals.group_by("group", "stat")
        .agg(pl.col("value").sum().alias("total"), pl.col("value").mean().alias("avg"))
        .collect()
    )


def custom_stats(
    stat: str | None = None,
    group: str | None = None,
    accounts: Sequence[int] | None = None,
    matches: Sequence[int] | None = None,
    *,
    final: bool = True,
    parquet_dir: str | Path | None = None,
    tz: str | None = None,
) -> pl.LazyFrame:
    """Read the stat counters the game tracks but never shows, with hero/won and local day joined on.

    - snapshot rows like the stats table, final=True (the default) keeps one
      row per stat with the last snapshot value
    - stat and group filter by name, accounts and matches narrow the rows
    - values are cumulative counts except the Bullet Stats group, which holds
      percents re-computed each snapshot, so never diff those
    """
    frame = scan("custom_stats", parquet_dir)

    if stat is not None:
        frame = frame.filter(pl.col("stat") == stat)

    if group is not None:
        frame = frame.filter(pl.col("group") == group)

    if accounts is not None:
        frame = frame.filter(pl.col("account_id").is_in(list(accounts)))

    if matches is not None:
        frame = frame.filter(pl.col("match_id").is_in(list(matches)))

    if final:
        frame = _final_custom_values(frame)

    frame = frame.join(
        scan("players", parquet_dir).select("match_id", "account_id", "hero", "won"),
        on=["match_id", "account_id"],
        how="left",
    )

    return _local_day(frame, parquet_dir, tz)


def aim_rates(
    hero: str | None = None,
    accounts: Sequence[int] | None = None,
    min_shots: int = 100,
    min_games: int = 50,
    parquet_dir: str | Path | None = None,
    tz: str | None = None,
) -> pl.DataFrame:
    """Rank each game of a hero by aim against heroes, as percentiles across the archive.

    - hit_percentile and headshot_percentile rank within the hero, 99 = top 1 percent
    - percentiles rank the whole archive before the accounts filter applies
    - min_shots drops low-volume games
    - percentiles are null until the archive holds min_games of the hero, a
      small archive ranks against too few games to mean anything (hero_games
      carries the population)
    """
    lf = custom_stats(group="Enemy Hero Accuracy", parquet_dir=parquet_dir, tz=tz).select(
        "match_id", "account_id", "hero", "won", "day", "stat", "value"
    )

    if hero is not None:
        lf = lf.filter(pl.col("hero") == hero)

    frame = (
        lf.collect()
        .pivot(on="stat", index=["match_id", "account_id", "hero", "won", "day"], values="value")
        .fill_null(0)
        .filter(pl.col("Shots") >= min_shots)
    )

    frame = (
        frame.with_columns(
            hit_rate=(100 * pl.col("Hits") / pl.col("Shots")),
            headshot_rate=(100 * pl.col("Headshots") / pl.col("Hits").clip(1)),
            hero_games=pl.len().over("hero"),
        )
        .with_columns(
            hit_percentile=(pl.col("hit_rate").rank() / pl.len() * 100).over("hero").round(0),
            headshot_percentile=(pl.col("headshot_rate").rank() / pl.len() * 100)
            .over("hero")
            .round(0),
        )
        .with_columns(
            pl.when(pl.col("hero_games") >= min_games)
            .then(pl.col("hit_percentile"))
            .alias("hit_percentile"),
            pl.when(pl.col("hero_games") >= min_games)
            .then(pl.col("headshot_percentile"))
            .alias("headshot_percentile"),
        )
    )

    if accounts is not None:
        frame = frame.filter(pl.col("account_id").is_in(list(accounts)))

    return frame


def _basic_melee() -> pl.Expr:
    """Match the bare light and heavy melee swing the game reports as Melee."""
    return pl.col("source_class").str.contains("ability_melee_")


def melee_by_player(match_id: int, parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Sum melee dealt and taken between heroes and count parries for every player in a match.

    - melee is the bare light and heavy swing the game reports as Melee
    - empower items, procs, and melee abilities stay out
    - dealt and taken count only hero targets and skip trooper farming
    - parries and missed_parries read the final parry snapshot
    """
    players = (
        scan("players", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("match_id", "account_id", "hero", "team")
    )

    melee = (
        scan("damage", parquet_dir)
        .filter(
            pl.col("match_id") == match_id,
            pl.col("stat") == "damage",
            damage_category() != "total",
            pl.col("target_account_id").is_not_null(),
            _basic_melee(),
        )
        .select("dealer_account_id", "target_account_id", "damage")
    )

    dealt = (
        melee.group_by("dealer_account_id")
        .agg(pl.col("damage").sum().alias("melee_dealt"))
        .rename({"dealer_account_id": "account_id"})
    )

    taken = (
        melee.group_by("target_account_id")
        .agg(pl.col("damage").sum().alias("melee_taken"))
        .rename({"target_account_id": "account_id"})
    )

    parries = (
        scan("custom_stats", parquet_dir)
        .filter(
            pl.col("match_id") == match_id,
            pl.col("stat").is_in(["Parry Success", "Parry Miss"]),
        )
        .group_by("account_id", "stat")
        .agg(pl.col("value").sort_by("time_stamp_s").last())
        .group_by("account_id")
        .agg(
            pl.col("value").filter(pl.col("stat") == "Parry Success").sum().alias("parries"),
            pl.col("value").filter(pl.col("stat") == "Parry Miss").sum().alias("missed_parries"),
        )
    )

    return (
        players.join(dealt, on="account_id", how="left")
        .join(taken, on="account_id", how="left")
        .join(parries, on="account_id", how="left")
        .with_columns(cs.exclude("match_id", "account_id", "hero", "team").fill_null(0))
    )


def melee_taken_by_attacker(
    match_id: int, account_id: int, parquet_dir: str | Path | None = None
) -> pl.LazyFrame:
    """Total the melee one player took per attacking hero."""
    attackers = (
        scan("players", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select(pl.col("account_id").alias("dealer_account_id"), pl.col("hero").alias("attacker"))
    )

    return (
        scan("damage", parquet_dir)
        .filter(
            pl.col("match_id") == match_id,
            pl.col("target_account_id") == account_id,
            pl.col("stat") == "damage",
            damage_category() != "total",
            _basic_melee(),
        )
        .group_by("dealer_account_id")
        .agg(pl.col("damage").sum().alias("melee"))
        .join(attackers, on="dealer_account_id", how="left")
        .select("attacker", "melee")
        .sort("melee", descending=True)
    )


def final_stats(parquet_dir: str | Path | None = None, tz: str | None = None) -> pl.LazyFrame:
    """Final snapshot values for each player in each match, with hero/won, local day, and gun rates.

    Snapshot columns are cumulative, so max() per match is the final value.
    accuracy and headshot_rate are null when nothing was fired.
    """
    shots = pl.col("shots_hit") + pl.col("shots_missed")
    bullets = pl.col("hero_bullets_hit") + pl.col("hero_bullets_hit_crit")

    finals = (
        scan("stats", parquet_dir)
        .group_by("match_id", "account_id")
        .agg(cs.exclude("match_id", "account_id").max())
        .with_columns(
            pl.when(shots > 0).then(pl.col("shots_hit") / shots).alias("accuracy"),
            pl.when(bullets > 0)
            .then(pl.col("hero_bullets_hit_crit") / bullets)
            .alias("headshot_rate"),
        )
        .join(
            scan("players", parquet_dir).select("match_id", "account_id", "hero_id", "hero", "won"),
            on=["match_id", "account_id"],
        )
    )

    return _local_day(finals, parquet_dir, tz)


def team_damage_ranks(parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Rank players by hero damage within their team, one row per match player.

    - player_damage is the final snapshot value
    - rank 1 is the team damage chart top, flagged by top_team_damage
    """
    finals = final_stats(parquet_dir).select("match_id", "account_id", "player_damage")
    teams = scan("players", parquet_dir).select("match_id", "account_id", "team")

    return (
        finals.join(teams, on=["match_id", "account_id"])
        .with_columns(
            pl.col("player_damage")
            .rank("ordinal", descending=True)
            .over("match_id", "team")
            .alias("team_damage_rank")
        )
        .with_columns((pl.col("team_damage_rank") == 1).alias("top_team_damage"))
    )


def my_deaths(
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    tz: str | None = None,
) -> pl.LazyFrame:
    """Deaths for the player with hero, won, duration, and local day joined in."""
    games = my_games(parquet_dir, accounts, tz).select(
        "match_id", "account_id", "hero", "hero_id", "won", "day", "duration_s"
    )

    return scan("deaths", parquet_dir).join(games, on=["match_id", "account_id"])


def death_context(
    radius: float = 2000.0,
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    tz: str | None = None,
) -> pl.LazyFrame:
    """my_deaths plus counts of nearby allies and enemies, with solo and outnumbered flags.

    - needs the movement table for player positions (excluded by default)
    """
    if not table_exists("movement", parquet_dir):
        msg = 'movement table not exported: remove "movement" from the exclude list in config.toml and run `deadlock sync`'
        raise ValueError(msg)

    deaths = my_deaths(parquet_dir, accounts, tz)
    teams = scan("players", parquet_dir).select("match_id", "account_id", "team")

    mine = deaths.select("match_id", "account_id", "game_time_s", "x", "y").join(
        teams, on=["match_id", "account_id"]
    )
    others = (
        scan("movement", parquet_dir)
        .select(
            "match_id",
            "game_time_s",
            other_id=pl.col("account_id"),
            other_x=pl.col("x"),
            other_y=pl.col("y"),
        )
        .join(
            teams.select("match_id", other_id=pl.col("account_id"), other_team=pl.col("team")),
            on=["match_id", "other_id"],
        )
    )

    near = (
        mine.join(others, on=["match_id", "game_time_s"])
        .filter(pl.col("other_id") != pl.col("account_id"))
        .with_columns(
            ((pl.col("x") - pl.col("other_x")) ** 2 + (pl.col("y") - pl.col("other_y")) ** 2)
            .sqrt()
            .alias("dist")
        )
        .filter(pl.col("dist") <= radius)
        .group_by("match_id", "account_id", "game_time_s")
        .agg(
            (pl.col("other_team") == pl.col("team")).sum().alias("allies"),
            (pl.col("other_team") != pl.col("team")).sum().alias("enemies"),
        )
    )

    return (
        deaths.join(near, on=["match_id", "account_id", "game_time_s"], how="left")
        .with_columns(pl.col("allies", "enemies").fill_null(0))
        .with_columns(
            (pl.col("allies") == 0).alias("solo"),
            (pl.col("enemies") > pl.col("allies") + 1).alias("outnumbered"),
        )
    )


def hero_games(
    hero: str,
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    since: dt.date | None = None,
) -> pl.LazyFrame:
    """List your ranked games on one hero as match and account pairs.

    - only ranked games count, matching the downloaded pool
    - since keeps games from that local day onward
    """
    hero_id = heroes.hero_id_by_name(hero)

    if hero_id is None:
        msg = f"Unknown hero {hero!r}"
        raise ValueError(msg)

    games = my_games(parquet_dir, accounts).filter(
        pl.col("hero_id") == hero_id, pl.col("match_mode") == 1
    )

    if since is not None:
        games = games.filter(pl.col("day") >= since)

    return games.select("match_id", "account_id").unique()
