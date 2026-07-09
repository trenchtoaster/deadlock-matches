"""Resolve badge level data to the skill rating label from the assets API data."""

from __future__ import annotations

import datetime as dt
import functools
import json
from pathlib import Path

from deadlock_matches import history

SKILL_RATING_JSON = Path(__file__).parent / "data" / "skill_rating.json"
RANK_HISTORY_PARQUET = Path(__file__).parent / "data" / "rank_history.parquet"


@functools.cache
def tier_map(path: Path = SKILL_RATING_JSON) -> dict[int, str]:
    """Load skill_rating.json into {tier: name}, cached per path."""
    records = json.loads(Path(path).read_text(encoding="utf-8"))

    return {rec["tier"]: rec["name"] for rec in records}


def rank_asof(tier: int, when: dt.datetime | dt.date, path: Path = RANK_HISTORY_PARQUET) -> str | None:
    """Return the rank name for a tier in effect at the given time.

    - latest era on or before `when`
    - times older than all history get the earliest era
    - no history at all falls back to the bundled current snapshot
    """
    if not history.has_history(path):
        return tier_map().get(tier)

    rec = history.record_asof(path, tier, when)

    return rec["name"] if rec else None


def label(badge: int | None, path: Path = SKILL_RATING_JSON) -> str | None:
    """Turn a badge level into a label.

    - badge levels are the tier number * 10 plus the level within the tier
    - 0 is Obscurus, 62 is Emissary 2, 106 is Ascendant 6, 111 is Eternus 1
    - unknown tiers come back as badge<N>
    """
    if badge is None:
        return None

    tier, level = divmod(badge, 10)
    name = tier_map(path).get(tier)

    if name is None:
        return f"badge{badge}"

    if tier == 0:
        return name

    return f"{name} {level}"
