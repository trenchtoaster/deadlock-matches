"""Buff statue magnitudes from the bundled statues.json snapshot."""

from __future__ import annotations

import datetime as dt
import functools
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deadlock_matches.assets import history

STATUES_JSON = Path(__file__).parent / "data" / "statues.json"
STATUE_HISTORY_PARQUET = Path(__file__).parent / "data" / "statue_history.parquet"

STATUE_RE = re.compile(r"^(?P<buff>\w+?)_permanent_pickup(?:_lv(?P<level>\d+))?$")
POWER_UP_RE = re.compile(r"^(?P<buff>\w+?)_powerup_pickup$")


def parse_pickup(class_name: str) -> tuple[str | None, int | None]:
    """Split a pickup class name into its buff family and statue level.

    - hp_permanent_pickup_lv2 -> (hp, 2), the unsuffixed name is level 1
    - gun_powerup_pickup -> (gun, None), the temporary crate power ups have no level
    - anything else -> (None, None)
    """
    m = STATUE_RE.match(class_name)

    if m:
        return m["buff"], int(m["level"] or 1)

    m = POWER_UP_RE.match(class_name)

    if m:
        return m["buff"], None

    return None, None


def is_statue(class_name: str) -> bool:
    """Whether a class name is a permanent buff statue pickup."""
    return STATUE_RE.match(class_name) is not None


@dataclass(frozen=True, slots=True)
class Statue:
    """One buff statue pickup with the permanent stat a single pickup grants."""

    id: int
    class_name: str
    buff: str | None
    level: int | None
    stat: str | None
    value: float | None

    @classmethod
    def from_record(cls, rec: dict[str, Any]) -> Statue:
        """Parse a raw statues.json record."""
        buff, level = parse_pickup(rec["class_name"])

        return cls(
            id=rec["id"],
            class_name=rec["class_name"],
            buff=buff,
            level=level,
            stat=rec.get("stat"),
            value=rec.get("value"),
        )


@functools.cache
def statue_map(path: Path = STATUES_JSON) -> dict[str, Statue]:
    """Cached load of statues.json, keyed by class name."""
    records = json.loads(Path(path).read_text(encoding="utf-8"))

    return {rec["class_name"]: Statue.from_record(rec) for rec in records}


def statue_map_asof(
    when: dt.datetime | dt.date, path: Path = STATUE_HISTORY_PARQUET
) -> dict[str, Statue]:
    """Return every statue in effect at a time, keyed by class name.

    - one Statue per class name from the era live at when
    - no history at all falls back to the bundled current snapshot
    """
    records = history.records_asof(path, when)

    if records is None:
        return statue_map()

    return {rec["class_name"]: Statue.from_record(rec) for rec in records.values()}
