"""Item metadata from the bundled items.json snapshot."""

from __future__ import annotations

import datetime as dt
import functools
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from deadlock_matches.assets import history, store

ITEMS_JSON = store.seed_path("items.json")
ITEM_HISTORY_PARQUET = store.seed_path("item_history.parquet")


@dataclass(frozen=True, slots=True)
class Item:
    """A purchasable item, keeping just the fields the analysis code touches.

    components holds the class_names of lower-tier items this one is built
    from. An item vanishing into one of these in a build is an upgrade, not
    a sell.
    """

    id: int
    name: str
    class_name: str | None
    cost: int | None
    slot: str | None
    tier: int | None
    is_active: bool
    description: str | None = None
    components: tuple[str, ...] = ()
    activation: str | None = None
    shopable: bool = False
    disabled: bool = False
    imbue: str | None = None
    upgrades: tuple[tuple[dict[str, Any], ...], ...] = ()
    properties: dict[str, Any] = field(default_factory=dict)
    scaling: dict[str, Any] = field(default_factory=dict)
    damage_types: dict[str, str] = field(default_factory=dict)
    scale_types: dict[str, str] = field(default_factory=dict)
    negatives: tuple[str, ...] = ()
    conditionals: dict[str, str] = field(default_factory=dict)
    labels: dict[str, Any] = field(default_factory=dict)
    sections: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_record(cls, rec: dict[str, Any]) -> Item:
        """Parse one items.json record into an Item."""
        return cls(
            id=rec["id"],
            name=rec["name"],
            class_name=rec.get("class_name"),
            cost=rec.get("cost"),
            slot=rec.get("slot"),
            tier=rec.get("tier"),
            is_active=bool(rec.get("is_active")),
            description=rec.get("description"),
            components=tuple(rec.get("components") or ()),
            activation=rec.get("activation"),
            shopable=bool(rec.get("shopable")),
            disabled=bool(rec.get("disabled")),
            imbue=rec.get("imbue"),
            upgrades=tuple(tuple(dict(up) for up in tier) for tier in rec.get("upgrades") or []),
            properties=dict(rec.get("properties") or {}),
            scaling=dict(rec.get("scaling") or {}),
            damage_types=dict(rec.get("damage_types") or {}),
            scale_types=dict(rec.get("scale_types") or {}),
            negatives=tuple(rec.get("negatives") or ()),
            conditionals=dict(rec.get("conditionals") or {}),
            labels=dict(rec.get("labels") or {}),
            sections=tuple(rec.get("sections") or ()),
        )


@functools.cache
def item_map(path: Path | None = None) -> dict[int, Item]:
    """Cached load of items.json, keyed by item ID."""
    src = Path(path) if path is not None else store.read_path("items.json")
    records = json.loads(src.read_text(encoding="utf-8"))

    return {rec["id"]: Item.from_record(rec) for rec in records}


def item_name(item_id: int, path: Path | None = None) -> str:
    """Item display name, falling back to "id<N>" for unknown IDs."""
    item = item_map(path).get(item_id)

    return item.name if item else f"id{item_id}"


@functools.cache
def item_by_name(name: str, path: Path | None = None) -> Item | None:
    """Look up an item by display name, ignoring case."""
    low = name.lower()

    for item in item_map(path).values():
        if item.name.lower() == low:
            return item

    return None


@functools.cache
def item_by_class_name(class_name: str, path: Path | None = None) -> Item | None:
    """Look up an item by engine class_name."""
    for item in item_map(path).values():
        if item.class_name == class_name:
            return item

    return None


def item_asof(item_id: int, at: dt.datetime | dt.date, path: Path | None = None) -> Item | None:
    """Return the item cost, tier, and slot in effect at the given time.

    - latest era on or before `at`
    - times older than all history get the earliest era
    - no history at all falls back to the current snapshot
    """
    src = Path(path) if path is not None else store.read_path("item_history.parquet")

    if not history.has_history(src):
        return item_map().get(item_id)

    rec = history.record_asof(src, item_id, at)

    return Item.from_record(rec) if rec else None


def item_map_asof(at: dt.datetime | dt.date, path: Path | None = None) -> dict[int, Item]:
    """Return every item in effect at a time, keyed by id.

    - one Item per id from the era live at the target time
    - no history at all falls back to the current snapshot
    """
    src = Path(path) if path is not None else store.read_path("item_history.parquet")
    records = history.records_asof(src, at)

    if records is None:
        return item_map()

    return {rec["id"]: Item.from_record(rec) for rec in records.values()}
