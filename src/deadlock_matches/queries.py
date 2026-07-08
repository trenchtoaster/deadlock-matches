"""Reusable polars queries over the exported parquet tables."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl

from deadlock_matches import abilities, config, export, heroes, items, schemas
from deadlock_matches import skill_rating as sr

if TYPE_CHECKING:
    from collections.abc import Sequence


def scan(table: str, parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Lazily scan one exported table by name (one of schemas.TABLES).

    parquet_dir defaults to the standard export directory, here and in every
    query below.
    """
    if table not in schemas.TABLES:
        known = ", ".join(schemas.TABLES)
        msg = f"Unknown table {table!r}, tables: {known}"
        raise ValueError(msg)

    parquet_dir = export.PARQUET_DIR if parquet_dir is None else Path(parquet_dir)

    return pl.scan_parquet(parquet_dir / f"{table}.parquet")


def table_exists(table: str, parquet_dir: str | Path | None = None) -> bool:
    """Whether one exported table's parquet file is on disk (movement is excluded by default)."""
    if table not in schemas.TABLES:
        known = ", ".join(schemas.TABLES)
        msg = f"Unknown table {table!r}, tables: {known}"
        raise ValueError(msg)

    parquet_dir = export.PARQUET_DIR if parquet_dir is None else Path(parquet_dir)

    return (parquet_dir / f"{table}.parquet").exists()


def my_games(
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    tz: str | None = None,
) -> pl.LazyFrame:
    """One row per match the player appeared in, joined to match details.

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
    """One row per buy of one item with its ownership window.

    A sold buy's window ends at the sell time, a kept buy's at the end of the
    match.
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
    """One row per buyer per match with the first buy time and summed owned seconds."""
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

    row = (
        _item_buys(windows)
        .join(dmg, on=["match_id", "account_id"], how="left")
        .select(
            pl.len().alias("builds"),
            pl.col("owned_s").sum(),
            pl.col("damage").fill_null(0).sum().alias("damage"),
        )
        .collect()
    )

    builds = int(row.item(0, "builds"))
    owned = float(row.item(0, "owned_s") or 0)
    total = float(row.item(0, "damage") or 0)

    dealt_row = (
        _dealt_owning(windows, parquet_dir)
        .select(pl.col("dealt_after_buy").sum().alias("dealt"))
        .collect()
    )
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
    """One row per game for the player, with the first buy time and damage for one item joined in.

    Games without a buy keep nulls, so "not built" games stay visible next to
    the built ones. owned_s sums the ownership windows, ending at the sell
    time when a buy was sold. hero filters to games on that hero. since keeps
    only days on or after that date (YYYY-MM-DD, like 2026-07-01).
    buy_n is the item's first named purchase order. tier_buy_n is its order
    among items of the same tier. first_tier_item is what the player bought
    first in that tier, and is_first_tier_item marks games where it was this item.
    dealt_after_buy is the hero damage the player dealt while owning the item,
    the denominator for the item's percent of hero damage.
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

    windows = _item_windows(pl.col("item_id") == it.id, parquet_dir)
    dealt = (
        scan("damage", parquet_dir)
        .filter(
            pl.col("source_class") == it.class_name,
            pl.col("stat") == "damage",
            pl.col("target_account_id").is_not_null(),
        )
        .group_by("match_id", "dealer_account_id")
        .agg(pl.col("damage").sum())
    )
    ordered_buys = (
        scan("item_events", parquet_dir)
        .filter(pl.col("item").is_not_null())
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
    )
    reward_rows = [
        {
            "hero_id": hero.id,
            "reward_n": n,
            "level": info.level,
            "required_souls": info.required_souls,
            "reward": reward,
        }
        for hero in heroes.hero_map().values()
        for reward in ("ability_unlocks", "ability_points")
        for n, info in enumerate(
            (info for info in hero.levels if reward in info.currencies),
            start=1,
        )
    ]
    rewards = pl.LazyFrame(
        reward_rows,
        schema={
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
            left_on=["hero_id", "ability_unlock_n"],
            right_on=["hero_id", "reward_n"],
            how="left",
        )
        .join(
            points,
            left_on=["hero_id", "ability_points_spent"],
            right_on=["hero_id", "reward_n"],
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
    )


def daily_record(
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
    tz: str | None = None,
    days: int | None = None,
    since: str | dt.date | None = None,
    hero: str | None = None,
    by: str = "day",
) -> pl.DataFrame:
    """Per local day W/L record with net wins and a running total.

    days keeps only the last N days of games, None keeps everything. since
    keeps only days on or after that date (YYYY-MM-DD or YYYYMMDD, like 2026-07-01). hero filters to
    one hero's games. by rolls the days into week or month buckets, where a
    week starts on Monday.
    """
    if by not in ("day", "week", "month"):
        msg = f"Unknown bucket {by!r}, use day, week, or month"
        raise ValueError(msg)

    lf = my_games(parquet_dir, accounts, tz)

    if hero is not None:
        hero_id = heroes.hero_id_by_name(hero)

        if hero_id is None:
            msg = f"Unknown hero {hero!r}"
            raise ValueError(msg)

        lf = lf.filter(pl.col("hero_id") == hero_id)

    daily = (
        lf.unique(subset="match_id")
        .group_by("day")
        .agg(
            pl.len().cast(pl.Int32).alias("games"),
            pl.col("won").sum().cast(pl.Int32).alias("wins"),
            (pl.col("mvp_rank") == 1).sum().cast(pl.Int32).alias("mvps"),
            (pl.col("mvp_rank") >= 2).sum().cast(pl.Int32).alias("key_players"),
        )
        .sort("day")
        .collect()
    )

    if since is not None:
        since = dt.date.fromisoformat(since) if isinstance(since, str) else since
        daily = daily.filter(pl.col("day") >= since)

    if days is not None:
        daily = daily.tail(days)

    if by != "day":
        every = "1w" if by == "week" else "1mo"
        daily = (
            daily.group_by(pl.col("day").dt.truncate(every))
            .agg(pl.col("games", "wins", "mvps", "key_players").sum())
            .sort("day")
        )

    return (
        daily.with_columns((pl.col("games") - pl.col("wins")).alias("losses"))
        .with_columns(
            (pl.col("wins") / pl.col("games") * 100).alias("win_rate"),
            (pl.col("wins") - pl.col("losses")).alias("net"),
        )
        .with_columns(pl.col("net").cum_sum().alias("cum_net"))
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
    - adds the dealer's `hero` and `start_local`/`day` columns, so filtering
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
        .agg(pl.exclude("match_id", "account_id").max())
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
    """Rank every player's hero damage within their team, one row per match player.

    - player_damage is the final snapshot value
    - rank 1 is the team's damage chart top, flagged by top_team_damage
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


def stale_hero_matches(parquet_dir: str | Path | None = None) -> list[int]:
    """Match IDs played on an older balance patch than the bundled hero stats.

    Flags matches where base health computed from heroes.json exceeds the max
    health recorded in the snapshots, which can only happen when the hero
    stats changed after the match.
    """
    hero_ids = scan("players", parquet_dir).select("match_id", "account_id", "hero_id")
    flagged = (
        scan("stats", parquet_dir)
        .select("match_id", "account_id", "level", "max_health")
        .join(hero_ids, on=["match_id", "account_id"])
        .join(hero_scaling(), on=["hero_id", "level"])
        .filter((pl.col("max_health") > 0) & (pl.col("base_health") > pl.col("max_health")))
        .select("match_id")
        .unique()
        .collect()
    )

    return sorted(flagged["match_id"].to_list())


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
        msg = 'movement table not exported: remove "movement" from the exclude list in config.toml and run `deadlock export`'
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


def snapshot_players(
    hero: str,
    parquet_dir: str | Path | None = None,
    accounts: Sequence[int] | None = None,
) -> list[dict]:
    """Games by the player on one hero, shaped like the player blocks the timeline module accepts.

    Each entry is {"stats": [snapshot dicts]} keyed by the protobuf field names,
    so timeline.compare and friends take them unchanged instead of re-reading
    every archived protobuf.
    """
    hero_id = heroes.hero_id_by_name(hero)

    if hero_id is None:
        msg = f"Unknown hero {hero!r}"
        raise ValueError(msg)

    games = (
        my_games(parquet_dir, accounts)
        .filter(pl.col("hero_id") == hero_id)
        .select("match_id", "account_id")
    )
    snaps = scan("stats", parquet_dir).join(games, on=["match_id", "account_id"]).collect()
    sources = scan("soul_sources", parquet_dir).join(games, on=["match_id", "account_id"]).collect()

    raw_names = {schemas.souls(f): f for f in schemas.STAT_FIELDS}
    by_snap: dict[tuple, dict] = {}

    for row in snaps.iter_rows(named=True):
        key = (row["match_id"], row["account_id"], row["time_stamp_s"])
        snap = {raw_names[c]: v for c, v in row.items() if c in raw_names}
        snap["gold_sources"] = []
        by_snap[key] = snap

    for row in sources.iter_rows(named=True):
        key = (row["match_id"], row["account_id"], row["time_stamp_s"])
        snap = by_snap.setdefault(key, {"time_stamp_s": row["time_stamp_s"], "gold_sources": []})
        snap["gold_sources"].append(
            {"source": row["source"], "gold": row["souls"], "gold_orbs": row["souls_orbs"]}
        )

    blocks: dict[tuple, list[dict]] = {}

    for (match_id, account_id, _), snap in sorted(by_snap.items()):
        blocks.setdefault((match_id, account_id), []).append(snap)

    return [{"stats": snaps} for snaps in blocks.values()]


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
    """Split one player's match into intervals of stat gains.

    - snapshots are cumulative, so an interval's gain is its last snapshot
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
    """Split one player's damage to heroes into per-source gains per interval.

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


def source_intervals(
    games: pl.DataFrame | pl.LazyFrame,
    interval_s: int = 300,
    parquet_dir: str | Path | None = None,
    stat: str = "damage",
) -> pl.LazyFrame:
    """Split damage or healing by source and interval for multiple players.

    - the many-game version of damage_intervals, same semantics per player:
      detail rows on hero targets only, a gain lands in the interval holding
      the sample that recorded it, forward fill carries a source's cumulative
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

    - each player's cumulative net worth carries forward through intervals
      without a snapshot, so one player's gap never dents the team total
    - lead is the team 0 total minus the team 1 total at the interval's end
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


def movement_profile(parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Movement metrics per player per match from the movement table, alive seconds only.

    - time sliding, in the air, ziplining, and fighting players as a percent
      of alive seconds
    - dashes and air dashes counted on the transition into the state
    - distance skips zipline seconds, respawn jumps, and other teleports
    - farm souls (troopers, jungle, treasure, denies) for pace per minute and per distance
    """
    grp = "match_id", "account_id"
    contiguous = pl.col("game_time_s") - pl.col("prev_time") == 1
    walking = (pl.col("move_type") != "ziplining") & (pl.col("prev_move") != "ziplining")

    metrics = (
        scan("movement", parquet_dir)
        .filter(pl.col("health_percent") > 0)
        .sort("match_id", "account_id", "game_time_s")
        .with_columns(
            pl.col("game_time_s").shift(1).over(grp).alias("prev_time"),
            pl.col("move_type").shift(1).over(grp).alias("prev_move"),
            pl.col("x").shift(1).over(grp).alias("prev_x"),
            pl.col("y").shift(1).over(grp).alias("prev_y"),
        )
        .with_columns(
            ((pl.col("x") - pl.col("prev_x")) ** 2 + (pl.col("y") - pl.col("prev_y")) ** 2)
            .sqrt()
            .alias("step")
        )
        .with_columns(
            pl.when(contiguous & walking & (pl.col("step") < 2500))
            .then(pl.col("step"))
            .alias("step")
        )
        .group_by(*grp)
        .agg(
            pl.len().alias("alive_s"),
            (pl.col("move_type") == "slide").mean().mul(100).alias("slide_percent"),
            (pl.col("move_type") == "in_air").mean().mul(100).alias("in_air_percent"),
            (pl.col("move_type") == "ziplining").mean().mul(100).alias("zipline_percent"),
            (pl.col("combat_type") == "player").mean().mul(100).alias("combat_percent"),
            ((pl.col("move_type") == "ground_dash") & (pl.col("prev_move") != "ground_dash"))
            .sum()
            .alias("dashes"),
            ((pl.col("move_type") == "air_dash") & (pl.col("prev_move") != "air_dash"))
            .sum()
            .alias("air_dashes"),
            pl.col("step").sum().alias("distance"),
            pl.col("step").is_not_null().sum().alias("moving_s"),
            (pl.col("step") < 40).mean().mul(100).alias("stationary_percent"),
        )
        .with_columns(
            (pl.col("dashes") / (pl.col("alive_s") / 60)).alias("dashes_min"),
            (pl.col("air_dashes") / (pl.col("alive_s") / 60)).alias("air_dashes_min"),
            pl.when(pl.col("moving_s") > 0)
            .then(pl.col("distance") / (pl.col("moving_s") / 60))
            .alias("distance_min"),
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


def hero_scaling() -> pl.LazyFrame:
    """Per hero per level reference frame built from heroes.json, not parquet.

    Columns: hero_id, level, required_souls, base_health, spirit_power.
    Join stats to players on (match_id, account_id) for hero_id, then join
    this on (hero_id, level) to split level scaling from item stats.
    """
    rows = [
        {
            "hero_id": hero.id,
            "level": info.level,
            "required_souls": info.required_souls,
            "base_health": hero.base_health(info.level),
            "spirit_power": hero.spirit_power(info.level),
        }
        for hero in heroes.hero_map().values()
        for info in hero.levels
    ]
    schema = {
        "hero_id": pl.Int64,
        "level": pl.Int64,
        "required_souls": pl.Int64,
        "base_health": pl.Float64,
        "spirit_power": pl.Float64,
    }

    return pl.LazyFrame(rows, schema=schema)


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
