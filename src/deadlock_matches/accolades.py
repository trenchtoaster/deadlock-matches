"""Accolade names from the bundled accolades.json snapshot."""

from __future__ import annotations

import functools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ACCOLADES_JSON = Path(__file__).parent / "data" / "accolades.json"


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
def accolade_map(path: Path = ACCOLADES_JSON) -> dict[int, Accolade]:
    """Cached load of accolades.json, keyed by accolade id."""
    records = json.loads(Path(path).read_text(encoding="utf-8"))

    return {rec["id"]: Accolade.from_record(rec) for rec in records}
