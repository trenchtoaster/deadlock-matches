"""Accolade names from the bundled accolades.json snapshot."""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deadlock_matches.assets import store

ACCOLADES_JSON = store.seed_path("accolades.json")


@dataclass(frozen=True, slots=True)
class Accolade:
    """One end of match stat award.

    class_name is the stat it grades (kills, headshot_damage), name is the
    award title the post game screen shows (Killer Instinct).
    """

    id: int
    class_name: str
    name: str

    @classmethod
    def from_record(cls, rec: dict[str, Any]) -> Accolade:
        """Parse a raw accolades.json record."""
        return cls(id=rec["id"], class_name=rec["class_name"], name=rec["name"])


@functools.cache
def accolade_map(path: Path | None = None) -> dict[int, Accolade]:
    """Cached load of accolades.json, keyed by accolade id."""
    src = Path(path) if path is not None else store.read_path("accolades.json")
    records = json.loads(src.read_text(encoding="utf-8"))

    return {rec["id"]: Accolade.from_record(rec) for rec in records}
