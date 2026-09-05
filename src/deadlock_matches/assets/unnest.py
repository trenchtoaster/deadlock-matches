"""Flatten the committed asset history into parquet tables.

- each era stores one JSON record per asset, split into a flat table plus a table per nested field
- every row keeps its era (era_from, client_version)
"""

from __future__ import annotations

import datetime as dt
import json
from typing import TYPE_CHECKING, Any

import polars as pl

from deadlock_matches import schemas
from deadlock_matches.assets import history, snapshots, statues, store

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _parse_from(value: str) -> dt.datetime:
    """Parse a committed era start string into a UTC datetime the as-of join can use."""
    parsed = dt.datetime.fromisoformat(value)

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)


def _era_records(path: Path) -> Iterator[tuple[dt.datetime, int, str, dict[str, Any]]]:
    """Yield era_from, client_version, id, and decoded record for each committed era row."""
    table = history._table(path)

    if table is None:
        return

    for when, build, rid, record in table.select("from", "build", "id", "record").iter_rows():
        yield _parse_from(when), build, rid, json.loads(record)


def _era_frame(path: Path) -> pl.DataFrame | None:
    """Return the committed era rows with the era start parsed and the grain named."""
    table = history._table(path)

    if table is None:
        return None

    starts = {value: _parse_from(value) for value in table.get_column("from").unique()}

    return table.with_columns(
        pl.col("from")
        .replace_strict(starts, return_dtype=pl.Datetime("us", "UTC"))
        .alias("era_from"),
        pl.col("build").alias("client_version"),
    )


def _flat_table(frame: pl.DataFrame | None, table: str, names: dict[str, str]) -> pl.DataFrame:
    """Decode the record column of every era row into one flat table.

    - names maps each record field to the column it fills
    - a boolean column reads a missing field as false, the way the game treats it
    """
    spec = schemas.TABLES[table]

    if frame is None:
        return schemas.conform(table, [])

    dtype = pl.Struct({field: spec[column].dtype for field, column in names.items()})
    columns = []

    for field, column in names.items():
        value = pl.col("record").struct.field(field)

        if spec[column].dtype == pl.Boolean:
            value = value.fill_null(False)

        columns.append(value.alias(column))

    decoded = frame.with_columns(pl.col("record").str.json_decode(dtype))

    return schemas.conform(table, decoded.select(*columns, "era_from", "client_version"))


def _weapon_table(frame: pl.DataFrame | None) -> pl.DataFrame:
    """Flatten the weapon block of every gun record into the weapon history table."""
    if frame is None:
        return schemas.conform("ability_weapon_history", [])

    spec = schemas.TABLES["ability_weapon_history"]
    dtype = pl.Struct(
        {
            "class_name": pl.String,
            "kind": pl.String,
            "weapon": pl.Struct({f: spec[f].dtype for f in snapshots.WEAPON_FIELDS}),
        }
    )
    decoded = frame.with_columns(pl.col("record").str.json_decode(dtype)).filter(
        pl.col("record").struct.field("kind") == "weapon"
    )
    weapon = pl.col("record").struct.field("weapon")
    rows = decoded.select(
        pl.col("record").struct.field("class_name").alias("ability_class"),
        *[weapon.struct.field(f).alias(f) for f in snapshots.WEAPON_FIELDS],
        "era_from",
        "client_version",
    )

    return schemas.conform("ability_weapon_history", rows)


ITEM_FIELDS = {
    "id": "item_id",
    "name": "name",
    "class_name": "class_name",
    "cost": "cost",
    "slot": "slot",
    "tier": "tier",
    "is_active": "is_active",
    "description": "description",
}

HERO_FIELDS = {
    "id": "hero_id",
    "name": "name",
    "class_name": "class_name",
    "hero_type": "hero_type",
    "gun_tag": "gun_tag",
    "complexity": "complexity",
    "player_selectable": "player_selectable",
    "disabled": "disabled",
}

ABILITY_FIELDS = {
    "class_name": "ability_class",
    "id": "id",
    "name": "name",
    "hero": "hero",
    "kind": "kind",
    "description": "description",
}

RANK_FIELDS = {"tier": "tier", "name": "name"}


def item_tables(path: Path | None = None) -> dict[str, pl.DataFrame]:
    """Flatten the committed item history into the item and component tables."""
    path = store.read_path("item_history.parquet") if path is None else path
    components: list[dict] = []

    for era_from, build, _rid, rec in _era_records(path):
        grain = {"era_from": era_from, "client_version": build}

        for pos, comp in enumerate(rec.get("components") or []):
            components.append(
                {
                    "item_id": rec["id"],
                    "position": pos,
                    "component_class_name": comp,
                    **grain,
                }
            )

    return {
        "item_history": _flat_table(_era_frame(path), "item_history", ITEM_FIELDS),
        "item_component_history": schemas.conform("item_component_history", components),
    }


def hero_tables(path: Path | None = None) -> dict[str, pl.DataFrame]:
    """Flatten the committed hero history into the hero, level, stat, and boon tables."""
    path = store.read_path("hero_history.parquet") if path is None else path
    levels: list[dict] = []
    stats: list[dict] = []
    level_ups: list[dict] = []

    for era_from, build, _rid, rec in _era_records(path):
        grain = {"era_from": era_from, "client_version": build}

        levels.extend(
            {
                "hero_id": rec["id"],
                "level": lvl["level"],
                "required_souls": lvl.get("required_souls", 0),
                "standard_upgrade": bool(lvl.get("standard_upgrade")),
                **grain,
            }
            for lvl in rec.get("levels") or []
        )

        stats.extend(
            {"hero_id": rec["id"], "stat": stat, "value": value, **grain}
            for stat, value in (rec.get("stats") or {}).items()
        )

        level_ups.extend(
            {"hero_id": rec["id"], "stat": stat, "per_level_value": value, **grain}
            for stat, value in (rec.get("level_up") or {}).items()
        )

    return {
        "hero_history": _flat_table(_era_frame(path), "hero_history", HERO_FIELDS),
        "hero_level_history": schemas.conform("hero_level_history", levels),
        "hero_stat_history": schemas.conform("hero_stat_history", stats),
        "hero_level_up_history": schemas.conform("hero_level_up_history", level_ups),
    }


def ability_tables(path: Path | None = None) -> dict[str, pl.DataFrame]:
    """Flatten the committed ability history into the ability, property, upgrade, and weapon tables."""
    path = store.read_path("ability_history.parquet") if path is None else path
    props: list[dict] = []
    upgrades: list[dict] = []

    for era_from, build, _rid, rec in _era_records(path):
        grain = {"era_from": era_from, "client_version": build}
        cls = rec["class_name"]

        values = rec.get("properties") or {}
        scaling = rec.get("scaling") or {}

        for prop in sorted(set(values) | set(scaling)):
            scale = scaling.get(prop) or {}
            props.append(
                {
                    "ability_class": cls,
                    "property": prop,
                    "value": values.get(prop),
                    "scale_stat": scale.get("stat"),
                    "scale": scale.get("scale"),
                    **grain,
                }
            )

        upgrades.extend(
            {
                "ability_class": cls,
                "tier": tier,
                "property": up.get("property"),
                "bonus": up.get("bonus"),
                "type": up.get("type"),
                "stat": up.get("stat"),
                **grain,
            }
            for tier, entries in enumerate(rec.get("upgrades") or [], start=1)
            for up in entries
        )

    frame = _era_frame(path)

    return {
        "ability_history": _flat_table(frame, "ability_history", ABILITY_FIELDS),
        "ability_property_history": schemas.conform("ability_property_history", props),
        "ability_upgrade_history": schemas.conform("ability_upgrade_history", upgrades),
        "ability_weapon_history": _weapon_table(frame),
    }


def rank_tables(path: Path | None = None) -> dict[str, pl.DataFrame]:
    """Flatten the committed rank history into the rank table."""
    path = store.read_path("rank_history.parquet") if path is None else path

    return {"rank_history": _flat_table(_era_frame(path), "rank_history", RANK_FIELDS)}


def statue_tables(path: Path | None = None) -> dict[str, pl.DataFrame]:
    """Flatten the committed statue history into the statue table."""
    path = store.read_path("statue_history.parquet") if path is None else path
    rows: list[dict] = []

    for era_from, build, _rid, rec in _era_records(path):
        buff, level = statues.parse_pickup(rec["class_name"])

        rows.append(
            {
                "class_name": rec["class_name"],
                "buff": buff,
                "level": level,
                "stat": rec.get("stat"),
                "value": rec.get("value"),
                "era_from": era_from,
                "client_version": build,
            }
        )

    return {"statue_history": schemas.conform("statue_history", rows)}


def all_asset_tables() -> dict[str, pl.DataFrame]:
    """Flatten every committed asset history into its tables."""
    return {
        **item_tables(),
        **hero_tables(),
        **ability_tables(),
        **rank_tables(),
        **statue_tables(),
    }
