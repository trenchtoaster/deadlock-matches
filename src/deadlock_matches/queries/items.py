"""Item pricing, ownership windows, and buy order queries."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from deadlock_matches import config
from deadlock_matches.assets import abilities, heroes, items
from deadlock_matches.queries.core import _ERA_SENTINEL, asset_asof, my_games, scan, table_exists
from deadlock_matches.queries.delivery import damage_category
from deadlock_matches.queries.scaling import _hero_by_era, _with_hero_era

if TYPE_CHECKING:
    from collections.abc import Sequence


def item_events_priced(parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Reprice item_events against the item era live at each match start.

    - joins item_events to matches for start_time, then as-of onto item_history
    - cost, slot, and tier come from item_history, not the baked snapshot
    """
    matches = scan("matches", parquet_dir).select("match_id", "start_time")
    left = (
        scan("item_events", parquet_dir).drop("cost", "slot", "tier").join(matches, on="match_id")
    )

    return asset_asof(left, "item_history", by="item_id", parquet_dir=parquet_dir)


def _component_closure(parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Expand item components to every ancestor in the upgrade chain.

    - depth 1 is the direct component, each extra hop follows that
      component to its own component within the same era snapshot
    - one row per (item_id, component_class_name, era_from) at the
      smallest depth reaching it
    """
    direct = (
        scan("item_component_history", parquet_dir)
        .select("item_id", "component_class_name", "era_from")
        .with_columns(pl.lit(1, dtype=pl.Int32).alias("depth"))
    )
    ids = (
        scan("item_history", parquet_dir)
        .select(
            pl.col("class_name").alias("component_class_name"),
            pl.col("item_id").alias("_component_item_id"),
        )
        .unique()
    )
    parents = direct.select(
        pl.col("item_id").alias("_component_item_id"),
        pl.col("component_class_name").alias("_next_class_name"),
        "era_from",
    )

    tiers = [direct]
    frontier = direct
    for _ in range(2):
        frontier = (
            frontier.join(ids, on="component_class_name")
            .join(parents, on=["_component_item_id", "era_from"])
            .select(
                "item_id",
                pl.col("_next_class_name").alias("component_class_name"),
                "era_from",
                (pl.col("depth") + 1).alias("depth"),
            )
        )
        tiers.append(frontier)

    return (
        pl.concat(tiers)
        .group_by("item_id", "component_class_name", "era_from")
        .agg(pl.col("depth").min())
    )


def item_events_effective(parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Add an effective_cost column with the marginal souls each buy cost.

    - effective_cost is the era price minus the era prices of the component
      buys the purchase consumed (the flags=1 rows leaving the inventory at
      the buy time)
    - component lists come from the item_component_history era live at match
      start and cover the whole upgrade chain
    - a buy that skips a tier still credits the lower item it consumed
    - a component consumed while two same-second buys both list it credits
      the closest chain relative first, then the lower item_id
    - a plain sell keeps its full effective_cost and the refund counts as
      soul income
    """
    events = item_events_priced(parquet_dir)
    key = ["match_id", "account_id", "item_id", "game_time_s"]

    comps = _component_closure(parquet_dir).with_columns(
        pl.when(pl.col("era_from") == pl.col("era_from").min().over("item_id"))
        .then(pl.lit(_ERA_SENTINEL))
        .otherwise(pl.col("era_from"))
        .alias("_from")
    )
    candidates = (
        events.select(*key, "start_time")
        .join(comps, on="item_id")
        .filter(pl.col("_from") <= pl.col("start_time"))
        .filter(pl.col("_from") == pl.col("_from").max().over(key))
        .select(*key, "component_class_name", "depth")
    )
    consumed = events.filter(pl.col("flags") == 1, pl.col("sold_time_s") > 0).select(
        "match_id",
        "account_id",
        pl.col("class_name").alias("component_class_name"),
        pl.col("sold_time_s").alias("game_time_s"),
        pl.col("cost").alias("component_cost"),
    )
    consumed_key = ["match_id", "account_id", "component_class_name", "game_time_s"]
    credits = (
        candidates.join(consumed, on=consumed_key)
        .filter(pl.col("depth") == pl.col("depth").min().over(consumed_key))
        .filter(pl.col("item_id") == pl.col("item_id").min().over(consumed_key))
        .group_by(key)
        .agg(pl.col("component_cost").sum().alias("_credit"))
    )

    return (
        events.join(credits, on=key, how="left")
        .with_columns((pl.col("cost") - pl.col("_credit").fill_null(0)).alias("effective_cost"))
        .drop("_credit")
    )


def item_attribution(parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """item_events with an attribution column derived from the damage table.

    - proc = the item shows up as its own upgrade_ damage source somewhere in damage
    - stat = it never does, its value hides inside other damage rows (Boundless Spirit, Echo Shard)
    - derived at read time so it stays consistent no matter how the tables were appended
    """
    proc = (
        scan("damage", parquet_dir)
        .filter(pl.col("stat") == "damage")
        .filter(pl.col("source_class").str.starts_with("upgrade_"))
        .select(pl.col("source_class").alias("class_name"))
        .unique()
        .with_columns(pl.lit(True).alias("_proc"))
    )

    catalog = items.item_map()
    named = [(item_id, item.class_name) for item_id, item in catalog.items() if item.class_name]
    lookup = pl.LazyFrame(
        {
            "item_id": [item_id for item_id, _ in named],
            "class_name": [class_name for _, class_name in named],
        }
    )

    return (
        scan("item_events", parquet_dir)
        .join(lookup, on="item_id", how="left")
        .join(proc, on="class_name", how="left")
        .with_columns(
            pl.when(pl.col("_proc").is_not_null())
            .then(pl.lit("proc"))
            .otherwise(pl.lit("stat"))
            .alias("attribution")
        )
        .drop("_proc", "class_name")
    )


def _item_windows(predicate: pl.Expr, parquet_dir: str | Path | None) -> pl.LazyFrame:
    """Build one row per buy of one item with its ownership window.

    The window for a sold buy ends at the sell time, for a kept buy at the
    end of the match.
    """
    return (
        scan("item_events", parquet_dir)
        .filter(predicate)
        .join(scan("matches", parquet_dir).select("match_id", "duration_s"), on="match_id")
        .with_columns(
            pl.when(pl.col("sold_time_s") > 0)
            .then(pl.col("sold_time_s"))
            .otherwise(pl.col("duration_s"))
            .alias("end_s"),
            (pl.col("sold_time_s") == 0).alias("kept"),
        )
    )


def _item_buys(windows: pl.LazyFrame) -> pl.LazyFrame:
    """Build one row per buyer per match with the first buy time and summed owned seconds."""
    return windows.group_by("match_id", "account_id").agg(
        pl.col("game_time_s").min(),
        (pl.col("end_s") - pl.col("game_time_s")).sum().alias("owned_s"),
    )


def _dealt_owning(windows: pl.LazyFrame, parquet_dir: str | Path | None) -> pl.LazyFrame:
    """Hero damage each buyer dealt while owning the item, from the stats snapshots.

    For each ownership window, subtracts the cumulative player_damage at
    the buy from the value at the sell (or match end), then sums the
    windows. Damage dealt between a sell and a rebuy stays out.
    """
    snaps = scan("stats", parquet_dir).select(
        "match_id", "account_id", "time_stamp_s", "player_damage"
    )
    spans = windows.select("match_id", "account_id", "game_time_s", "end_s", "kept")
    joined = snaps.join(spans, on=["match_id", "account_id"])
    grp = "match_id", "account_id", "game_time_s"

    before = (
        joined.filter(pl.col("time_stamp_s") <= pl.col("game_time_s"))
        .group_by(*grp)
        .agg(pl.col("player_damage").max().alias("damage_before"))
    )
    until = (
        joined.filter(pl.col("kept") | (pl.col("time_stamp_s") <= pl.col("end_s")))
        .group_by(*grp)
        .agg(pl.col("player_damage").max().alias("damage_until"))
    )

    return (
        spans.join(until, on=list(grp), how="left")
        .join(before, on=list(grp), how="left")
        .group_by("match_id", "account_id")
        .agg(
            (pl.col("damage_until").fill_null(0) - pl.col("damage_before").fill_null(0))
            .sum()
            .alias("dealt_after_buy")
        )
    )


def item_value(
    item: str,
    parquet_dir: str | Path | None = None,
    hero: str | None = None,
    accounts: Sequence[int] | None = None,
) -> dict[str, float]:
    """Damage per minute owned for one item, across everyone in the tables.

    Counts every buy, ending the ownership window at the sell time when the
    item was sold. hero filters to players who played that hero, accounts
    to those buyers only. percent_of_hero_damage is the item damage as a
    percent of all the hero damage its buyers dealt while owning it.
    """
    it = items.item_by_name(item)

    if it is None:
        msg = f"Unknown item {item!r}"
        raise ValueError(msg)

    windows = _item_windows(pl.col("item") == it.name, parquet_dir)

    if hero is not None:
        played = (
            scan("players", parquet_dir)
            .filter(pl.col("hero") == hero)
            .select("match_id", "account_id")
        )
        windows = windows.join(played, on=["match_id", "account_id"])

    if accounts is not None:
        windows = windows.filter(pl.col("account_id").is_in(list(accounts)))

    dmg = (
        scan("damage", parquet_dir)
        .filter(
            pl.col("stat") == "damage",
            pl.col("source_class") == it.class_name,
            pl.col("target_account_id").is_not_null(),
            damage_category() != "total",
        )
        .group_by("match_id", pl.col("dealer_account_id").alias("account_id"))
        .agg(pl.col("damage").sum())
    )

    totals = (
        _item_buys(windows)
        .join(dmg, on=["match_id", "account_id"], how="left")
        .select(
            pl.len().alias("builds"),
            pl.col("owned_s").sum(),
            pl.col("damage").fill_null(0).sum().alias("damage"),
        )
    )
    dealt_total = _dealt_owning(windows, parquet_dir).select(
        pl.col("dealt_after_buy").sum().alias("dealt")
    )
    row, dealt_row = pl.collect_all([totals, dealt_total])

    builds = int(row.item(0, "builds"))
    owned = float(row.item(0, "owned_s") or 0)
    total = float(row.item(0, "damage") or 0)
    dealt = float(dealt_row.item() or 0)

    return {
        "builds": builds,
        "damage": total,
        "owned_s": owned,
        "per_min": total * 60 / owned if owned else 0.0,
        "dealt_after_buy": dealt,
        "percent_of_hero_damage": 100 * total / dealt if dealt else 0.0,
    }


def item_games(
    item: str,
    hero: str | None = None,
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    since: str | dt.date | None = None,
) -> pl.LazyFrame:
    """Build one row per game for the player, with the first buy time and damage for one item joined in.

    Games without a buy keep nulls, so "not built" games stay visible next to
    the built ones. owned_s sums the ownership windows, ending at the sell
    time when a buy was sold. hero filters to games on that hero. since keeps
    only days on or after that date (YYYY-MM-DD, like 2026-07-01).
    buy_n is the purchase order of the first named buy. tier_buy_n is its order
    among items of the same tier. first_tier_item is what the player bought
    first in that tier, and is_first_tier_item marks games where it was this item.
    dealt_after_buy is the hero damage the player dealt while owning the item,
    the denominator for the item percent of hero damage. effective_cost sums
    the era prices of its buys minus the components they consumed and is
    null when the versioned asset tables are missing.
    """
    it = items.item_by_name(item)

    if it is None:
        msg = f"Unknown item {item!r}"
        raise ValueError(msg)

    games = my_games(parquet_dir, accounts)

    if since is not None:
        since = dt.date.fromisoformat(since) if isinstance(since, str) else since
        games = games.filter(pl.col("day") >= since)

    if hero is not None:
        hero_id = heroes.hero_id_by_name(hero)

        if hero_id is None:
            msg = f"Unknown hero {hero!r}"
            raise ValueError(msg)

        games = games.filter(pl.col("hero_id") == hero_id)

    keys = games.select("match_id", "account_id")
    windows = _item_windows(pl.col("item_id") == it.id, parquet_dir).join(
        keys, on=["match_id", "account_id"], how="semi"
    )
    dealt = (
        scan("damage", parquet_dir)
        .filter(
            pl.col("source_class") == it.class_name,
            pl.col("stat") == "damage",
            pl.col("target_account_id").is_not_null(),
        )
        .join(
            keys.rename({"account_id": "dealer_account_id"}),
            on=["match_id", "dealer_account_id"],
            how="semi",
        )
        .group_by("match_id", "dealer_account_id")
        .agg(pl.col("damage").sum())
    )
    ordered_buys = (
        scan("item_events", parquet_dir)
        .filter(pl.col("item").is_not_null())
        .join(keys, on=["match_id", "account_id"], how="semi")
        .sort("match_id", "account_id", "game_time_s")
        .with_columns(
            pl.col("game_time_s").rank("ordinal").over("match_id", "account_id").alias("buy_n"),
            pl.col("game_time_s")
            .rank("ordinal")
            .over("match_id", "account_id", "tier")
            .alias("tier_buy_n"),
        )
    )
    target_order = (
        ordered_buys.filter(pl.col("item_id") == it.id)
        .group_by("match_id", "account_id")
        .agg(
            pl.col("buy_n").first(),
            pl.col("tier_buy_n").first(),
            pl.col("tier").first().alias("target_tier"),
        )
    )
    first_tier = ordered_buys.filter(pl.col("tier_buy_n") == 1).select(
        "match_id",
        "account_id",
        "tier",
        pl.col("item").alias("first_tier_item"),
        pl.col("game_time_s").alias("first_tier_time_s"),
    )
    priced = table_exists("item_history", parquet_dir) and table_exists(
        "item_component_history", parquet_dir
    )

    if priced:
        effective = (
            item_events_effective(parquet_dir)
            .filter(pl.col("item_id") == it.id)
            .join(keys, on=["match_id", "account_id"], how="semi")
            .group_by("match_id", "account_id")
            .agg(pl.col("effective_cost").sum())
        )
    else:
        effective = keys.clear().with_columns(pl.lit(None, dtype=pl.Int64).alias("effective_cost"))

    return (
        games.select("match_id", "account_id", "hero", "won", "duration_s", "start_time")
        .join(_item_buys(windows), on=["match_id", "account_id"], how="left")
        .join(effective, on=["match_id", "account_id"], how="left")
        .join(target_order, on=["match_id", "account_id"], how="left")
        .with_columns(pl.col("target_tier").fill_null(it.tier).alias("target_tier"))
        .join(
            first_tier,
            left_on=["match_id", "account_id", "target_tier"],
            right_on=["match_id", "account_id", "tier"],
            how="left",
        )
        .join(
            dealt,
            left_on=["match_id", "account_id"],
            right_on=["match_id", "dealer_account_id"],
            how="left",
        )
        .join(_dealt_owning(windows, parquet_dir), on=["match_id", "account_id"], how="left")
        .with_columns((pl.lit(it.name) == pl.col("first_tier_item")).alias("is_first_tier_item"))
        .sort("start_time")
    )


def ability_upgrades(
    hero: str | None = None,
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    since: str | dt.date | None = None,
    tz: str | None = None,
) -> pl.LazyFrame:
    """Ability unlocks and upgrades in spend order, with AP cost and soul threshold."""
    ability_rows = [
        {
            "item_id": ability.id,
            "ability": ability.name,
            "ability_class": ability.class_name,
            "hero_id": ability.hero,
        }
        for ability in abilities.ability_map().values()
        if ability.kind == "ability"
    ]
    ability_frame = pl.LazyFrame(
        ability_rows,
        schema={
            "item_id": pl.Int64,
            "ability": pl.String,
            "ability_class": pl.String,
            "hero_id": pl.Int64,
        },
    )

    games = my_games(parquet_dir, accounts, tz).select(
        "match_id", "account_id", "hero", "hero_id", "won", "duration_s", "start_time", "day"
    )

    if since is not None:
        since = dt.date.fromisoformat(since) if isinstance(since, str) else since
        games = games.filter(pl.col("day") >= since)

    if hero is not None:
        hero_id = heroes.hero_id_by_name(hero)

        if hero_id is None:
            msg = f"Unknown hero {hero!r}"
            raise ValueError(msg)

        games = games.filter(pl.col("hero_id") == hero_id)

    events = (
        scan("item_events", parquet_dir)
        .select("match_id", "account_id", "game_time_s", "item_id")
        .join(ability_frame, on="item_id")
        .join(games, on=["match_id", "account_id", "hero_id"])
        .sort("match_id", "account_id", "game_time_s")
        .with_columns(
            pl.int_range(1, pl.len() + 1)
            .over("match_id", "account_id", "ability")
            .alias("ability_upgrade_n"),
            pl.int_range(1, pl.len() + 1).over("match_id", "account_id").alias("ability_event_n"),
        )
        .with_columns(
            pl.when(pl.col("ability_upgrade_n") == 2)
            .then(1)
            .when(pl.col("ability_upgrade_n") == 3)
            .then(2)
            .when(pl.col("ability_upgrade_n") == 4)
            .then(5)
            .otherwise(0)
            .alias("ability_point_cost"),
            pl.when(pl.col("ability_upgrade_n") == 1)
            .then(1)
            .otherwise(0)
            .cum_sum()
            .over("match_id", "account_id")
            .alias("ability_unlock_n"),
        )
        .with_columns(
            pl.col("ability_point_cost")
            .cum_sum()
            .over("match_id", "account_id")
            .alias("ability_points_spent")
        )
        .pipe(_with_hero_era)
    )
    reward_rows = [
        {
            "era_from": era_from,
            "hero_id": hero.id,
            "reward_n": n,
            "level": info.level,
            "required_souls": info.required_souls,
            "reward": reward,
        }
        for era_from, _build, hero in _hero_by_era()
        for reward in ("ability_unlocks", "ability_points")
        for n, info in enumerate(
            (info for info in hero.levels if reward in info.currencies),
            start=1,
        )
    ]
    rewards = pl.LazyFrame(
        reward_rows,
        schema={
            "era_from": pl.Datetime("us", "UTC"),
            "hero_id": pl.Int64,
            "reward": pl.String,
            "reward_n": pl.Int64,
            "level": pl.Int64,
            "required_souls": pl.Int64,
        },
    )
    unlocks = rewards.filter(pl.col("reward") == "ability_unlocks")
    points = rewards.filter(pl.col("reward") == "ability_points")

    return (
        events.join(
            unlocks,
            left_on=["hero_id", "era_from", "ability_unlock_n"],
            right_on=["hero_id", "era_from", "reward_n"],
            how="left",
        )
        .join(
            points,
            left_on=["hero_id", "era_from", "ability_points_spent"],
            right_on=["hero_id", "era_from", "reward_n"],
            how="left",
            suffix="_point",
        )
        .with_columns(
            pl.when(pl.col("ability_point_cost") > 0)
            .then(pl.col("level_point"))
            .otherwise(pl.col("level"))
            .alias("level"),
            pl.when(pl.col("ability_point_cost") > 0)
            .then(pl.col("required_souls_point"))
            .otherwise(pl.col("required_souls"))
            .alias("required_souls"),
            pl.when(pl.col("ability_point_cost") > 0)
            .then(pl.col("reward_point"))
            .otherwise(pl.col("reward"))
            .alias("reward"),
        )
        .select(
            "match_id",
            "account_id",
            "hero",
            "won",
            "day",
            "duration_s",
            "game_time_s",
            "ability",
            "ability_class",
            "ability_upgrade_n",
            "ability_event_n",
            "ability_point_cost",
            "ability_points_spent",
            "ability_unlock_n",
            "reward",
            "level",
            "required_souls",
        )
        .sort("match_id", "account_id", "game_time_s")
    )


def item_buys(
    item: str | None = None,
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    tier: int | None = None,
) -> pl.LazyFrame:
    """Item purchases by the player with a buy_n order column, named items only.

    - pass item (a display name) to keep one item, None keeps every purchase
    - pass tier to keep one shop tier, buy_n still counts every purchase in the match
    """
    accounts = config.config_accounts() if accounts is None else list(accounts)

    if not accounts:
        msg = "no accounts: pass accounts= or fill in accounts in config.toml"
        raise ValueError(msg)

    buys = (
        scan("item_events", parquet_dir)
        .filter(pl.col("account_id").is_in(accounts), pl.col("item").is_not_null())
        .with_columns(
            pl.col("game_time_s").rank("ordinal").over("match_id", "account_id").alias("buy_n")
        )
    )

    if item is not None:
        buys = buys.filter(pl.col("item") == item)

    if tier is not None:
        buys = buys.filter(pl.col("tier") == tier)

    return buys
