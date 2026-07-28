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
from deadlock_matches.queries.delivery import hero_damage, with_delivery
from deadlock_matches.queries.items import _item_windows, item_events_effective
from deadlock_matches.queries.labels import (
    buff_family,
    buff_level,
    hero_name,
    stack_class_name,
    stack_name,
    with_damage_source_name,
    with_soul_source_name,
)
from deadlock_matches.queries.semantic import (
    Dimension,
    Format,
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


FLAT = Format(group=True, small=2)

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
        missing="zero",
    ),
    "games": Measure(
        pl.col("match_id").n_unique(),
        "count",
        comment="Distinct matches that recorded the counter.",
        missing="zero",
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
    "buff": Dimension(buff_family(), comment="Buff family such as ammo, cd, spirit, or wp."),
    "level": Dimension(buff_level()),
}

BUFF_GAME_MEASURES = {
    "held": Measure(
        pl.col("count").filter(pl.col("permanent")).sum(),
        "count",
        comment="Permanent buffs the player finished with, whatever they were picked up from.",
        missing="zero",
    ),
    "bridge": Measure(
        pl.col("count").filter(~pl.col("permanent")).sum(),
        "count",
        comment="Temporary bridge buffs claimed.",
        missing="zero",
    ),
    "games": Measure(
        pl.col("match_id").n_unique(),
        "count",
        comment="Distinct matches that recorded a buff in the group.",
        missing="zero",
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
        pl.col("account_id"),
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
        missing="zero",
    ),
    "games": Measure(
        pl.col("match_id").n_unique(),
        "count",
        comment="Distinct matches with a detail row in the group.",
        missing="zero",
    ),
    "targets": Measure(
        pl.col("target_account_id").n_unique(),
        "count",
        comment="Distinct enemy heroes the group landed on.",
        missing="zero",
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
        missing="zero",
    ),
    "gun_body": Measure(
        _DAMAGE.filter(_BULLET & ~_HEADSHOT).sum(),
        "count",
        comment="Bullet damage from shots that were not headshots.",
        direction="maximize",
        missing="zero",
    ),
    "gun_headshot": Measure(
        _DAMAGE.filter(_BULLET & _HEADSHOT).sum(),
        "count",
        comment="Bullet damage from the _crit sources. gun_body holds the rest.",
        direction="maximize",
        missing="zero",
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
        predicate &= pl.col("account_id").is_in(list(accounts))

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

_DEALT = _AMOUNT != 0

_DEALT_GAMES = pl.struct("match_id", "account_id").filter(_DEALT)

DAMAGE_SOURCE_MEASURES = {
    "total": Measure(
        _AMOUNT.sum(),
        "count",
        comment="Selected stat summed over detail rows.",
        direction="maximize",
        missing="zero",
    ),
    "games": Measure(
        _DEALT_GAMES.n_unique(),
        "count",
        comment="Distinct player-games where the source recorded the selected stat.",
        missing="zero",
    ),
    "minutes": Measure(
        pl.col("game_minutes").filter(_DEALT).filter(_DEALT_GAMES.is_first_distinct()).sum(),
        "minutes",
        comment="Combined length of the games where the source recorded the selected stat.",
        missing="zero",
    ),
    "per_game": Measure(
        lambda measure: try_divide(measure["total"], measure["games"]),
        "ratio",
        comment="Selected stat per match where the source appeared.",
        format=FLAT,
        direction="maximize",
    ),
    "per_min": Measure(
        lambda measure: try_divide(measure["total"], measure["minutes"]),
        "ratio",
        comment="Selected stat per minute of the games where the source appeared.",
        format=FLAT,
        direction="maximize",
    ),
    "owned_minutes": Measure(
        pl.col("owned_minutes").sum(),
        "minutes",
        comment="Minutes an item source was owned, counting the games where it dealt nothing.",
        missing="zero",
    ),
    "per_min_owned": Measure(
        lambda measure: try_divide(measure["total"], measure["owned_minutes"]),
        "ratio",
        comment="Item sources only, and null for a gun or an ability, which nobody buys.",
        format=FLAT,
        direction="maximize",
    ),
    "outlay": Measure(
        pl.col("effective_cost").sum(),
        "souls",
        comment="Effective souls put into an item source, its era price less its components.",
        missing="zero",
    ),
    "per_1k": Measure(
        lambda measure: try_divide(measure["total"] * 1000, measure["outlay"]),
        "ratio",
        comment="Selected stat per 1,000 souls of effective outlay, item sources only.",
        format=FLAT,
        direction="maximize",
    ),
    "share": Measure(
        lambda measure: try_divide(measure["total"], pl.col("window_total").max()),
        "proportion",
        comment="The share of everything the window recorded, so the sources add to one.",
        direction="maximize",
    ),
    "per_window_game": Measure(
        lambda measure: try_divide(measure["total"], pl.col("window_games").max()),
        "ratio",
        comment="Selected stat per game of the hero, counting the games the source sat out.",
        format=FLAT,
        direction="maximize",
    ),
    "per_window_min": Measure(
        lambda measure: try_divide(measure["total"], pl.col("window_minutes").max()),
        "ratio",
        comment="Selected stat per minute of every game of the hero, not only its own games.",
        format=FLAT,
        direction="maximize",
    ),
    "gun": Measure(
        _AMOUNT.filter(pl.col("delivery") == "gun").sum(),
        "count",
        comment="Selected stat from gun shots only.",
        direction="maximize",
        missing="zero",
    ),
    "abilities": Measure(
        _AMOUNT.filter(pl.col("delivery") == "ability").sum(),
        "count",
        comment="Selected stat from ability casts only.",
        direction="maximize",
        missing="zero",
    ),
    "items": Measure(
        _AMOUNT.filter(pl.col("delivery").str.ends_with("_proc")).sum(),
        "count",
        comment="Gun-triggered and spirit-triggered item procs together.",
        direction="maximize",
        missing="zero",
    ),
    "self": Measure(
        pl.col("self_amount").sum(),
        "count",
        comment="Healing or another selected stat whose target was its dealer.",
        missing="zero",
    ),
}


_SOURCE_KEYS = ("match_id", "account_id", "source_class")


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

    - the window columns repeat the whole covered game set on every row, so
      a share or a per game rate divides by every game of the hero rather
      than by the games the group happened to appear in
    - an item source keeps a row in a game where it was owned and dealt
      nothing, which is the only way per_1k divides by every soul spent on
      it. Those rows carry a zero amount, so games and minutes read them out
    """
    resolved_accounts = _resolved_accounts(accounts)
    hero_name = _resolved_hero_name(hero)
    predicate = (pl.col("hero") == hero_name) & pl.col("account_id").is_in(resolved_accounts)

    if matches is not None:
        predicate &= pl.col("match_id").is_in(list(matches))

    detail = (
        hero_damage(stat=stat, tz=tz)
        .filter(predicate)
        .group_by(
            "match_id",
            "account_id",
            "source_name",
            "source_class",
            "delivery",
        )
        .agg(
            pl.col("damage").sum().alias("amount"),
            pl.col("damage")
            .filter(pl.col("target_account_id") == pl.col("account_id"))
            .sum()
            .alias("self_amount"),
        )
    )
    games = _hero_window(hero_name, resolved_accounts, matches, tz)
    rows = _with_item_facts(detail, games, resolved_accounts, matches)

    return rows.join(games, on=["match_id", "account_id"], how="left").with_columns(
        pl.col("amount").sum().alias("window_total")
    )


def _hero_window(
    hero_name: str,
    accounts: Sequence[int],
    matches: Sequence[int] | None,
    tz: str | None,
) -> pl.LazyFrame:
    """Take every player-game a damage source view covers with the length of each.

    - the window is the games of the hero, not the games that recorded the
      selected stat, so heal prevented still divides by every game
    - the count and the combined minutes ride along on every row rather than
      arriving by a cross join, which projection pushdown is free to undo
    """
    games = (
        view_frame(my_games(accounts, tz))
        .filter(pl.col("hero") == hero_name)
        .select(
            "match_id",
            "account_id",
            "hero",
            "day",
            "start_local",
            (pl.col("matches.duration_s") / 60).alias("game_minutes"),
        )
    )

    if matches is not None:
        games = games.filter(pl.col("match_id").is_in(list(matches)))

    return games.unique(subset=["match_id", "account_id"]).with_columns(
        pl.len().alias("window_games"),
        pl.col("game_minutes").sum().alias("window_minutes"),
    )


def _with_item_facts(
    detail: pl.LazyFrame,
    games: pl.LazyFrame,
    accounts: Sequence[int],
    matches: Sequence[int] | None,
) -> pl.LazyFrame:
    """Add the owned minutes and effective outlay of each item source per game.

    - only the source classes the damage rows already hold take part, so an
      item that never dealt the selected stat never becomes a source of its
      own
    - a game where one of them was owned and dealt nothing joins in as a
      zero amount row, which is what makes the two denominators whole
    """
    classes = detail.select("source_class").unique()
    owned = _owned_game_minutes(classes, games, accounts, matches)
    outlay = _outlay_game_souls(classes, games, accounts, matches)
    facts = with_damage_source_name(
        with_delivery(
            owned.join(outlay, on=list(_SOURCE_KEYS), how="full", coalesce=True),
        )
    )

    return (
        detail.join(facts, on=list(_SOURCE_KEYS), how="full", coalesce=True)
        .with_columns(
            pl.coalesce("source_name", "source_name_right").alias("source_name"),
            pl.coalesce("delivery", "delivery_right").alias("delivery"),
            pl.col("amount", "self_amount", "owned_minutes", "effective_cost").fill_null(0),
        )
        .drop("category", "source_name_right", "delivery_right")
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
    sources = summarize(
        damage_source_games,
        by=("source_name", "source_class", "delivery"),
        measures=(
            "games",
            "total",
            "per_min",
            "per_min_owned",
            "per_1k",
            "share",
        ),
        hero=hero,
        accounts=accounts,
        matches=matches,
        stat=stat,
        parquet_dir=parquet_dir,
    ).collect()

    if sources.is_empty():
        msg = f"no {stat} rows for {hero} on accounts {accounts}"
        raise ValueError(msg)

    return (
        sources.filter(pl.col("total") != 0)
        .with_columns(
            pl.col("per_min", "per_min_owned", "per_1k").round(1),
            (pl.col("share") * 100).round(1).alias("percent"),
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


def _item_source_class() -> pl.Expr:
    """Resolve an item id to the engine class name a damage source carries."""
    names = {item.id: item.class_name for item in items.item_map().values() if item.class_name}

    return (
        pl.col("item_id")
        .replace_strict(names, default=None, return_dtype=pl.String)
        .alias("source_class")
    )


def _item_predicate(accounts: Sequence[int], matches: Sequence[int] | None) -> pl.Expr:
    """Cut an item event scan down to the accounts and matches the window covers."""
    predicate = pl.col("account_id").is_in(list(accounts))

    if matches is not None:
        predicate &= pl.col("match_id").is_in(list(matches))

    return predicate


def _owned_game_minutes(
    classes: pl.LazyFrame,
    games: pl.LazyFrame,
    accounts: Sequence[int],
    matches: Sequence[int] | None,
) -> pl.LazyFrame:
    """Sum the minutes each item damage source was owned into one row per game and source.

    - ownership windows come from the buys, like the item command: a sold or
      consumed buy ends at sold_time_s, a kept buy at the end of the match
    """
    return (
        _item_windows(_item_predicate(accounts, matches), None)
        .with_columns(_item_source_class())
        .join(classes.select("source_class"), on="source_class", how="semi")
        .join(games.select("match_id", "account_id"), on=["match_id", "account_id"], how="semi")
        .group_by(*_SOURCE_KEYS)
        .agg(((pl.col("end_s") - pl.col("game_time_s")).sum() / 60).alias("owned_minutes"))
    )


def _outlay_game_souls(
    classes: pl.LazyFrame,
    games: pl.LazyFrame,
    accounts: Sequence[int],
    matches: Sequence[int] | None,
) -> pl.LazyFrame:
    """Sum the effective souls put into each item damage source per game and source.

    - effective means the era price minus the components already paid for,
      so a tier four item is not charged twice
    - empty when the versioned asset tables are missing, which leaves per_1k
      null rather than wrong
    """
    priced = table_exists("item_history") and table_exists("item_component_history")

    if not priced:
        return pl.LazyFrame(
            schema={
                "match_id": pl.Int64,
                "account_id": pl.Int64,
                "source_class": pl.String,
                "effective_cost": pl.Int64,
            }
        )

    return (
        item_events_effective()
        .filter(_item_predicate(accounts, matches))
        .with_columns(_item_source_class())
        .join(classes.select("source_class"), on="source_class", how="semi")
        .join(games.select("match_id", "account_id"), on=["match_id", "account_id"], how="semi")
        .group_by(*_SOURCE_KEYS)
        .agg(pl.col("effective_cost").sum())
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
        missing="zero",
    ),
    "secured_orbs": Measure(
        pl.col("secured_orbs").sum(),
        "souls",
        comment="The part of those souls that came from securing deniable orbs.",
        direction="maximize",
        missing="zero",
    ),
    "games": Measure(
        pl.col("match_id").n_unique(),
        "count",
        comment="Distinct matches where the source paid nonzero souls.",
        missing="zero",
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
            missing="zero",
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
        with_soul_source_name(scan("soul_sources"))
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

COMBAT_GAME_COUNTERS = (
    *COMBAT_COUNTERS,
    ("Enemy Hero Accuracy - Incoming", "Shots", "incoming_shots"),
    ("Enemy Hero Accuracy - Incoming", "Hits", "incoming_hits"),
)


def _counter_totals(counters: Sequence[tuple[str | None, str, str]]) -> list[pl.Expr]:
    """Sum each named custom stat into a column of its own."""
    return [
        pl.col("value")
        .filter(
            pl.col("group").is_null() if group is None else pl.col("group") == group,
            pl.col("stat") == stat,
        )
        .sum()
        .cast(pl.Int64)
        .alias(name)
        for group, stat, name in counters
    ]


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
    totals = finals.group_by("hero").agg(*_counter_totals(COMBAT_COUNTERS))
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

    split = finals.group_by("match_id", "account_id").agg(*_counter_totals(COMBAT_COUNTERS))
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


COMBAT_GAME_DIMENSIONS = {
    "match_id": Dimension(pl.col("match_id")),
    "account_id": Dimension(pl.col("account_id")),
    "hero": Dimension(pl.col("hero")),
    "won": Dimension(pl.col("won")),
    "day": Dimension(pl.col("day"), comment="Local date, not the UTC date."),
    "week": Dimension(pl.col("start_local").dt.strftime("%G-W%V")),
    "month": Dimension(pl.col("start_local").dt.strftime("%Y-%m")),
}

_PER_GAME = Format(decimals=1, group=True)


def _counter(column: str, comment: str, direction: str = "") -> Measure:
    """Sum one fight counter across player-games."""
    return Measure(
        pl.col(column).sum(),
        "count",
        comment=comment,
        direction=direction,
        missing="zero",
    )


COMBAT_GAME_MEASURES = {
    "games": Measure(
        pl.len(),
        "count",
        comment="Every game of the hero, tracked counters or not.",
        missing="zero",
    ),
    "shots": _counter("shots", "Shots fired at enemy heroes, never at troopers."),
    "hits": _counter("hits", "Shots that landed on an enemy hero.", "maximize"),
    "headshots": _counter("headshots", "Hits that landed on the head.", "maximize"),
    "incoming_shots": _counter("incoming_shots", "Shots enemy heroes fired at the player."),
    "incoming_hits": _counter("incoming_hits", "Enemy shots that landed.", "minimize"),
    "parries": _counter("parries", "Counterspell auto-parries included.", "maximize"),
    "missed_parries": _counter("missed_parries", "Parry attempts that whiffed.", "minimize"),
    "gun_damage": _counter(
        "gun_damage", "Bullet damage to heroes, headshots included.", "maximize"
    ),
    "hit_rate": Measure(
        lambda measure: try_divide(measure["hits"], measure["shots"]),
        "proportion",
        comment="Hits over shots at enemy heroes, far below the all-target accuracy.",
        direction="maximize",
    ),
    "headshot_rate": Measure(
        lambda measure: try_divide(measure["headshots"], measure["hits"]),
        "proportion",
        comment="Headshots over hits, so it reads the aim inside the shots that landed.",
        direction="maximize",
    ),
    "incoming_hit_rate": Measure(
        lambda measure: try_divide(measure["incoming_hits"], measure["incoming_shots"]),
        "proportion",
        comment="How often enemy fire lands on the player, where lower is the harder target.",
        direction="minimize",
    ),
    "shots_per_game": Measure(
        lambda measure: try_divide(measure["shots"], measure["games"]),
        "ratio",
        comment="How much the player shoots, whether or not the shots land.",
        format=_PER_GAME,
    ),
    "gun_damage_per_game": Measure(
        lambda measure: try_divide(measure["gun_damage"], measure["games"]),
        "ratio",
        format=_PER_GAME,
        direction="maximize",
    ),
    "gun_damage_per_hit": Measure(
        lambda measure: try_divide(measure["gun_damage"], measure["hits"]),
        "ratio",
        comment="What one landed bullet is worth, which the build and the target decide.",
        format=_PER_GAME,
        direction="maximize",
    ),
    "parries_per_game": Measure(
        lambda measure: try_divide(measure["parries"], measure["games"]),
        "ratio",
        format=_PER_GAME,
        direction="maximize",
    ),
    "missed_parries_per_game": Measure(
        lambda measure: try_divide(measure["missed_parries"], measure["games"]),
        "ratio",
        format=_PER_GAME,
        direction="minimize",
    ),
}


@view(
    grain=("match_id", "account_id"),
    dimensions=COMBAT_GAME_DIMENSIONS,
    measures=COMBAT_GAME_MEASURES,
)
def combat_games(
    hero: str,
    accounts: Sequence[int] | None = None,
    matches: Sequence[int] | None = None,
    tz: str | None = None,
) -> MetricView:
    """One row per game of a hero with the fight counters the game tracks but never shows.

    - shots, hits, and headshots count fire at enemy heroes only, and the
      incoming pair counts enemy fire at the player
    - parries include Counterspell auto-parries
    - gun damage is the bullet damage to heroes of the same game, so the
      damage per hit divides two figures that cover the same shots
    - a game with no tracked counters keeps zeros rather than dropping out,
      which is what makes the per game rates divide by every game
    """
    return MetricView(source=lambda: _combat_game_rows(hero, accounts, matches, tz))


def _combat_game_rows(
    hero: str,
    accounts: Sequence[int] | None,
    matches: Sequence[int] | None,
    tz: str | None,
) -> pl.LazyFrame:
    """Join the fight counters and the gun damage onto every game of a hero."""
    resolved = _resolved_accounts(accounts)
    mine = _hero_game_rows(hero, resolved, None, tz, None, None)

    if matches is not None:
        mine = mine.filter(pl.col("match_id").is_in(list(matches)))

    keys = mine.select("match_id", "account_id")
    finals = _final_custom_values(
        scan("custom_stats").join(keys, on=["match_id", "account_id"], how="semi")
    )
    counters = finals.group_by("match_id", "account_id").agg(*_counter_totals(COMBAT_GAME_COUNTERS))
    names = [name for _, _, name in COMBAT_GAME_COUNTERS]
    rows = mine.join(counters, on=["match_id", "account_id"], how="left").join(
        _gun_damage_games(resolved, matches), on=["match_id", "account_id"], how="left"
    )

    return rows.with_columns(pl.col(*names, "gun_damage").fill_null(0))


def _gun_damage_games(
    accounts: Sequence[int],
    matches: Sequence[int] | None,
) -> pl.LazyFrame:
    """Sum the bullet damage to heroes of each player-game."""
    if not table_exists("damage"):
        return pl.LazyFrame(
            schema={"match_id": pl.Int64, "account_id": pl.Int64, "gun_damage": pl.Int64}
        )

    return summarize(
        hero_damage_games(accounts=accounts, matches=matches),
        by=("match_id", "account_id"),
        measures=("gun",),
    ).rename({"gun": "gun_damage"})
