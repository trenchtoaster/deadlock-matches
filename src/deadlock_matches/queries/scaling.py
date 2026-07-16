"""Hero balance eras and level scaling."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

import polars as pl

from deadlock_matches.assets import heroes, history, store
from deadlock_matches.queries.core import _ERA_SENTINEL, _asof_era_join

if TYPE_CHECKING:
    from collections.abc import Iterator


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
