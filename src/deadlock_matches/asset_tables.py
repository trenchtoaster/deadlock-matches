"""Flatten the committed asset history into parquet tables.

- each era stores one JSON record per asset, split into a flat table plus a table per nested field
- every row keeps its era (era_from, client_version)
"""

from __future__ import annotations

import datetime as dt
import json
from typing import TYPE_CHECKING, Any

import polars as pl

from deadlock_matches import abilities, assets, heroes, history, items, schemas, statues
from deadlock_matches import skill_rating as sr

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def _parse_from(value: str) -> dt.datetime:
    """Parse a committed era start string into a UTC datetime the as-of join can use."""
    parsed = dt.datetime.fromisoformat(value)

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.UTC)


def _era_records(path: Path) -> Iterator[tuple[dt.datetime, int, str, dict[str, Any]]]:
    """Yield era_from, client_version, id, and decoded record for each committed era row."""
    if not history.has_history(path):
        return

    table = pl.read_parquet(path)

    for when, build, rid, record in table.select("from", "build", "id", "record").iter_rows():
        yield _parse_from(when), build, rid, json.loads(record)


def item_tables(path: Path | None = None) -> dict[str, pl.DataFrame]:
    """Flatten the committed item history into the item and component tables."""
    path = items.ITEM_HISTORY_PARQUET if path is None else path
    parents: list[dict] = []
    components: list[dict] = []

    for era_from, build, _rid, rec in _era_records(path):
        grain = {"era_from": era_from, "client_version": build}

        parents.append(
            {
                "item_id": rec["id"],
                "name": rec.get("name"),
                "class_name": rec.get("class_name"),
                "cost": rec.get("cost"),
                "slot": rec.get("slot"),
                "tier": rec.get("tier"),
                "is_active": bool(rec.get("is_active")),
                "description": rec.get("description"),
                **grain,
            }
        )

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
        "item_history": schemas.conform("item_history", parents),
        "item_component_history": schemas.conform("item_component_history", components),
    }


def hero_tables(path: Path | None = None) -> dict[str, pl.DataFrame]:
    """Flatten the committed hero history into the hero, level, stat, and boon tables."""
    path = heroes.HERO_HISTORY_PARQUET if path is None else path
    parents: list[dict] = []
    levels: list[dict] = []
    stats: list[dict] = []
    level_ups: list[dict] = []

    for era_from, build, _rid, rec in _era_records(path):
        grain = {"era_from": era_from, "client_version": build}

        parents.append(
            {
                "hero_id": rec["id"],
                "name": rec.get("name"),
                "class_name": rec.get("class_name"),
                "hero_type": rec.get("hero_type"),
                "gun_tag": rec.get("gun_tag"),
                "complexity": rec.get("complexity"),
                "player_selectable": bool(rec.get("player_selectable")),
                "disabled": bool(rec.get("disabled")),
                **grain,
            }
        )

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
        "hero_history": schemas.conform("hero_history", parents),
        "hero_level_history": schemas.conform("hero_level_history", levels),
        "hero_stat_history": schemas.conform("hero_stat_history", stats),
        "hero_level_up_history": schemas.conform("hero_level_up_history", level_ups),
    }


def ability_tables(path: Path | None = None) -> dict[str, pl.DataFrame]:
    """Flatten the committed ability history into the ability, property, upgrade, and weapon tables."""
    path = abilities.ABILITY_HISTORY_PARQUET if path is None else path
    parents: list[dict] = []
    props: list[dict] = []
    upgrades: list[dict] = []
    weapons: list[dict] = []

    for era_from, build, _rid, rec in _era_records(path):
        grain = {"era_from": era_from, "client_version": build}
        cls = rec["class_name"]

        parents.append(
            {
                "ability_class": cls,
                "id": rec["id"],
                "name": rec.get("name"),
                "hero": rec.get("hero"),
                "kind": rec.get("kind"),
                "description": rec.get("description"),
                **grain,
            }
        )

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

        if rec.get("kind") == "weapon":
            weapon = rec.get("weapon") or {}
            weapons.append(
                {
                    "ability_class": cls,
                    **{f: weapon.get(f) for f in assets.WEAPON_FIELDS},
                    **grain,
                }
            )

    return {
        "ability_history": schemas.conform("ability_history", parents),
        "ability_property_history": schemas.conform("ability_property_history", props),
        "ability_upgrade_history": schemas.conform("ability_upgrade_history", upgrades),
        "ability_weapon_history": schemas.conform("ability_weapon_history", weapons),
    }


def rank_tables(path: Path | None = None) -> dict[str, pl.DataFrame]:
    """Flatten the committed rank history into the rank table."""
    path = sr.RANK_HISTORY_PARQUET if path is None else path
    rows: list[dict] = []

    for era_from, build, _rid, rec in _era_records(path):
        rows.append(
            {
                "tier": rec["tier"],
                "name": rec.get("name"),
                "era_from": era_from,
                "client_version": build,
            }
        )

    return {"rank_history": schemas.conform("rank_history", rows)}


def statue_tables(path: Path | None = None) -> dict[str, pl.DataFrame]:
    """Flatten the committed statue history into the statue table."""
    path = statues.STATUE_HISTORY_PARQUET if path is None else path
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
