"""Per game splits and per source totals for the archive commands."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from deadlock_matches.assets import heroes, items
from deadlock_matches.queries.core import (
    _resolved_accounts,
    my_games,
    scan,
    table_exists,
)
from deadlock_matches.queries.delivery import hero_damage
from deadlock_matches.queries.items import _item_windows, item_events_effective
from deadlock_matches.queries.labels import hero_name, stack_class_name, stack_name
from deadlock_matches.queries.semantic import (
    Dimension,
    Join,
    Measure,
    MetricView,
    summarize,
    try_divide,
    view,
    view_frame,
)
from deadlock_matches.queries.stats import _final_custom_values

if TYPE_CHECKING:
    from collections.abc import Sequence


STACK_GAME_DIMENSIONS = {
    "match_id": Dimension(pl.col("match_id")),
    "account_id": Dimension(pl.col("account_id")),
    "hero": Dimension(hero_name("players.hero_id")),
    "team": Dimension(pl.col("players.team")),
    "ability_id": Dimension(pl.col("ability_id")),
    "class_name": Dimension(stack_class_name()),
    "name": Dimension(stack_name()),
}

STACK_GAME_MEASURES = {
    "total": Measure(
        pl.col("value").sum(),
        "count",
        comment="Sum of final counters; the counter meaning depends on the ability or item.",
    ),
    "games": Measure(
        pl.col("match_id").n_unique(),
        "count",
        comment="Distinct matches that recorded the counter.",
    ),
    "mean": Measure(
        pl.col("value").mean(),
        "ratio",
        comment="Mean final counter per player-game in the group.",
    ),
    "max": Measure(
        pl.col("value").max(),
        "count",
        comment="Best single player-game in the group.",
    ),
}


@view(
    grain=("match_id", "account_id", "ability_id"),
    dimensions=STACK_GAME_DIMENSIONS,
    measures=STACK_GAME_MEASURES,
)
def stack_games(accounts: Sequence[int] | None = None) -> MetricView:
    """One row per final stack counter, player, and match."""
    return MetricView(
        source="stacks",
        joins=(Join("players", using=("match_id", "account_id")),),
        filter=None if accounts is None else pl.col("account_id").is_in(list(accounts)),
    )


BUFF_GAME_DIMENSIONS = {
    "match_id": Dimension(pl.col("match_id")),
    "account_id": Dimension(pl.col("account_id")),
    "hero": Dimension(hero_name("players.hero_id")),
    "team": Dimension(pl.col("players.team")),
    "type": Dimension(pl.col("type"), comment="Pickup class name, one per family and level."),
    "buff": Dimension(pl.col("buff"), comment="Buff family such as ammo, cd, spirit, or wp."),
    "level": Dimension(pl.col("level")),
}

BUFF_GAME_MEASURES = {
    "held": Measure(
        pl.col("count").filter(pl.col("permanent")).sum(),
        "count",
        comment="Permanent buffs the player finished with, whatever they were picked up from.",
    ),
    "bridge": Measure(
        pl.col("count").filter(~pl.col("permanent")).sum(),
        "count",
        comment="Temporary bridge buffs claimed.",
    ),
    "games": Measure(
        pl.col("match_id").n_unique(),
        "count",
        comment="Distinct matches that recorded a buff in the group.",
    ),
}


@view(
    grain=("match_id", "account_id", "type"),
    dimensions=BUFF_GAME_DIMENSIONS,
    measures=BUFF_GAME_MEASURES,
)
def buff_games(
    accounts: Sequence[int] | None = None,
    matches: Sequence[int] | None = None,
) -> MetricView:
    """One row per buff family, level, and player of a match.

    - counts carry no timestamps, so there is no per-interval split
    - accounts left out keeps every player, which is what a whole-lobby table
      wants. It does not fall back to config.toml
    """
    predicate = pl.lit(value=True)

    if accounts is not None:
        predicate &= pl.col("account_id").is_in(list(accounts))

    if matches is not None:
        predicate &= pl.col("match_id").is_in(list(matches))

    return MetricView(
        source="buffs",
        joins=(Join("players", using=("match_id", "account_id")),),
        filter=predicate,
    )


def _resolved_hero_name(hero: str) -> str:
    """Resolve a fuzzy hero name to the canonical display name."""
    hero_id = heroes.hero_id_by_name(hero)

    if hero_id is None:
        msg = f"Unknown hero {hero!r}"
        raise ValueError(msg)

    return heroes.hero_name(hero_id)


HERO_DAMAGE_DIMENSIONS = {
    "match_id": Dimension(pl.col("match_id")),
    "account_id": Dimension(
        pl.col("dealer_account_id"),
        comment="The player who dealt it.",
        synonyms=("dealer_account_id",),
    ),
    "target_account_id": Dimension(
        pl.col("target_account_id"),
        comment="The hero on the receiving end.",
    ),
    "hero": Dimension(pl.col("hero"), comment="Hero the dealer played."),
    "day": Dimension(pl.col("day"), comment="Local date, not the UTC date."),
    "week": Dimension(pl.col("start_local").dt.strftime("%G-W%V")),
    "month": Dimension(pl.col("start_local").dt.strftime("%Y-%m")),
    "source_name": Dimension(pl.col("source_name")),
    "source_class": Dimension(pl.col("source_class")),
    "category": Dimension(
        pl.col("category"),
        comment="Gun, item, or ability, read off the source class name.",
    ),
    "delivery": Dimension(
        pl.col("delivery"),
        comment="Gun, ability, gun-triggered item proc, or spirit-triggered item proc.",
    ),
}

_DAMAGE = pl.col("damage")
_BULLET = pl.col("category") == "gun"
_HEADSHOT = pl.col("source_class").str.ends_with("_crit")

HERO_DAMAGE_MEASURES = {
    "total": Measure(
        _DAMAGE.sum(),
        "count",
        comment="Selected stat summed over detail rows.",
        direction="maximize",
    ),
    "games": Measure(
        pl.col("match_id").n_unique(),
        "count",
        comment="Distinct matches with a detail row in the group.",
    ),
    "targets": Measure(
        pl.col("target_account_id").n_unique(),
        "count",
        comment="Distinct enemy heroes the group landed on.",
    ),
    "per_game": Measure(
        lambda measure: try_divide(measure["total"], measure["games"]),
        "ratio",
        comment="Selected stat per match where the group appeared.",
        direction="maximize",
    ),
    "gun": Measure(
        _DAMAGE.filter(_BULLET).sum(),
        "count",
        comment="Body shots and headshots together.",
        direction="maximize",
    ),
    "gun_body": Measure(
        _DAMAGE.filter(_BULLET & ~_HEADSHOT).sum(),
        "count",
        comment="Bullet damage from shots that were not headshots.",
        direction="maximize",
    ),
    "gun_headshot": Measure(
        _DAMAGE.filter(_BULLET & _HEADSHOT).sum(),
        "count",
        comment="Bullet damage from the _crit sources. gun_body holds the rest.",
        direction="maximize",
    ),
}


@view(
    grain=("match_id", "account_id", "target_account_id", "source_class"),
    dimensions=HERO_DAMAGE_DIMENSIONS,
    measures=HERO_DAMAGE_MEASURES,
)
def hero_damage_games(
    accounts: Sequence[int] | None = None,
    matches: Sequence[int] | None = None,
    stat: str = "damage",
    tz: str | None = None,
) -> MetricView:
    """One row per dealer, target, and damage source of a match.

    - the screen total rows, non-hero targets, and zero rows are already gone,
      so summing by source is safe
    - accounts left out keeps every dealer, which is what a whole-lobby table
      wants. It does not fall back to config.toml
    - stat swaps the figure like hero_damage: damage, healing, mitigated, ...
    """
    predicate = pl.lit(value=True)

    if accounts is not None:
        predicate &= pl.col("dealer_account_id").is_in(list(accounts))

    if matches is not None:
        predicate &= pl.col("match_id").is_in(list(matches))

    return MetricView(source=lambda: hero_damage(stat=stat, tz=tz), filter=predicate)


DAMAGE_SOURCE_DIMENSIONS = {
    "match_id": Dimension(pl.col("match_id")),
    "account_id": Dimension(pl.col("account_id")),
    "hero": Dimension(pl.col("hero")),
    "day": Dimension(pl.col("day"), comment="Local date, not the UTC date."),
    "week": Dimension(pl.col("start_local").dt.strftime("%G-W%V")),
    "month": Dimension(pl.col("start_local").dt.strftime("%Y-%m")),
    "source_name": Dimension(pl.col("source_name")),
    "source_class": Dimension(pl.col("source_class")),
    "delivery": Dimension(
        pl.col("delivery"),
        comment="Gun, ability, gun-triggered item proc, or spirit-triggered item proc.",
    ),
}

_AMOUNT = pl.col("amount")

DAMAGE_SOURCE_MEASURES = {
    "total": Measure(
        _AMOUNT.sum(),
        "count",
        comment="Selected stat summed over detail rows.",
        direction="maximize",
    ),
    "games": Measure(
        pl.col("match_id").n_unique(),
        "count",
        comment="Distinct matches where the source recorded the selected stat.",
    ),
    "per_game": Measure(
        lambda measure: try_divide(measure["total"], measure["games"]),
        "ratio",
        comment="Selected stat per match where the source appeared.",
        direction="maximize",
    ),
    "gun": Measure(
        _AMOUNT.filter(pl.col("delivery") == "gun").sum(),
        "count",
        comment="Selected stat from gun shots only.",
        direction="maximize",
    ),
    "abilities": Measure(
        _AMOUNT.filter(pl.col("delivery") == "ability").sum(),
        "count",
        comment="Selected stat from ability casts only.",
        direction="maximize",
    ),
    "items": Measure(
        _AMOUNT.filter(pl.col("delivery").str.ends_with("_proc")).sum(),
        "count",
        comment="Gun-triggered and spirit-triggered item procs together.",
        direction="maximize",
    ),
    "self": Measure(
        pl.col("self_amount").sum(),
        "count",
        comment="Healing or another selected stat whose target was its dealer.",
    ),
}


def _damage_sources(
    hero: str,
    accounts: Sequence[int] | None,
    matches: Sequence[int] | None,
    stat: str,
    tz: str | None,
) -> pl.LazyFrame:
    """Roll hero_damage detail rows up to one row per match, account, and source.

    Source normalization and delivery classification live here. Measures
    then aggregate the selected stat by source, delivery, game, or date.
    """
    resolved_accounts = _resolved_accounts(accounts)
    hero_name = _resolved_hero_name(hero)
    predicate = (pl.col("hero") == hero_name) & pl.col("dealer_account_id").is_in(resolved_accounts)

    if matches is not None:
        predicate &= pl.col("match_id").is_in(list(matches))

    return (
        hero_damage(stat=stat, tz=tz)
        .filter(predicate)
        .group_by(
            "match_id",
            pl.col("dealer_account_id").alias("account_id"),
            "hero",
            "day",
            "start_local",
            "source_name",
            "source_class",
            "delivery",
        )
        .agg(
            pl.col("damage").sum().alias("amount"),
            pl.col("damage")
            .filter(pl.col("target_account_id") == pl.col("dealer_account_id"))
            .sum()
            .alias("self_amount"),
        )
    )


@view(
    grain=("match_id", "account_id", "source_class", "delivery"),
    dimensions=DAMAGE_SOURCE_DIMENSIONS,
    measures=DAMAGE_SOURCE_MEASURES,
)
def damage_source_games(
    hero: str,
    accounts: Sequence[int] | None = None,
    matches: Sequence[int] | None = None,
    stat: str = "damage",
    tz: str | None = None,
) -> MetricView:
    """One row per match, account, and damage or healing source.

    - stat swaps the figure like hero_damage: damage, healing, mitigated, ...
    """
    return MetricView(
        source=lambda: _damage_sources(hero, accounts, matches, stat, tz),
        joins=(Join("matches", using="match_id"),),
    )


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
    accounts = _resolved_accounts(accounts)
    rows = view_frame(
        damage_source_games(hero, accounts=accounts, matches=matches, stat=stat),
        parquet_dir=parquet_dir,
    ).collect()

    if rows.is_empty():
        msg = f"no {stat} rows for {hero} on accounts {accounts}"
        raise ValueError(msg)

    sources = summarize(
        damage_source_games,
        by=("source_name", "source_class", "delivery"),
        measures=("total", "games"),
        lf=rows.lazy(),
    ).collect()
    source_minutes = (
        rows.select(
            "source_name",
            "source_class",
            "delivery",
            "match_id",
            pl.col("matches.duration_s").alias("duration_s"),
        )
        .unique()
        .group_by("source_name", "source_class", "delivery")
        .agg((pl.col("duration_s").sum() / 60).alias("minutes"))
    )
    sources = sources.join(source_minutes, on=["source_name", "source_class", "delivery"])

    match_ids = (
        pl.Series("match_id", matches, dtype=pl.Int64).unique()
        if matches is not None
        else rows.get_column("match_id").unique()
    )
    ids = _proc_item_ids(rows)
    owned_rows, outlay_rows = pl.collect_all(
        [
            _owned_minutes(ids, accounts, match_ids, parquet_dir),
            _effective_outlay(ids, accounts, match_ids, parquet_dir),
        ]
    )
    grand = sources.get_column("total").sum()
    owned = {ids[item_id]: minutes for item_id, minutes in owned_rows.iter_rows()}
    owned_min = (
        pl.col("source_class").replace_strict(owned, default=None, return_dtype=pl.Float64)
        if owned
        else pl.lit(None, dtype=pl.Float64)
    )
    outlay = {ids[item_id]: souls for item_id, souls in outlay_rows.iter_rows()}
    outlay_souls = (
        pl.col("source_class").replace_strict(outlay, default=None, return_dtype=pl.Float64)
        if outlay
        else pl.lit(None, dtype=pl.Float64)
    )
    item_row = pl.col("delivery").str.ends_with("_proc")

    return (
        sources.with_columns(
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
) -> pl.LazyFrame:
    """Sum the minutes each item damage source was owned across the given games, lazily.

    - one row per item id, only the item proc sources in ids appear, and the
      frame stays empty without any
    - ownership windows come from the buys, like the item command: a sold or
      consumed buy ends at sold_time_s, a kept buy at the end of the match
    """
    if not ids:
        return pl.LazyFrame(schema={"item_id": pl.Int64, "minutes": pl.Float64})

    return (
        _item_windows(
            pl.col("item_id").is_in(list(ids))
            & pl.col("match_id").is_in(match_ids.implode())
            & pl.col("account_id").is_in(accounts),
            parquet_dir,
        )
        .group_by("item_id")
        .agg(((pl.col("end_s") - pl.col("game_time_s")).sum() / 60).alias("minutes"))
        .filter(pl.col("minutes") > 0)
    )


def _effective_outlay(
    ids: dict[int, str],
    accounts: Sequence[int],
    match_ids: pl.Series,
    parquet_dir: str | Path | None,
) -> pl.LazyFrame:
    """Sum the effective souls put into each item damage source across the given games, lazily.

    - one row per item id, only the item proc sources in ids appear
    - empty when the versioned asset tables are missing
    """
    priced = table_exists("item_history", parquet_dir) and table_exists(
        "item_component_history", parquet_dir
    )

    if not ids or not priced:
        return pl.LazyFrame(schema={"item_id": pl.Int64, "souls": pl.Int64})

    return (
        item_events_effective(parquet_dir)
        .filter(
            pl.col("item_id").is_in(list(ids)),
            pl.col("match_id").is_in(match_ids.implode()),
            pl.col("account_id").is_in(list(accounts)),
        )
        .group_by("item_id")
        .agg(pl.col("effective_cost").sum().alias("souls"))
        .filter(pl.col("souls") > 0)
    )


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

    mine = view_frame(my_games(accounts, tz), parquet_dir=parquet_dir).filter(
        pl.col("hero_id") == hero_id
    )

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
        pl.col("matches.duration_s").alias("duration_s"),
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
    split = summarize(
        damage_source_games,
        by=("match_id", "account_id"),
        measures=("total", "gun", "abilities", "items"),
        hero=hero,
        accounts=accounts,
        parquet_dir=parquet_dir,
        tz=tz,
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
    split = summarize(
        damage_source_games,
        by=("match_id", "account_id"),
        measures=("total", "abilities", "items", "self"),
        hero=hero,
        accounts=accounts,
        parquet_dir=parquet_dir,
        stat="healing",
        tz=tz,
    )
    prevented = summarize(
        damage_source_games,
        by=("match_id", "account_id"),
        measures=("total",),
        hero=hero,
        accounts=accounts,
        parquet_dir=parquet_dir,
        stat="heal_prevented",
        tz=tz,
    ).rename({"total": "prevented"})
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

SOUL_SOURCE_DIMENSIONS = {
    "match_id": Dimension(pl.col("match_id")),
    "account_id": Dimension(pl.col("account_id")),
    "hero": Dimension(pl.col("hero")),
    "day": Dimension(pl.col("day"), comment="Local date, not the UTC date."),
    "week": Dimension(pl.col("start_local").dt.strftime("%G-W%V")),
    "month": Dimension(pl.col("start_local").dt.strftime("%Y-%m")),
    "source_name": Dimension(pl.col("source_name")),
    "group": Dimension(
        pl.col("group"),
        comment="Waves, roaming, combat, or objectives; rare and catch-up sources are null.",
    ),
}

_SOULS = pl.col("souls")

SOUL_SOURCE_MEASURES = {
    "souls": Measure(
        _SOULS.sum(),
        "souls",
        comment="Gross souls including secured orb portions, not final net worth.",
        direction="maximize",
    ),
    "secured_orbs": Measure(
        pl.col("secured_orbs").sum(),
        "souls",
        comment="The part of those souls that came from securing deniable orbs.",
        direction="maximize",
    ),
    "games": Measure(
        pl.col("match_id").n_unique(),
        "count",
        comment="Distinct matches where the source paid nonzero souls.",
    ),
    "souls_per_game": Measure(
        lambda measure: try_divide(measure["souls"], measure["games"]),
        "souls",
        comment="Gross souls over the matches where the source paid, not over every match.",
        direction="maximize",
    ),
    "orb_share": Measure(
        lambda measure: try_divide(measure["secured_orbs"], measure["souls"]),
        "proportion",
        comment="Secured deniable orb portions over gross souls.",
    ),
    **{
        group: Measure(
            _SOULS.filter(pl.col("group") == group).sum(),
            "souls",
            direction="maximize",
        )
        for group in ("waves", "roaming", "combat", "objectives")
    },
}


@view(
    grain=("match_id", "account_id", "source_name"),
    dimensions=SOUL_SOURCE_DIMENSIONS,
    measures=SOUL_SOURCE_MEASURES,
)
def soul_source_games(
    hero: str,
    accounts: Sequence[int] | None = None,
    matches: Sequence[int] | None = None,
    tz: str | None = None,
) -> MetricView:
    """One row per match, account, and nonzero soul source."""
    return MetricView(
        source=lambda: _soul_sources(hero, accounts, matches, tz),
        joins=(Join("matches", using="match_id"),),
    )


def _soul_sources(
    hero: str,
    accounts: Sequence[int] | None,
    matches: Sequence[int] | None,
    tz: str | None,
) -> pl.LazyFrame:
    """Roll the soul_sources snapshots up to one nonzero row per game and source."""
    resolved_accounts = _resolved_accounts(accounts)
    hero_name = _resolved_hero_name(hero)
    hero_games = (
        view_frame(my_games(resolved_accounts, tz))
        .filter(pl.col("hero") == hero_name)
        .select("match_id", "account_id", "hero", "day", "start_local")
    )

    if matches is not None:
        hero_games = hero_games.filter(pl.col("match_id").is_in(list(matches)))

    return (
        scan("soul_sources")
        .join(hero_games, on=["match_id", "account_id"])
        .group_by(
            "match_id",
            "account_id",
            "hero",
            "day",
            "start_local",
            "source_name",
        )
        .agg(
            pl.col("souls").max().alias("_guaranteed_souls"),
            pl.col("souls_orbs").max().alias("secured_orbs"),
        )
        .with_columns((pl.col("_guaranteed_souls") + pl.col("secured_orbs")).alias("souls"))
        .drop("_guaranteed_souls")
        .filter(pl.col("souls") != 0)
        .with_columns(
            pl.col("source_name")
            .replace_strict(SOUL_GROUP_COLUMNS, default=None, return_dtype=pl.String)
            .alias("group")
        )
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
    accounts = _resolved_accounts(accounts)
    finals = view_frame(
        soul_source_games(hero, accounts=accounts, matches=matches),
        parquet_dir=parquet_dir,
    ).collect()

    if finals.is_empty():
        msg = f"no soul_sources rows for {hero} on accounts {accounts}"
        raise ValueError(msg)

    sources = summarize(
        soul_source_games,
        by="source_name",
        measures=("souls", "secured_orbs", "games", "orb_share"),
        lf=finals.lazy(),
    ).collect()
    source_minutes = (
        finals.select("source_name", "match_id", pl.col("matches.duration_s").alias("duration_s"))
        .unique()
        .group_by("source_name")
        .agg((pl.col("duration_s").sum() / 60).alias("minutes"))
    )
    sources = sources.join(source_minutes, on="source_name")
    total = int(sources.get_column("souls").sum())

    return (
        sources.with_columns(
            (pl.col("souls") / total * 100).round(1).alias("percent"),
            (pl.col("orb_share") * 100).round(1),
        )
        .select("games", "source_name", "souls", "secured_orbs", "minutes", "percent", "orb_share")
        .sort("souls", descending=True)
    )


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
    split = summarize(
        soul_source_games,
        by=("match_id", "account_id"),
        measures=("souls", "waves", "roaming", "combat", "objectives"),
        hero=hero,
        accounts=accounts,
        parquet_dir=parquet_dir,
        tz=tz,
    ).rename({"souls": "total"})

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


def combat_hero_records(
    accounts: Sequence[int] | None = None,
    parquet_dir: str | Path | None = None,
    tz: str | None = None,
    days: int | None = None,
    since: str | dt.date | None = None,
) -> pl.DataFrame:
    """Take one row per hero with overall aim and parry counters.

    - rates use the summed counters, so games with more shots carry their
      proper weight instead of averaging per-game percentages
    - shots, hits, and headshots count fire at enemy heroes only
    - hit_pct is hits over shots and headshot_pct is headshots over hits,
      with both null for a hero with no tracked shots
    - parries include Counterspell auto-parries
    - days and since filter on the local day across all heroes
    """
    accounts = _resolved_accounts(accounts)
    mine = view_frame(my_games(accounts, tz), parquet_dir=parquet_dir)

    if since is not None:
        since = dt.date.fromisoformat(since) if isinstance(since, str) else since
        mine = mine.filter(pl.col("day") >= since)

    if days is not None:
        mine = mine.filter(pl.col("day").rank("dense", descending=True) <= days)

    games = mine.select("match_id", "account_id", "hero").unique()
    finals = _final_custom_values(
        scan("custom_stats", parquet_dir).filter(pl.col("account_id").is_in(accounts))
    ).join(games, on=["match_id", "account_id"])
    totals = finals.group_by("hero").agg(
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

    return (
        games.group_by("hero")
        .agg(pl.len().cast(pl.Int64).alias("games"))
        .join(totals, on="hero", how="left")
        .with_columns(pl.col(*counters).fill_null(0))
        .with_columns(
            pl.when(pl.col("shots") > 0)
            .then((pl.col("hits") / pl.col("shots") * 100).round(1))
            .alias("hit_pct"),
            pl.when(pl.col("hits") > 0)
            .then((pl.col("headshots") / pl.col("hits") * 100).round(1))
            .alias("headshot_pct"),
        )
        .sort("games", "hero", descending=[True, False])
        .collect()
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
