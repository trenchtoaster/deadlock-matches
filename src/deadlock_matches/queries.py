"""Reusable polars queries over the exported parquet tables."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import polars.selectors as cs

from deadlock_matches import config, export, schemas
from deadlock_matches.assets import abilities, heroes, history, items, store
from deadlock_matches.assets import skill_rating as sr

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

_ERA_SENTINEL = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)


def scan(table: str, parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Lazily scan one exported table by name (one of schemas.TABLES).

    parquet_dir defaults to the standard export directory, here and in every
    query below.
    """
    if table not in schemas.TABLES:
        known = ", ".join(schemas.TABLES)
        msg = f"Unknown table {table!r}, tables: {known}"
        raise ValueError(msg)

    parquet_dir = export.PARQUET_DIR if parquet_dir is None else parquet_dir

    if schemas.is_partitioned(table):
        directory = schemas.partition_dir(table, parquet_dir)

        if directory.is_dir():
            return pl.scan_parquet(str(directory / "*.parquet"))

    return pl.scan_parquet(schemas.table_path(table, parquet_dir))


def table_exists(table: str, parquet_dir: str | Path | None = None) -> bool:
    """Whether a table is on disk, as a month-partitioned directory or a single parquet file."""
    if table not in schemas.TABLES:
        known = ", ".join(schemas.TABLES)
        msg = f"Unknown table {table!r}, tables: {known}"
        raise ValueError(msg)

    parquet_dir = export.PARQUET_DIR if parquet_dir is None else parquet_dir

    if schemas.is_partitioned(table):
        directory = schemas.partition_dir(table, parquet_dir)

        if directory.is_dir() and next(directory.glob("*.parquet"), None) is not None:
            return True

    return schemas.table_path(table, parquet_dir).exists()


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
        .join_asof(prepared, left_on=on, right_on="_join_from", by=by_cols, strategy="backward")
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


def my_games(
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    tz: str | None = None,
) -> pl.LazyFrame:
    """Build one row per match the player appeared in, joined to match details.

    - adds start_local and day columns so grouping by day or week uses
      the local date, not the UTC date
    - accounts (Steam32 account IDs) and tz default to config.toml and
      the detected zone
    """
    accounts = config.config_accounts() if accounts is None else list(accounts)

    if not accounts:
        msg = "no accounts: pass accounts= or fill in accounts in config.toml"
        raise ValueError(msg)

    tz = config.config_timezone() if tz is None else tz

    return (
        scan("players", parquet_dir)
        .filter(pl.col("account_id").is_in(accounts))
        .join(scan("matches", parquet_dir), on="match_id")
        .with_columns(pl.col("start_time").dt.convert_time_zone(tz).alias("start_local"))
        .with_columns(pl.col("start_local").dt.date().alias("day"))
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
            pl.col("category") != "total",
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
    the denominator for the item percent of hero damage.
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
            pl.int_range(1, pl.len() + 1).over("match_id", "account_id").alias("buy_n"),
            pl.int_range(1, pl.len() + 1)
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

    return (
        games.select("match_id", "account_id", "hero", "won", "duration_s", "start_time")
        .join(_item_buys(windows), on=["match_id", "account_id"], how="left")
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

    games = (
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

    if days is not None:
        kept = games.get_column("day").unique().sort().tail(days)
        games = games.filter(pl.col("day").is_in(kept.implode()))

    return games


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


def _local_day(frame: pl.LazyFrame, parquet_dir: str | Path | None, tz: str | None) -> pl.LazyFrame:
    """Join match start_time and add start_local/day columns in the given zone."""
    tz = config.config_timezone() if tz is None else tz

    return (
        frame.join(scan("matches", parquet_dir).select("match_id", "start_time"), on="match_id")
        .with_columns(pl.col("start_time").dt.convert_time_zone(tz).alias("start_local"))
        .with_columns(pl.col("start_local").dt.date().alias("day"))
    )


def hero_damage(
    stat: str = "damage",
    parquet_dir: str | Path | None = None,
    tz: str | None = None,
) -> pl.LazyFrame:
    """Damage detail rows against hero targets, safe to sum by source.

    - drops `total` rows, which duplicate the gun/ability/item detail rows
    - drops non-player targets, so farm damage never inflates a source
    - adds `hero` and `start_local`/`day` columns for the dealer, so filtering
      by hero, account, or day needs no extra joins

    stat picks which figure to keep: damage, healing, mitigated, ...
    """
    dealers = scan("players", parquet_dir).select(
        "match_id",
        pl.col("account_id").alias("dealer_account_id"),
        "hero",
    )
    detail = (
        scan("damage", parquet_dir)
        .filter(
            pl.col("stat") == stat,
            pl.col("category") != "total",
            pl.col("target_account_id").is_not_null(),
        )
        .join(dealers, on=["match_id", "dealer_account_id"], how="left")
    )

    return _local_day(detail, parquet_dir, tz)


def damage_by_source(
    hero: str,
    accounts: Sequence[int] | None = None,
    matches: Sequence[int] | None = None,
    parquet_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Total damage to heroes by source across your games of a hero.

    - one row per source (gun, ability, item proc), summed over every game
    - per_min for gun and ability rows divides by your minutes on the hero,
      item rows divide by the minutes the item was owned, so a late buy
      is not diluted by the minutes before it existed
    - an item source with no buy on record keeps a null per_min
    - matches limits to specific match ids, like scoping to one game
    """
    accounts = config.config_accounts() if accounts is None else list(accounts)

    if not accounts:
        msg = "no accounts: pass accounts= or fill in accounts in config.toml"
        raise ValueError(msg)

    predicate = (pl.col("hero") == hero) & pl.col("dealer_account_id").is_in(accounts)

    if matches is not None:
        predicate = predicate & pl.col("match_id").is_in(list(matches))

    rows = (
        hero_damage(parquet_dir=parquet_dir)
        .filter(predicate)
        .select("match_id", "source_name", "source_class", "delivery", "damage")
        .collect()
    )

    if rows.is_empty():
        msg = f"no damage rows for {hero} on accounts {accounts}"
        raise ValueError(msg)

    match_ids = rows.get_column("match_id").unique()
    minutes = (
        scan("matches", parquet_dir)
        .filter(pl.col("match_id").is_in(match_ids.implode()))
        .select(pl.col("duration_s").sum())
        .collect()
        .item()
        / 60
    )
    grand = rows.get_column("damage").sum()
    owned = _owned_minutes(rows, accounts, match_ids, parquet_dir)
    owned_min = (
        pl.col("source_class").replace_strict(owned, default=None, return_dtype=pl.Float64)
        if owned
        else pl.lit(None, dtype=pl.Float64)
    )

    return (
        rows.group_by("source_name", "source_class", "delivery")
        .agg(
            pl.col("damage").sum().alias("total"),
            pl.col("match_id").n_unique().alias("games"),
        )
        .with_columns(
            pl.when(pl.col("delivery").str.ends_with("_proc"))
            .then((pl.col("total") / owned_min).round(1))
            .otherwise((pl.col("total") / minutes).round(1))
            .alias("per_min"),
            (pl.col("total") / grand * 100).round(1).alias("percent"),
        )
        .select("games", "source_name", "delivery", "total", "per_min", "percent")
        .sort("total", descending=True)
    )


def _owned_minutes(
    rows: pl.DataFrame,
    accounts: Sequence[int],
    match_ids: pl.Series,
    parquet_dir: str | Path | None,
) -> dict[str, float]:
    """Sum the minutes each item damage source was owned across the given games.

    - keyed by source_class, only the item proc sources in rows appear
    - ownership windows come from the buys, like the item command: a sold or
      consumed buy ends at sold_time_s, a kept buy at the end of the match
    - an item source whose class resolves to no known item is left out
    """
    classes = (
        rows.filter(pl.col("delivery").str.ends_with("_proc"))
        .get_column("source_class")
        .unique()
        .to_list()
    )
    ids = {}

    for source_class in classes:
        item = items.item_by_class_name(source_class)

        if item is not None:
            ids[item.id] = source_class

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


def damage_game_records(
    hero: str,
    accounts: Sequence[int] | None = None,
    parquet_dir: str | Path | None = None,
    tz: str | None = None,
    days: int | None = None,
    since: str | dt.date | None = None,
) -> pl.DataFrame:
    """Take one row per game of a hero with the damage to heroes split by delivery.

    - total sums every detail row, gun / abilities / items sum the matching
      delivery rows, items counts gun and spirit procs together
    - gun_pct, abilities_pct, and items_pct are shares of total, all null
      in a game with no hero damage
    - days and since filter on the local day, like lane_records
    """
    accounts = config.config_accounts() if accounts is None else list(accounts)
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

    mine = mine.select(
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

    split = (
        hero_damage(parquet_dir=parquet_dir, tz=tz)
        .select("match_id", pl.col("dealer_account_id").alias("account_id"), "delivery", "damage")
        .group_by("match_id", "account_id")
        .agg(
            pl.col("damage").sum().alias("total"),
            pl.col("damage").filter(pl.col("delivery") == "gun").sum().alias("gun"),
            pl.col("damage").filter(pl.col("delivery") == "ability").sum().alias("abilities"),
            pl.col("damage").filter(pl.col("delivery").str.ends_with("_proc")).sum().alias("items"),
        )
    )

    games = (
        mine.join(split, on=["match_id", "account_id"], how="left")
        .with_columns(pl.col("total", "gun", "abilities", "items").fill_null(0))
        .with_columns(
            pl.when(pl.col("total") > 0)
            .then((pl.col(part) / pl.col("total") * 100).round(1))
            .alias(f"{part}_pct")
            for part in ("gun", "abilities", "items")
        )
        .sort("start_local", "match_id")
        .collect()
    )

    if games.is_empty():
        msg = f"no games of {hero} on accounts {accounts}"
        raise ValueError(msg)

    return games


def souls_by_source(
    hero: str,
    accounts: Sequence[int] | None = None,
    matches: Sequence[int] | None = None,
    parquet_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Total souls by income source across your games of a hero.

    - souls sums the guaranteed and orb portions, the in game figure
    - orb_share is the deniable orb portion you secured, percent is share of the total
    - matches limits to specific match ids, like scoping to one game
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
        .collect()
    )

    if finals.is_empty():
        msg = f"no soul_sources rows for {hero} on accounts {accounts}"
        raise ValueError(msg)

    total = int((finals.get_column("souls") + finals.get_column("souls_orbs")).sum())

    return (
        finals.group_by("source_name")
        .agg(
            (pl.col("souls") + pl.col("souls_orbs")).sum().alias("souls"),
            pl.col("souls_orbs").sum().alias("secured_orbs"),
            pl.len().alias("games"),
        )
        .with_columns(
            (pl.col("souls") / total * 100).round(1).alias("percent"),
            (pl.col("secured_orbs") / pl.col("souls") * 100).round(1).alias("orb_share"),
        )
        .select("games", "source_name", "souls", "secured_orbs", "percent", "orb_share")
        .sort("souls", descending=True)
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
        frame = frame.group_by("match_id", "account_id", "group", "stat").agg(
            pl.col("value").sort_by("time_stamp_s").last()
        )

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
            pl.col("category") != "total",
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
            pl.col("category") != "total",
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


SOUL_COMPOSITES = {
    "farm": ("troopers", "jungle", "breakables", "treasure", "denies"),
    "troopers": ("troopers",),
    "jungle": ("jungle",),
    "breakables": ("breakables",),
    "rift_urn": ("treasure",),
    "deny_souls": ("denies",),
    "combat": ("players", "assists"),
    "objectives": ("bosses",),
    "catch_up": ("team_bonus",),
    "other": ("trophy_collector", "cultist_sacrifice", "assassinate", "goose_egg"),
}

COMPARE_STATS = (
    "souls",
    "farm",
    "troopers",
    "jungle",
    "breakables",
    "combat",
    "objectives",
    "catch_up",
    "other",
    "kills",
    "deaths",
    "assists",
    "damage",
    "damage_taken",
    "obj_damage",
    "healing",
    "heal_prevented",
    "creeps",
    "neutrals",
    "denies",
)

_KEYS = ["match_id", "account_id"]


def _bucket(column: str, interval_s: int) -> pl.Expr:
    """Assign a time column to its interval number, matching match_intervals."""
    return ((pl.col(column) - 1) // interval_s).clip(0).cast(pl.Int64).alias("interval")


def _interval_grid(
    games: pl.LazyFrame, interval_s: int, parquet_dir: str | Path | None
) -> pl.LazyFrame:
    """Lay out one row per full interval per game."""
    return (
        games.select(_KEYS)
        .unique()
        .join(scan("matches", parquet_dir).select("match_id", "duration_s"), on="match_id")
        .select(
            *_KEYS,
            pl.int_ranges(0, pl.col("duration_s") // interval_s).alias("interval"),
        )
        .explode("interval", empty_as_null=False)
    )


def _column_gains(
    games: pl.LazyFrame, column: str, interval_s: int, parquet_dir: str | Path | None
) -> pl.LazyFrame:
    """Diff one cumulative stats column into per interval gains per game."""
    cumulative = (
        scan("stats", parquet_dir)
        .join(games.select(_KEYS).unique(), on=_KEYS)
        .select(*_KEYS, _bucket("time_stamp_s", interval_s), pl.col(column).alias("value"))
        .group_by(*_KEYS, "interval")
        .agg(pl.col("value").max())
    )

    return (
        _interval_grid(games, interval_s, parquet_dir)
        .join(cumulative, on=[*_KEYS, "interval"], how="left")
        .sort(*_KEYS, "interval")
        .with_columns(pl.col("value").forward_fill().over(_KEYS).fill_null(0))
        .with_columns(
            (pl.col("value") - pl.col("value").shift(1).over(_KEYS).fill_null(0)).alias("gain")
        )
        .select(*_KEYS, "interval", "gain")
    )


def _source_gains(
    games: pl.LazyFrame,
    sources: Sequence[str],
    interval_s: int,
    parquet_dir: str | Path | None,
) -> pl.LazyFrame:
    """Diff a set of soul sources into per interval gains per game.

    Each source samples on its own clock, so every source forward-fills
    separately before the gains are summed.
    """
    per_source = (
        scan("soul_sources", parquet_dir)
        .join(games.select(_KEYS).unique(), on=_KEYS)
        .filter(pl.col("source_name").is_in(list(sources)))
        .select(
            *_KEYS,
            "source_name",
            _bucket("time_stamp_s", interval_s),
            (pl.col("souls") + pl.col("souls_orbs")).alias("value"),
        )
        .group_by(*_KEYS, "source_name", "interval")
        .agg(pl.col("value").max())
    )

    return (
        _interval_grid(games, interval_s, parquet_dir)
        .join(pl.LazyFrame({"source_name": list(sources)}), how="cross")
        .join(per_source, on=[*_KEYS, "source_name", "interval"], how="left")
        .sort(*_KEYS, "source_name", "interval")
        .with_columns(pl.col("value").forward_fill().over([*_KEYS, "source_name"]).fill_null(0))
        .with_columns(
            (
                pl.col("value")
                - pl.col("value").shift(1).over([*_KEYS, "source_name"]).fill_null(0)
            ).alias("gain")
        )
        .group_by(*_KEYS, "interval")
        .agg(pl.col("gain").sum())
    )


def _event_gains(
    games: pl.LazyFrame, interval_s: int, parquet_dir: str | Path | None, *, kills: bool
) -> pl.LazyFrame:
    """Count deaths table rows per interval per game, as victim or as killer."""
    deaths = scan("deaths", parquet_dir)

    if kills:
        deaths = (
            deaths.drop("account_id")
            .drop_nulls("killer_account_id")
            .rename({"killer_account_id": "account_id"})
        )

    events = (
        deaths.join(games.select(_KEYS).unique(), on=_KEYS)
        .select(*_KEYS, _bucket("game_time_s", interval_s))
        .group_by(*_KEYS, "interval")
        .agg(pl.len().cast(pl.Int64).alias("gain"))
    )

    return (
        _interval_grid(games, interval_s, parquet_dir)
        .join(events, on=[*_KEYS, "interval"], how="left")
        .with_columns(pl.col("gain").fill_null(0))
        .select(*_KEYS, "interval", "gain")
    )


def compare_intervals(
    games: pl.LazyFrame,
    stat: str,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
) -> pl.LazyFrame:
    """Split every given game into per interval gains of one compare stat.

    - full intervals only, so a game contributes exactly while it lasts
    - same bucket rule as match_intervals: a gain lands in the interval
      holding the sample that recorded it
    - kills and deaths count deaths table rows, snapshot counts drift
    - soul composites (farm, combat, ...) sum their sources, each source
      forward-filled on its own clock
    """
    if stat in ("kills", "deaths"):
        return _event_gains(games, interval_s, parquet_dir, kills=stat == "kills")

    if stat in INTERVAL_STATS:
        return _column_gains(games, INTERVAL_STATS[stat], interval_s, parquet_dir)

    if stat in SOUL_COMPOSITES:
        return _source_gains(games, SOUL_COMPOSITES[stat], interval_s, parquet_dir)

    known = ", ".join(COMPARE_STATS)
    msg = f"Unknown compare stat {stat!r}, one of: {known}"
    raise ValueError(msg)


def game_totals(
    games: pl.LazyFrame, stat: str, parquet_dir: str | Path | None = None
) -> pl.LazyFrame:
    """Total one compare stat over each whole game, one row per game."""
    with_duration = (
        games.select(_KEYS)
        .unique()
        .join(scan("matches", parquet_dir).select("match_id", "duration_s"), on="match_id")
    )

    if stat in ("kills", "deaths"):
        deaths = scan("deaths", parquet_dir)

        if stat == "kills":
            deaths = (
                deaths.drop("account_id")
                .drop_nulls("killer_account_id")
                .rename({"killer_account_id": "account_id"})
            )

        totals = (
            deaths.join(games.select(_KEYS).unique(), on=_KEYS)
            .group_by(_KEYS)
            .agg(pl.len().cast(pl.Int64).alias("total"))
        )

    elif stat in INTERVAL_STATS:
        totals = (
            scan("stats", parquet_dir)
            .join(games.select(_KEYS).unique(), on=_KEYS)
            .group_by(_KEYS)
            .agg(pl.col(INTERVAL_STATS[stat]).max().alias("total"))
        )

    elif stat in SOUL_COMPOSITES:
        totals = (
            scan("soul_sources", parquet_dir)
            .join(games.select(_KEYS).unique(), on=_KEYS)
            .filter(pl.col("source_name").is_in(list(SOUL_COMPOSITES[stat])))
            .group_by(*_KEYS, "source_name")
            .agg((pl.col("souls") + pl.col("souls_orbs")).max().alias("total"))
            .group_by(_KEYS)
            .agg(pl.col("total").sum())
        )

    else:
        known = ", ".join(COMPARE_STATS)
        msg = f"Unknown compare stat {stat!r}, one of: {known}"
        raise ValueError(msg)

    return (
        with_duration.join(totals, on=_KEYS, how="left")
        .with_columns(pl.col("total").fill_null(0))
        .filter(pl.col("duration_s") > 0)
        .select(*_KEYS, "total", "duration_s")
    )


def game_rates(
    games: pl.LazyFrame, stat: str, parquet_dir: str | Path | None = None
) -> pl.LazyFrame:
    """Compute the whole game rate per minute of one compare stat, one row per game."""
    return game_totals(games, stat, parquet_dir).select(
        *_KEYS, (pl.col("total") * 60 / pl.col("duration_s")).alias("rate")
    )


def cumulative_at(
    games: pl.LazyFrame,
    stat: str,
    marks_s: Sequence[int],
    parquet_dir: str | Path | None = None,
) -> pl.LazyFrame:
    """Read the cumulative value of one compare stat at each mark, per game.

    - the value is the last recorded sample at or before the mark
    - only games that reach a mark contribute rows for it
    """
    marks = pl.LazyFrame({"mark_s": sorted(set(marks_s))}, schema={"mark_s": pl.Int64})
    reached = (
        games.select(_KEYS)
        .unique()
        .join(scan("matches", parquet_dir).select("match_id", "duration_s"), on="match_id")
        .join(marks, how="cross")
        .filter(pl.col("duration_s") >= pl.col("mark_s"))
        .select(*_KEYS, "mark_s")
    )

    if stat in INTERVAL_STATS:
        values = (
            scan("stats", parquet_dir)
            .join(games.select(_KEYS).unique(), on=_KEYS)
            .select(*_KEYS, "time_stamp_s", pl.col(INTERVAL_STATS[stat]).alias("value"))
            .join(marks, how="cross")
            .filter(pl.col("time_stamp_s") <= pl.col("mark_s"))
            .group_by(*_KEYS, "mark_s")
            .agg(pl.col("value").max())
        )

    elif stat in SOUL_COMPOSITES:
        values = (
            scan("soul_sources", parquet_dir)
            .join(games.select(_KEYS).unique(), on=_KEYS)
            .filter(pl.col("source_name").is_in(list(SOUL_COMPOSITES[stat])))
            .select(
                *_KEYS,
                "source_name",
                "time_stamp_s",
                (pl.col("souls") + pl.col("souls_orbs")).alias("value"),
            )
            .join(marks, how="cross")
            .filter(pl.col("time_stamp_s") <= pl.col("mark_s"))
            .group_by(*_KEYS, "source_name", "mark_s")
            .agg(pl.col("value").max())
            .group_by(*_KEYS, "mark_s")
            .agg(pl.col("value").sum())
        )

    else:
        known = ", ".join(k for k in COMPARE_STATS if k not in ("kills", "deaths"))
        msg = f"Unknown cumulative stat {stat!r}, one of: {known}"
        raise ValueError(msg)

    return (
        reached.join(values, on=[*_KEYS, "mark_s"], how="left")
        .with_columns(pl.col("value").fill_null(0))
        .select(*_KEYS, "mark_s", "value")
    )


INTERVAL_STATS = {
    "souls": "net_worth",
    "assists": "assists",
    "damage": "player_damage",
    "damage_taken": "player_damage_taken",
    "obj_damage": "boss_damage",
    "healing": "player_healing",
    "heal_prevented": "heal_prevented",
    "creeps": "creep_kills",
    "neutrals": "neutral_kills",
    "denies": "denies",
}

INTERVAL_COLUMNS = (
    "souls",
    "kills",
    "deaths",
    "assists",
    "damage",
    "damage_taken",
    "obj_damage",
    "healing",
    "heal_prevented",
    "creeps",
    "neutrals",
    "denies",
)


def match_intervals(
    match_id: int,
    account_id: int,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Split the match for one player into intervals of stat gains.

    - snapshots are cumulative, so the gain in an interval is its last snapshot
      minus the last snapshot of the interval before it
    - intervals without a snapshot inherit the previous values and show zero gains
    - coverage ends at the last snapshot, and the last interval ends at the
      match end, so it can be shorter than the rest
    - kills and deaths are counted from the deaths table, since the snapshot
      fields drift from the match screen
    - souls_min is the souls gained per minute inside the interval
    """
    duration = (
        scan("matches", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("duration_s")
        .collect()
    )

    if duration.is_empty():
        msg = f"match {match_id} not in the tables"
        raise ValueError(msg)

    fields = list(INTERVAL_STATS.values())
    snaps = (
        scan("stats", parquet_dir)
        .filter(pl.col("match_id") == match_id, pl.col("account_id") == account_id)
        .select("time_stamp_s", *fields)
        .collect()
    )

    if snaps.is_empty():
        msg = f"account {account_id} has no snapshots in match {match_id}"
        raise ValueError(msg)

    duration_s = int(duration.item())
    bucket = ((pl.col("time_stamp_s") - 1) // interval_s).clip(0).cast(pl.Int64).alias("interval")
    cumulative = snaps.with_columns(bucket).group_by("interval").agg(pl.col(fields).max())

    mine = pl.col("account_id") == account_id
    killed = (pl.col("killer_account_id") == account_id).fill_null(value=False)
    events = (
        scan("deaths", parquet_dir)
        .filter(pl.col("match_id") == match_id, mine | killed)
        .select(
            ((pl.col("game_time_s") - 1) // interval_s).clip(0).cast(pl.Int64).alias("interval"),
            killed.alias("kill"),
            mine.alias("death"),
        )
        .group_by("interval")
        .agg(
            pl.col("kill").sum().cast(pl.Int64).alias("kills"),
            pl.col("death").sum().cast(pl.Int64).alias("deaths"),
        )
        .collect()
    )

    n = cumulative.select(pl.col("interval").max()).item() + 1
    gains = (
        pl.DataFrame({"interval": range(n)}, schema={"interval": pl.Int64})
        .join(cumulative, on="interval", how="left")
        .sort("interval")
        .with_columns(pl.col(fields).fill_null(strategy="forward").fill_null(0))
        .with_columns(pl.col(f) - pl.col(f).shift(1).fill_null(0) for f in fields)
        .join(events, on="interval", how="left")
        .with_columns(pl.col("kills", "deaths").fill_null(0))
        .sort("interval")
    )

    return (
        gains.rename({raw: name for name, raw in INTERVAL_STATS.items() if raw != name})
        .with_columns(
            (pl.col("interval") * interval_s).alias("start_s"),
            ((pl.col("interval") + 1) * interval_s).clip(upper_bound=duration_s).alias("end_s"),
        )
        .with_columns(
            (pl.col("souls") * 60 / (pl.col("end_s") - pl.col("start_s"))).alias("souls_min")
        )
        .select("start_s", "end_s", *INTERVAL_COLUMNS, "souls_min")
    )


def damage_intervals(
    match_id: int,
    account_id: int,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
    stat: str = "damage",
) -> pl.DataFrame:
    """Split the damage to heroes for one player into per source gains per interval.

    - detail rows only, the match screen totals are excluded
    - samples in damage_sources are sparse (about every three minutes), so a
      gain lands in the interval holding the sample that recorded it
    - one row per source per interval, sources ordered by match total
    - delivery comes along for gun/ability/item grouping
    """
    duration = (
        scan("matches", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("duration_s")
        .collect()
    )

    if duration.is_empty():
        msg = f"match {match_id} not in the tables"
        raise ValueError(msg)

    samples = (
        scan("damage_sources", parquet_dir)
        .filter(
            pl.col("match_id") == match_id,
            pl.col("dealer_account_id") == account_id,
            pl.col("stat") == stat,
            pl.col("vs_heroes"),
            pl.col("category") != "total",
        )
        .select("source_name", "delivery", "time_stamp_s", "damage")
        .collect()
    )

    if samples.is_empty():
        msg = f"account {account_id} has no {stat} to heroes in match {match_id}"
        raise ValueError(msg)

    duration_s = int(duration.item())
    bucket = ((pl.col("time_stamp_s") - 1) // interval_s).clip(0).cast(pl.Int64).alias("interval")
    cumulative = (
        samples.with_columns(bucket).group_by("source_name", "interval").agg(pl.col("damage").max())
    )

    n = cumulative.select(pl.col("interval").max()).item() + 1
    grid = (
        samples.select("source_name", "delivery")
        .unique()
        .join(pl.DataFrame({"interval": range(n)}, schema={"interval": pl.Int64}), how="cross")
    )

    gains = (
        grid.join(cumulative, on=["source_name", "interval"], how="left")
        .sort("source_name", "interval")
        .with_columns(
            pl.col("damage").fill_null(strategy="forward").fill_null(0).over("source_name")
        )
        .with_columns(pl.col("damage") - pl.col("damage").shift(1).fill_null(0).over("source_name"))
        .with_columns(pl.col("damage").sum().over("source_name").alias("total"))
    )

    return (
        gains.with_columns(
            (pl.col("interval") * interval_s).alias("start_s"),
            ((pl.col("interval") + 1) * interval_s).clip(upper_bound=duration_s).alias("end_s"),
        )
        .sort(["total", "source_name", "interval"], descending=[True, False, False])
        .select("source_name", "delivery", "start_s", "end_s", "damage", "total")
    )


def enemy_damage_intervals(
    match_id: int,
    account_id: int,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
    *,
    dealt: bool = False,
) -> pl.DataFrame:
    """Split the damage exchanged with each enemy hero into gains per interval.

    - the damage every enemy dealt to this player, or with dealt=True the
      damage this player dealt to each enemy
    - detail rows between hero dealers and hero targets only
    - samples in damage_targets are sparse (about every three minutes), so each
      source forward fills on its own clock before the per enemy sum
    - one row per enemy per interval, enemies ordered by match total
    """
    duration = (
        scan("matches", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("duration_s")
        .collect()
    )

    if duration.is_empty():
        msg = f"match {match_id} not in the tables"
        raise ValueError(msg)

    mine = "dealer_account_id" if dealt else "target_account_id"
    other = "target_account_id" if dealt else "dealer_account_id"
    samples = (
        scan("damage_targets", parquet_dir)
        .filter(
            pl.col("match_id") == match_id,
            pl.col(mine) == account_id,
            pl.col(other).is_not_null(),
            pl.col("stat") == "damage",
            pl.col("category") != "total",
        )
        .select(pl.col(other).alias("enemy_account_id"), "source_class", "time_stamp_s", "damage")
        .collect()
    )

    if samples.is_empty():
        direction = "dealt to" if dealt else "taken from"
        msg = f"account {account_id} has no damage {direction} heroes in match {match_id}"
        raise ValueError(msg)

    duration_s = int(duration.item())
    bucket = ((pl.col("time_stamp_s") - 1) // interval_s).clip(0).cast(pl.Int64).alias("interval")
    keys = ["enemy_account_id", "source_class"]
    cumulative = (
        samples.with_columns(bucket).group_by(*keys, "interval").agg(pl.col("damage").max())
    )

    n = cumulative.select(pl.col("interval").max()).item() + 1
    grid = (
        samples.select(keys)
        .unique()
        .join(pl.DataFrame({"interval": range(n)}, schema={"interval": pl.Int64}), how="cross")
    )

    gains = (
        grid.join(cumulative, on=[*keys, "interval"], how="left")
        .sort(*keys, "interval")
        .with_columns(pl.col("damage").fill_null(strategy="forward").fill_null(0).over(keys))
        .with_columns(pl.col("damage") - pl.col("damage").shift(1).fill_null(0).over(keys))
        .group_by("enemy_account_id", "interval")
        .agg(pl.col("damage").sum())
        .with_columns(pl.col("damage").sum().over("enemy_account_id").alias("total"))
    )

    in_match = (
        scan("players", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select(pl.col("account_id").alias("enemy_account_id"), pl.col("hero").alias("enemy"))
        .collect()
    )

    return (
        gains.join(in_match, on="enemy_account_id", how="left")
        .with_columns(
            (pl.col("interval") * interval_s).alias("start_s"),
            ((pl.col("interval") + 1) * interval_s).clip(upper_bound=duration_s).alias("end_s"),
        )
        .sort(["total", "enemy", "interval"], descending=[True, False, False])
        .select("enemy", "enemy_account_id", "start_s", "end_s", "damage", "total")
    )


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


def soul_intervals(
    match_id: int,
    account_id: int,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Split the souls for one player into per source gains per interval.

    - value is souls + souls_orbs, the in game per source number
    - soul_sources samples about every three minutes, so a gain lands in the
      interval holding the sample that recorded it
    - one row per source per interval, sources with any souls, ordered by total
    """
    duration = (
        scan("matches", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("duration_s")
        .collect()
    )

    if duration.is_empty():
        msg = f"match {match_id} not in the tables"
        raise ValueError(msg)

    samples = (
        scan("soul_sources", parquet_dir)
        .filter(pl.col("match_id") == match_id, pl.col("account_id") == account_id)
        .select(
            "source_name", "time_stamp_s", (pl.col("souls") + pl.col("souls_orbs")).alias("souls")
        )
        .collect()
    )

    if samples.is_empty():
        msg = f"account {account_id} has no soul sources in match {match_id}"
        raise ValueError(msg)

    duration_s = int(duration.item())
    bucket = ((pl.col("time_stamp_s") - 1) // interval_s).clip(0).cast(pl.Int64).alias("interval")
    cumulative = (
        samples.with_columns(bucket).group_by("source_name", "interval").agg(pl.col("souls").max())
    )

    n = cumulative.select(pl.col("interval").max()).item() + 1
    grid = (
        samples.select("source_name")
        .unique()
        .join(pl.DataFrame({"interval": range(n)}, schema={"interval": pl.Int64}), how="cross")
    )

    gains = (
        grid.join(cumulative, on=["source_name", "interval"], how="left")
        .sort("source_name", "interval")
        .with_columns(
            pl.col("souls").fill_null(strategy="forward").fill_null(0).over("source_name")
        )
        .with_columns(pl.col("souls") - pl.col("souls").shift(1).fill_null(0).over("source_name"))
        .with_columns(pl.col("souls").sum().over("source_name").alias("total"))
    )

    return (
        gains.with_columns(
            (pl.col("interval") * interval_s).alias("start_s"),
            ((pl.col("interval") + 1) * interval_s).clip(upper_bound=duration_s).alias("end_s"),
        )
        .filter(pl.col("total") > 0)
        .sort(["total", "source_name", "interval"], descending=[True, False, False])
        .select("source_name", "start_s", "end_s", "souls", "total")
    )


def source_intervals(
    games: pl.DataFrame | pl.LazyFrame,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
    stat: str = "damage",
) -> pl.LazyFrame:
    """Split damage or healing by source and interval for multiple players.

    - the many-game version of damage_intervals, same semantics per player:
      detail rows on hero targets only, a gain lands in the interval holding
      the sample that recorded it, forward fill carries the cumulative value
      of a source
      across intervals without a sample
    - games needs match_id and account_id columns, anything else is ignored,
      and player games without matching rows just contribute nothing
    - full marks intervals that run the whole interval_s, the last interval
      ends at the match end so it can be shorter
    """
    keys = ["match_id", "account_id"]
    wanted = games.lazy().select(keys).unique()
    bucket = ((pl.col("time_stamp_s") - 1) // interval_s).clip(0).cast(pl.Int64).alias("interval")
    samples = (
        scan("damage_sources", parquet_dir)
        .rename({"dealer_account_id": "account_id"})
        .join(wanted, on=keys)
        .filter(pl.col("stat") == stat, pl.col("vs_heroes"), pl.col("category") != "total")
        .with_columns(bucket)
        .group_by(*keys, "source_name", "delivery", "interval")
        .agg(pl.col("damage").max())
    )

    sources = samples.select(*keys, "source_name", "delivery").unique()
    spans = samples.group_by(keys).agg(pl.col("interval").max().alias("n"))
    grid = (
        sources.join(spans, on=keys)
        .with_columns(pl.int_ranges(0, pl.col("n") + 1).alias("interval"))
        .explode("interval", empty_as_null=False)
        .drop("n")
    )
    durations = scan("matches", parquet_dir).select("match_id", "duration_s")

    return (
        grid.join(samples, on=[*keys, "source_name", "delivery", "interval"], how="left")
        .sort(*keys, "source_name", "interval")
        .with_columns(
            pl.col("damage").fill_null(strategy="forward").fill_null(0).over(*keys, "source_name")
        )
        .with_columns(
            pl.col("damage") - pl.col("damage").shift(1).fill_null(0).over(*keys, "source_name")
        )
        .with_columns(pl.col("damage").sum().over(*keys, "source_name").alias("total"))
        .join(durations, on="match_id")
        .with_columns(
            (pl.col("interval") * interval_s).alias("start_s"),
            ((pl.col("interval") + 1) * interval_s)
            .clip(upper_bound=pl.col("duration_s"))
            .alias("end_s"),
        )
        .with_columns((pl.col("end_s") - pl.col("start_s") == interval_s).alias("full"))
        .sort(
            [*keys, "total", "source_name", "interval"],
            descending=[False, False, True, False, False],
        )
        .select(*keys, "source_name", "delivery", "start_s", "end_s", "full", "damage", "total")
    )


def team_intervals(
    match_id: int,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Split a match into intervals of souls gained per team, with the running lead.

    - the cumulative net worth of each player carries forward through intervals
      without a snapshot, so a gap for one player never dents the team total
    - lead is the team 0 total minus the team 1 total at the interval end
    """
    duration = (
        scan("matches", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("duration_s")
        .collect()
    )

    if duration.is_empty():
        msg = f"match {match_id} not in the tables"
        raise ValueError(msg)

    snaps = (
        scan("stats", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("account_id", "time_stamp_s", "net_worth")
        .collect()
    )

    if snaps.is_empty():
        msg = f"match {match_id} has no snapshots"
        raise ValueError(msg)

    duration_s = int(duration.item())
    bucket = ((pl.col("time_stamp_s") - 1) // interval_s).clip(0).cast(pl.Int64).alias("interval")
    cumulative = (
        snaps.with_columns(bucket).group_by("account_id", "interval").agg(pl.col("net_worth").max())
    )

    n = cumulative.select(pl.col("interval").max()).item() + 1
    grid = (
        cumulative.select("account_id")
        .unique()
        .join(pl.DataFrame({"interval": range(n)}, schema={"interval": pl.Int64}), how="cross")
    )
    filled = (
        grid.join(cumulative, on=["account_id", "interval"], how="left")
        .sort("account_id", "interval")
        .with_columns(
            pl.col("net_worth").fill_null(strategy="forward").fill_null(0).over("account_id")
        )
    )

    teams = (
        scan("players", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("account_id", "team")
        .collect()
    )

    return (
        filled.join(teams, on="account_id")
        .group_by("interval", "team")
        .agg(pl.col("net_worth").sum())
        .pivot(on="team", index="interval", values="net_worth")
        .rename({"0": "total_team0", "1": "total_team1"})
        .sort("interval")
        .with_columns(
            (pl.col("total_team0") - pl.col("total_team0").shift(1).fill_null(0)).alias(
                "souls_team0"
            ),
            (pl.col("total_team1") - pl.col("total_team1").shift(1).fill_null(0)).alias(
                "souls_team1"
            ),
            (pl.col("total_team0") - pl.col("total_team1")).alias("lead"),
            (pl.col("interval") * interval_s).alias("start_s"),
            ((pl.col("interval") + 1) * interval_s).clip(upper_bound=duration_s).alias("end_s"),
        )
        .select("start_s", "end_s", "souls_team0", "souls_team1", "lead")
    )


MOVEMENT_COUNTS = [
    "alive_s",
    "moving_s",
    "stationary_s",
    "slide_s",
    "in_air_s",
    "zipline_s",
    "combat_s",
    "dashes",
    "air_dashes",
    "distance",
]


def _movement_percents() -> list[pl.Expr]:
    """Derive the percent and pace columns from summed movement counts."""
    alive = pl.col("alive_s")
    moving = pl.col("moving_s")

    return [
        pl.when(alive > 0).then(100 * pl.col("slide_s") / alive).alias("slide_percent"),
        pl.when(alive > 0).then(100 * pl.col("in_air_s") / alive).alias("in_air_percent"),
        pl.when(alive > 0).then(100 * pl.col("zipline_s") / alive).alias("zipline_percent"),
        pl.when(alive > 0).then(100 * pl.col("combat_s") / alive).alias("combat_percent"),
        pl.when(moving > 0).then(100 * pl.col("stationary_s") / moving).alias("stationary_percent"),
        pl.when(moving > 0).then(pl.col("distance") / (moving / 60)).alias("distance_min"),
    ]


def movement_intervals(
    match_id: int,
    account_id: int,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
) -> pl.DataFrame:
    """Split the movement for one player into intervals of distance and state counts.

    - sums the per minute movement_intervals rows into the requested buckets
    - percents cover alive seconds, stationary and pace cover moving seconds
    - intervals spent fully dead keep zero counts and null percents
    - the last interval ends at the match end, so it can be shorter than the rest
    """
    if not table_exists("movement_intervals", parquet_dir):
        msg = "movement_intervals table not built yet, run `deadlock sync`"
        raise ValueError(msg)

    duration = (
        scan("matches", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("duration_s")
        .collect()
    )

    if duration.is_empty():
        msg = f"match {match_id} not in the tables"
        raise ValueError(msg)

    buckets = (
        scan("movement_intervals", parquet_dir)
        .filter(pl.col("match_id") == match_id, pl.col("account_id") == account_id)
        .group_by((pl.col("start_s") // interval_s).alias("interval"))
        .agg(pl.col(MOVEMENT_COUNTS).sum())
        .collect()
    )

    if buckets.is_empty():
        msg = f"account {account_id} has no movement rows in match {match_id}"
        raise ValueError(msg)

    duration_s = int(duration.item())
    last = buckets.select(pl.col("interval").max()).item()
    n = max((duration_s - 1) // interval_s + 1, last + 1)

    return (
        pl.DataFrame({"interval": range(n)}, schema={"interval": pl.Int64})
        .join(buckets, on="interval", how="left")
        .sort("interval")
        .with_columns(pl.col(MOVEMENT_COUNTS).fill_null(0))
        .with_columns(
            (pl.col("interval") * interval_s).alias("start_s"),
            ((pl.col("interval") + 1) * interval_s).clip(upper_bound=duration_s).alias("end_s"),
        )
        .with_columns(_movement_percents())
        .select(
            "start_s",
            "end_s",
            *MOVEMENT_COUNTS,
            "slide_percent",
            "in_air_percent",
            "zipline_percent",
            "combat_percent",
            "stationary_percent",
            "distance_min",
        )
    )


def movement_scoreboard(match_id: int, parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Sum the movement of every player in one match.

    - the movement_profile columns without the farm pace
    - hero and team come joined from the players table
    - players without movement rows stay out
    """
    return (
        scan("movement_intervals", parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .group_by("match_id", "account_id")
        .agg(pl.col(MOVEMENT_COUNTS).sum())
        .with_columns(_movement_percents())
        .join(
            scan("players", parquet_dir).select("match_id", "account_id", "hero", "team"),
            on=["match_id", "account_id"],
        )
    )


def movement_profile(parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Movement metrics per player per match from the movement_intervals table.

    - time sliding, in the air, ziplining, and fighting players as a percent
      of alive seconds
    - dashes and air dashes counted on the transition into the state
    - distance skips zipline seconds, respawn jumps, and other teleports
    - farm souls (troopers, jungle, treasure, denies) for pace per minute and per distance
    """
    grp = "match_id", "account_id"

    metrics = (
        scan("movement_intervals", parquet_dir)
        .group_by(*grp)
        .agg(pl.col(MOVEMENT_COUNTS).sum())
        .with_columns(_movement_percents())
        .with_columns(
            (pl.col("dashes") / (pl.col("alive_s") / 60)).alias("dashes_min"),
            (pl.col("air_dashes") / (pl.col("alive_s") / 60)).alias("air_dashes_min"),
        )
    )

    farm = (
        scan("soul_sources", parquet_dir)
        .filter(pl.col("source_name").is_in(["troopers", "jungle", "treasure", "denies"]))
        .group_by("match_id", "account_id", "source_name")
        .agg(pl.col("souls").max())
        .group_by(*grp)
        .agg(pl.col("souls").sum().alias("farm_souls"))
    )

    return (
        metrics.join(farm, on=list(grp), how="left")
        .join(scan("matches", parquet_dir).select("match_id", "duration_s"), on="match_id")
        .with_columns(
            (pl.col("farm_souls") / (pl.col("duration_s") / 60)).alias("farm_min"),
            pl.when(pl.col("distance") > 0)
            .then(1000 * pl.col("farm_souls") / pl.col("distance"))
            .alias("souls_per_1000_units"),
        )
    )


def _era_from(value: str) -> dt.datetime:
    """Parse a stored era from string into a UTC datetime."""
    parsed = dt.datetime.fromisoformat(value)

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)


def _hero_by_era() -> Iterator[tuple[dt.datetime, int | None, heroes.Hero]]:
    """Yield the era start, client version, and hero resolved for each hero in each balance era."""
    path = store.read_path("hero_history.parquet")
    era_list = history.eras(path)

    if not era_list:
        for hero in heroes.hero_map().values():
            yield _ERA_SENTINEL, None, hero

        return

    for from_str, build in era_list:
        when = _era_from(from_str)

        for hero_id in heroes.hero_map():
            hero = heroes.hero_asof(hero_id, when, path)

            if hero is not None:
                yield when, build, hero


def _hero_era_starts() -> list[dt.datetime]:
    """Return each hero balance era start as a UTC datetime, oldest first."""
    era_list = history.eras(store.read_path("hero_history.parquet"))

    if not era_list:
        return [_ERA_SENTINEL]

    return [_era_from(from_str) for from_str, _ in era_list]


def _with_hero_era(left: pl.LazyFrame, on: str = "start_time") -> pl.LazyFrame:
    """Attach the hero balance era live at the time of each row as an era_from column."""
    starts = _hero_era_starts()
    first = min(starts)
    era_frame = (
        pl.LazyFrame({"era_from": starts}, schema={"era_from": pl.Datetime("us", "UTC")})
        .with_columns(
            pl.when(pl.col("era_from") == first)
            .then(pl.lit(_ERA_SENTINEL))
            .otherwise(pl.col("era_from"))
            .alias("_join_from")
        )
        .sort("_join_from")
    )

    return (
        left.sort(on)
        .join_asof(era_frame, left_on=on, right_on="_join_from", strategy="backward")
        .drop("_join_from")
    )


def hero_scaling() -> pl.LazyFrame:
    """Per hero per level base health and spirit power, one block per balance era.

    Columns: era_from, client_version, hero_id, level, required_souls, base_health,
    spirit_power. base_health and spirit power come from the hero stats live in each
    era, so old matches join against the tuning that was current when they were played.
    Use hero_scaling_asof to attach the era-correct rows to match rows by start time.
    """
    rows = [
        {
            "era_from": era_from,
            "client_version": build,
            "hero_id": hero.id,
            "level": info.level,
            "required_souls": info.required_souls,
            "base_health": hero.base_health(info.level),
            "spirit_power": hero.spirit_power(info.level),
        }
        for era_from, build, hero in _hero_by_era()
        for info in hero.levels
    ]
    schema = {
        "era_from": pl.Datetime("us", "UTC"),
        "client_version": pl.Int64,
        "hero_id": pl.Int64,
        "level": pl.Int64,
        "required_souls": pl.Int64,
        "base_health": pl.Float64,
        "spirit_power": pl.Float64,
    }

    return pl.LazyFrame(rows, schema=schema)


def hero_scaling_asof(left: pl.LazyFrame) -> pl.LazyFrame:
    """Attach era-correct base_health and spirit_power to left rows by start time.

    - left carries hero_id, level, and start_time
    - as-of joins hero_scaling by (hero_id, level) on the era live at start_time
    """
    scaling = hero_scaling().drop("client_version")

    return _asof_era_join(left, scaling, by=["hero_id", "level"])


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
