"""Per game splits and per source totals for the archive commands."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from deadlock_matches import config
from deadlock_matches.assets import heroes, items
from deadlock_matches.queries.core import _resolved_accounts, my_games, scan, table_exists
from deadlock_matches.queries.delivery import hero_damage
from deadlock_matches.queries.items import _item_windows, item_events_effective
from deadlock_matches.queries.stats import _final_custom_values

if TYPE_CHECKING:
    from collections.abc import Sequence


def damage_by_source(
    hero: str,
    accounts: Sequence[int] | None = None,
    matches: Sequence[int] | None = None,
    parquet_dir: str | Path | None = None,
    stat: str = "damage",
) -> pl.DataFrame:
    """Total damage to heroes by source across every game of a hero.

    - one row per source (gun, ability, item proc), summed over every game
    - per_min divides a row by the combined minutes of the games where the
      source appeared
    - per_min_owned divides item rows by the minutes the item was owned
    - per_1k divides item rows by every 1,000 souls of effective cost put
      into the item
    - gun and ability rows keep a null per_min_owned and per_1k, and so does
      an item source with no buy on record
    - matches limits the rows to specific match ids
    - stat swaps the figure like hero_damage: damage, healing, mitigated, ...
    """
    accounts = config.config_accounts() if accounts is None else list(accounts)

    if not accounts:
        msg = "no accounts: pass accounts= or fill in accounts in config.toml"
        raise ValueError(msg)

    predicate = (pl.col("hero") == hero) & pl.col("dealer_account_id").is_in(accounts)

    if matches is not None:
        predicate = predicate & pl.col("match_id").is_in(list(matches))

    rows = (
        hero_damage(stat=stat, parquet_dir=parquet_dir)
        .filter(predicate)
        .select("match_id", "source_name", "source_class", "delivery", "damage")
        .collect()
    )

    if rows.is_empty():
        msg = f"no {stat} rows for {hero} on accounts {accounts}"
        raise ValueError(msg)

    if matches is not None:
        match_ids = pl.Series("match_id", matches, dtype=pl.Int64).unique()

    else:
        match_ids = rows.get_column("match_id").unique()

    durations = (
        scan("matches", parquet_dir)
        .filter(pl.col("match_id").is_in(match_ids.implode()))
        .select("match_id", "duration_s")
        .collect()
    )
    source_minutes = (
        rows.select("source_name", "source_class", "delivery", "match_id")
        .unique()
        .join(durations, on="match_id")
        .group_by("source_name", "source_class", "delivery")
        .agg((pl.col("duration_s").sum() / 60).alias("minutes"))
    )
    grand = rows.get_column("damage").sum()
    ids = _proc_item_ids(rows)
    owned = _owned_minutes(ids, accounts, match_ids, parquet_dir)
    owned_min = (
        pl.col("source_class").replace_strict(owned, default=None, return_dtype=pl.Float64)
        if owned
        else pl.lit(None, dtype=pl.Float64)
    )
    outlay = _effective_outlay(ids, accounts, match_ids, parquet_dir)
    outlay_souls = (
        pl.col("source_class").replace_strict(outlay, default=None, return_dtype=pl.Float64)
        if outlay
        else pl.lit(None, dtype=pl.Float64)
    )
    item_row = pl.col("delivery").str.ends_with("_proc")

    return (
        rows.group_by("source_name", "source_class", "delivery")
        .agg(
            pl.col("damage").sum().alias("total"),
            pl.col("match_id").n_unique().alias("games"),
        )
        .join(source_minutes, on=["source_name", "source_class", "delivery"])
        .with_columns(
            (pl.col("total") / pl.col("minutes")).round(1).alias("per_min"),
            pl.when(item_row)
            .then((pl.col("total") / owned_min).round(1))
            .otherwise(pl.lit(None, dtype=pl.Float64))
            .alias("per_min_owned"),
            pl.when(item_row)
            .then((pl.col("total") / outlay_souls * 1000).round(1))
            .otherwise(pl.lit(None, dtype=pl.Float64))
            .alias("per_1k"),
            (pl.col("total") / grand * 100).round(1).alias("percent"),
        )
        .select(
            "games",
            "source_name",
            "delivery",
            "total",
            "per_min",
            "per_min_owned",
            "per_1k",
            "percent",
        )
        .sort("total", descending=True)
    )


def _proc_item_ids(rows: pl.DataFrame) -> dict[int, str]:
    """Map item ids to the proc source classes present in rows.

    - a source class resolving to no known item is left out
    """
    classes = (
        rows.select("delivery", "source_class")
        .filter(pl.col("delivery").str.ends_with("_proc"))
        .get_column("source_class")
        .unique()
        .to_list()
    )
    ids = {}

    for source_class in classes:
        item = items.item_by_class_name(source_class)

        if item is not None:
            ids[item.id] = source_class

    return ids


def _owned_minutes(
    ids: dict[int, str],
    accounts: Sequence[int],
    match_ids: pl.Series,
    parquet_dir: str | Path | None,
) -> dict[str, float]:
    """Sum the minutes each item damage source was owned across the given games.

    - keyed by source_class, only the item proc sources in ids appear
    - ownership windows come from the buys, like the item command: a sold or
      consumed buy ends at sold_time_s, a kept buy at the end of the match
    """
    if not ids:
        return {}

    windows = (
        _item_windows(
            pl.col("item_id").is_in(list(ids))
            & pl.col("match_id").is_in(match_ids.implode())
            & pl.col("account_id").is_in(accounts),
            parquet_dir,
        )
        .group_by("item_id")
        .agg(((pl.col("end_s") - pl.col("game_time_s")).sum() / 60).alias("minutes"))
        .filter(pl.col("minutes") > 0)
        .collect()
    )

    return {ids[item_id]: minutes for item_id, minutes in windows.iter_rows()}


def _effective_outlay(
    ids: dict[int, str],
    accounts: Sequence[int],
    match_ids: pl.Series,
    parquet_dir: str | Path | None,
) -> dict[str, float]:
    """Sum the effective souls put into each item damage source across the given games.

    - keyed by source_class, only the item proc sources in ids appear
    - empty when the versioned asset tables are missing
    """
    priced = table_exists("item_history", parquet_dir) and table_exists(
        "item_component_history", parquet_dir
    )

    if not ids or not priced:
        return {}

    outlay = (
        item_events_effective(parquet_dir)
        .filter(
            pl.col("item_id").is_in(list(ids)),
            pl.col("match_id").is_in(match_ids.implode()),
            pl.col("account_id").is_in(list(accounts)),
        )
        .group_by("item_id")
        .agg(pl.col("effective_cost").sum().alias("souls"))
        .filter(pl.col("souls") > 0)
        .collect()
    )

    return {ids[item_id]: souls for item_id, souls in outlay.iter_rows()}


def _hero_game_rows(
    hero: str,
    accounts: Sequence[int],
    parquet_dir: str | Path | None,
    tz: str | None,
    days: int | None,
    since: str | dt.date | None,
) -> pl.LazyFrame:
    """Take one row per game of a hero inside the day window, lazily.

    - day, result, K/D/A, and duration ride along for the per game tables
    - days and since filter on the local day, like lane_records
    """
    hero_id = heroes.hero_id_by_name(hero)

    if hero_id is None:
        msg = f"Unknown hero {hero!r}"
        raise ValueError(msg)

    mine = my_games(parquet_dir, accounts, tz).filter(pl.col("hero_id") == hero_id)

    if since is not None:
        since = dt.date.fromisoformat(since) if isinstance(since, str) else since
        mine = mine.filter(pl.col("day") >= since)

    if days is not None:
        mine = mine.filter(pl.col("day").rank("dense", descending=True) <= days)

    return mine.select(
        "match_id",
        "account_id",
        "hero",
        "day",
        "start_local",
        "won",
        "kills",
        "deaths",
        "assists",
        "duration_s",
    )


def _collect_game_records(games: pl.LazyFrame, hero: str, accounts: Sequence[int]) -> pl.DataFrame:
    """Sort a game records frame by start time and refuse an empty window."""
    df = games.sort("start_local", "match_id").collect()

    if df.is_empty():
        msg = f"no games of {hero} on accounts {accounts}"
        raise ValueError(msg)

    return df


def _game_split_records(
    hero: str,
    split: pl.LazyFrame,
    parts: Sequence[str],
    accounts: Sequence[int],
    parquet_dir: str | Path | None,
    tz: str | None,
    days: int | None,
    since: str | dt.date | None,
    extras: Sequence[str] = (),
) -> pl.DataFrame:
    """Join a per-game split onto one row per game of a hero.

    - one row per game with day, result, K/D/A, and duration
    - each part fills to 0 and gets its percent of total in a _pct column,
      null in a game with no detail rows
    - extras fill to 0 too but get no share of total
    - days and since filter on the local day
    - accounts must arrive already resolved to ids
    """
    mine = _hero_game_rows(hero, accounts, parquet_dir, tz, days, since)

    games = (
        mine.join(split, on=["match_id", "account_id"], how="left")
        .with_columns(pl.col("total", *parts, *extras).fill_null(0))
        .with_columns(
            pl.when(pl.col("total") > 0)
            .then((pl.col(part) / pl.col("total") * 100).round(1))
            .alias(f"{part}_pct")
            for part in parts
        )
    )

    return _collect_game_records(games, hero, accounts)


def damage_game_records(
    hero: str,
    accounts: Sequence[int] | None = None,
    parquet_dir: str | Path | None = None,
    tz: str | None = None,
    days: int | None = None,
    since: str | dt.date | None = None,
) -> pl.DataFrame:
    """Take one row per game of a hero with the damage to heroes split by delivery.

    - total sums every detail row and gun / abilities / items sum the
      matching delivery rows
    - items counts gun and spirit procs together
    - gun_pct, abilities_pct, and items_pct are percents of total and go
      null in a game with no hero damage
    - days and since filter on the local day
    """
    accounts = _resolved_accounts(accounts)
    split = (
        hero_damage(parquet_dir=parquet_dir, tz=tz)
        .filter(pl.col("dealer_account_id").is_in(accounts))
        .select("match_id", pl.col("dealer_account_id").alias("account_id"), "delivery", "damage")
        .group_by("match_id", "account_id")
        .agg(
            pl.col("damage").sum().alias("total"),
            pl.col("damage").filter(pl.col("delivery") == "gun").sum().alias("gun"),
            pl.col("damage").filter(pl.col("delivery") == "ability").sum().alias("abilities"),
            pl.col("damage").filter(pl.col("delivery").str.ends_with("_proc")).sum().alias("items"),
        )
    )

    return _game_split_records(
        hero, split, ("gun", "abilities", "items"), accounts, parquet_dir, tz, days, since
    )


def healing_game_records(
    hero: str,
    accounts: Sequence[int] | None = None,
    parquet_dir: str | Path | None = None,
    tz: str | None = None,
    days: int | None = None,
    since: str | dt.date | None = None,
) -> pl.DataFrame:
    """Take one row per game of a hero with the healing split by delivery and recipient.

    - total sums every healing detail row and abilities / items sum the
      matching delivery rows
    - self keeps the healing that landed on the healer
    - abilities_pct, items_pct, and self_pct are percents of total and go
      null in a game with no healing
    - prevented sums the enemy healing denied and fills to 0 in a game
      without any
    - days and since filter on the local day
    """
    accounts = _resolved_accounts(accounts)
    split = (
        hero_damage(stat="healing", parquet_dir=parquet_dir, tz=tz)
        .filter(pl.col("dealer_account_id").is_in(accounts))
        .select(
            "match_id",
            pl.col("dealer_account_id").alias("account_id"),
            "target_account_id",
            "delivery",
            "damage",
        )
        .with_columns((pl.col("target_account_id") == pl.col("account_id")).alias("to_self"))
        .group_by("match_id", "account_id")
        .agg(
            pl.col("damage").sum().alias("total"),
            pl.col("damage").filter(pl.col("delivery") == "ability").sum().alias("abilities"),
            pl.col("damage").filter(pl.col("delivery").str.ends_with("_proc")).sum().alias("items"),
            pl.col("damage").filter(pl.col("to_self")).sum().alias("self"),
        )
    )

    prevented = (
        hero_damage(stat="heal_prevented", parquet_dir=parquet_dir, tz=tz)
        .filter(pl.col("dealer_account_id").is_in(accounts))
        .select("match_id", pl.col("dealer_account_id").alias("account_id"), "damage")
        .group_by("match_id", "account_id")
        .agg(pl.col("damage").sum().alias("prevented"))
    )
    split = split.join(prevented, on=["match_id", "account_id"], how="full", coalesce=True)

    return _game_split_records(
        hero,
        split,
        ("abilities", "items", "self"),
        accounts,
        parquet_dir,
        tz,
        days,
        since,
        extras=("prevented",),
    )


def souls_by_source(
    hero: str,
    accounts: Sequence[int] | None = None,
    matches: Sequence[int] | None = None,
    parquet_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Total souls by income source across every game of a hero.

    - souls sums the guaranteed and orb portions and matches the in game
      figure
    - orb_share is the deniable orb portion the player secured and percent
      is the share of the total
    - games counts only the games where the source paid souls (the tables
      hold a zero row for every source in every game)
    - minutes is the combined length of the games where the source paid
    - matches limits the rows to specific match ids
    """
    accounts = config.config_accounts() if accounts is None else list(accounts)

    if not accounts:
        msg = "no accounts: pass accounts= or fill in accounts in config.toml"
        raise ValueError(msg)

    hero_games = (
        scan("players", parquet_dir)
        .filter(pl.col("hero") == hero, pl.col("account_id").is_in(accounts))
        .select("match_id", "account_id")
    )

    if matches is not None:
        hero_games = hero_games.filter(pl.col("match_id").is_in(list(matches)))

    finals = (
        scan("soul_sources", parquet_dir)
        .join(hero_games, on=["match_id", "account_id"])
        .group_by("match_id", "account_id", "source_name")
        .agg(pl.col("souls").max(), pl.col("souls_orbs").max())
        .filter(pl.col("souls") + pl.col("souls_orbs") != 0)
        .collect()
    )

    if finals.is_empty():
        msg = f"no soul_sources rows for {hero} on accounts {accounts}"
        raise ValueError(msg)

    total = int((finals.get_column("souls") + finals.get_column("souls_orbs")).sum())
    durations = (
        scan("matches", parquet_dir)
        .filter(pl.col("match_id").is_in(finals.get_column("match_id").unique().implode()))
        .select("match_id", "duration_s")
        .collect()
    )
    source_minutes = (
        finals.select("source_name", "match_id")
        .unique()
        .join(durations, on="match_id")
        .group_by("source_name")
        .agg((pl.col("duration_s").sum() / 60).alias("minutes"))
    )

    return (
        finals.group_by("source_name")
        .agg(
            (pl.col("souls") + pl.col("souls_orbs")).sum().alias("souls"),
            pl.col("souls_orbs").sum().alias("secured_orbs"),
            pl.len().alias("games"),
        )
        .join(source_minutes, on="source_name")
        .with_columns(
            (pl.col("souls") / total * 100).round(1).alias("percent"),
            (pl.col("secured_orbs") / pl.col("souls") * 100).round(1).alias("orb_share"),
        )
        .select("games", "source_name", "souls", "secured_orbs", "minutes", "percent", "orb_share")
        .sort("souls", descending=True)
    )


SOUL_GROUP_COLUMNS = {
    "troopers": "waves",
    "denies": "waves",
    "jungle": "roaming",
    "breakables": "roaming",
    "players": "combat",
    "assists": "combat",
    "bosses": "objectives",
    "treasure": "objectives",
}


def souls_game_records(
    hero: str,
    accounts: Sequence[int] | None = None,
    parquet_dir: str | Path | None = None,
    tz: str | None = None,
    days: int | None = None,
    since: str | dt.date | None = None,
) -> pl.DataFrame:
    """Take one row per game of a hero with the souls split into source groups.

    - total is gross souls with the orb portions included and matches the
      in game figure
    - waves / roaming / combat / objectives sum the matching sources while
      the catch up and rare sources only count toward total
    - waves_pct, roaming_pct, combat_pct, and objectives_pct are percents
      of total and go null in a game with no soul snapshots
    - days and since filter on the local day
    """
    accounts = _resolved_accounts(accounts)
    finals = (
        scan("soul_sources", parquet_dir)
        .filter(pl.col("account_id").is_in(accounts))
        .group_by("match_id", "account_id", "source_name")
        .agg((pl.col("souls") + pl.col("souls_orbs")).max().alias("souls"))
        .with_columns(
            pl.col("source_name")
            .replace_strict(SOUL_GROUP_COLUMNS, default=None, return_dtype=pl.String)
            .alias("group")
        )
    )

    split = finals.group_by("match_id", "account_id").agg(
        pl.col("souls").sum().alias("total"),
        *[
            pl.col("souls").filter(pl.col("group") == group).sum().alias(group)
            for group in ("waves", "roaming", "combat", "objectives")
        ],
    )

    return _game_split_records(
        hero,
        split,
        ("waves", "roaming", "combat", "objectives"),
        accounts,
        parquet_dir,
        tz,
        days,
        since,
    )


COMBAT_COUNTERS = (
    ("Enemy Hero Accuracy", "Shots", "shots"),
    ("Enemy Hero Accuracy", "Hits", "hits"),
    ("Enemy Hero Accuracy", "Headshots", "headshots"),
    (None, "Parry Success", "parries"),
    (None, "Parry Miss", "missed_parries"),
)


def combat_game_records(
    hero: str,
    accounts: Sequence[int] | None = None,
    parquet_dir: str | Path | None = None,
    tz: str | None = None,
    days: int | None = None,
    since: str | dt.date | None = None,
) -> pl.DataFrame:
    """Take one row per game of a hero with the aim and parry counters.

    - shots, hits, and headshots count fire at enemy heroes only
    - hit_pct is hits over shots and headshot_pct is headshots over hits,
      with both null in a game with no tracked shots
    - parries and missed_parries read the final parry counters with
      Counterspell auto parries included
    - days and since filter on the local day
    """
    accounts = _resolved_accounts(accounts)
    mine = _hero_game_rows(hero, accounts, parquet_dir, tz, days, since)
    finals = _final_custom_values(
        scan("custom_stats", parquet_dir)
        .filter(pl.col("account_id").is_in(accounts))
        .join(mine.select("match_id", "account_id"), on=["match_id", "account_id"], how="semi")
    )

    split = finals.group_by("match_id", "account_id").agg(
        *[
            pl.col("value")
            .filter(
                pl.col("group").is_null() if group is None else pl.col("group") == group,
                pl.col("stat") == stat,
            )
            .sum()
            .cast(pl.Int64)
            .alias(name)
            for group, stat, name in COMBAT_COUNTERS
        ]
    )

    counters = [name for _, _, name in COMBAT_COUNTERS]
    games = (
        mine.join(split, on=["match_id", "account_id"], how="left")
        .with_columns(pl.col(*counters).fill_null(0))
        .with_columns(
            pl.when(pl.col("shots") > 0)
            .then((pl.col("hits") / pl.col("shots") * 100).round(1))
            .alias("hit_pct"),
            pl.when(pl.col("hits") > 0)
            .then((pl.col("headshots") / pl.col("hits") * 100).round(1))
            .alias("headshot_pct"),
        )
    )

    return _collect_game_records(games, hero, accounts)
