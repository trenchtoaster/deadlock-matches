"""Damage source categories and the delivery split."""

from __future__ import annotations

from pathlib import Path

import polars as pl

from deadlock_matches.queries.core import _local_day, asset_asof, scan

BULLET_PROC_OVERRIDES = frozenset({"upgrade_siphon_bullets"})


_TOTAL_PATTERN = r"^[A-Z][A-Za-z]*$"


def damage_category() -> pl.Expr:
    """Bucket source_class as gun, item, ability, or a match screen total.

    - citadel_weapon* rows are the gun itself, upgrade_* rows are shop items
    - a bare capitalized word (Bullet, Ability) is a summary row that just
      adds up the matching detail rows, so never sum totals with details
    - everything else is a hero kit ability class name
    """
    return (
        pl.when(pl.col("source_class").str.starts_with("citadel_weapon"))
        .then(pl.lit("gun"))
        .when(pl.col("source_class").str.starts_with("upgrade_"))
        .then(pl.lit("item"))
        .when(pl.col("source_class").str.contains(_TOTAL_PATTERN))
        .then(pl.lit("total"))
        .otherwise(pl.lit("ability"))
    )


def with_delivery(frame: pl.LazyFrame, parquet_dir: str | Path | None = None) -> pl.LazyFrame:
    """Add category and delivery columns to damage rows at read time.

    - category buckets source_class by its class name shape
    - delivery groups detail rows by what makes the damage happen: gun,
      ability, gun_proc for item procs that fire when a shot lands, and
      spirit_proc for items with their own trigger
    - item rows resolve through the shop slot of the item era live at match
      start, where the weapon slot means gun_proc and anything else spirit_proc
    - Siphon Bullets sits in the vitality slot yet procs on hit and stays
      gun_proc through BULLET_PROC_OVERRIDES
    - total rows keep a null delivery
    """
    frame = frame.with_columns(damage_category().alias("category"))

    pairs = (
        frame.filter(pl.col("category") == "item")
        .select("match_id", "source_class")
        .unique()
        .join(scan("matches", parquet_dir).select("match_id", "start_time"), on="match_id")
        .with_columns(pl.col("source_class").alias("class_name"))
    )
    slots = asset_asof(
        pairs,
        "item_history",
        by="class_name",
        parquet_dir=parquet_dir,
    ).select("match_id", "source_class", "slot")

    return (
        frame.join(slots, on=["match_id", "source_class"], how="left")
        .with_columns(
            pl.when(pl.col("category") == "gun")
            .then(pl.lit("gun"))
            .when(pl.col("category") == "ability")
            .then(pl.lit("ability"))
            .when(pl.col("category") != "item")
            .then(pl.lit(None, dtype=pl.String))
            .when(pl.col("source_class").is_in(BULLET_PROC_OVERRIDES))
            .then(pl.lit("gun_proc"))
            .when(pl.col("slot") == "weapon")
            .then(pl.lit("gun_proc"))
            .otherwise(pl.lit("spirit_proc"))
            .alias("delivery")
        )
        .drop("slot")
    )


def hero_damage(
    stat: str = "damage",
    parquet_dir: str | Path | None = None,
    tz: str | None = None,
) -> pl.LazyFrame:
    """Damage detail rows against hero targets, safe to sum by source.

    - drops `total` rows, which duplicate the gun/ability/item detail rows
    - drops non-player targets, so farm damage never inflates a source
    - drops zero value rows
    - adds `hero` and `start_local`/`day` columns for the dealer, so filtering
      by hero, account, or day needs no extra joins
    - adds `category` and `delivery` columns derived at read time, see
      with_delivery

    stat picks which figure to keep: damage, healing, mitigated, ...
    """
    dealers = scan("players", parquet_dir).select(
        "match_id",
        pl.col("account_id").alias("dealer_account_id"),
        "hero",
    )
    rows = scan("damage", parquet_dir).filter(
        pl.col("stat") == stat,
        damage_category() != "total",
        pl.col("target_account_id").is_not_null(),
        pl.col("damage") != 0,
    )
    detail = with_delivery(rows, parquet_dir).join(
        dealers, on=["match_id", "dealer_account_id"], how="left"
    )

    return _local_day(detail, parquet_dir, tz)
