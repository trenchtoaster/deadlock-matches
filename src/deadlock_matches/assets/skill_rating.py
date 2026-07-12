"""Resolve badge level data to the skill rating label from the assets API data."""

from __future__ import annotations

import datetime as dt
import functools
import json
from pathlib import Path

from deadlock_matches.assets import history, store

SKILL_RATING_JSON = store.seed_path("skill_rating.json")
RANK_HISTORY_PARQUET = store.seed_path("rank_history.parquet")


@functools.cache
def tier_map(path: Path | None = None) -> dict[int, str]:
    """Load skill_rating.json into {tier: name}, cached per path."""
    src = Path(path) if path is not None else store.read_path("skill_rating.json")
    records = json.loads(src.read_text(encoding="utf-8"))

    return {rec["tier"]: rec["name"] for rec in records}


def rank_asof(tier: int, at: dt.datetime | dt.date, path: Path | None = None) -> str | None:
    """Return the rank name for a tier in effect at the given time.

    - latest era on or before `at`
    - times older than all history get the earliest era
    - no history at all falls back to the current snapshot
    """
    src = Path(path) if path is not None else store.read_path("rank_history.parquet")

    if not history.has_history(src):
        return tier_map().get(tier)

    rec = history.record_asof(src, tier, at)

    return rec["name"] if rec else None


def subrank_index(badge: int) -> int:
    """Turn a badge level into a linear subrank count, 6 levels per tier.

    Badge levels skip 7-9 within each tier (95 -> 59), so averaging badges
    directly lands between levels. Average the indexes instead.
    """
    tier, level = divmod(badge, 10)

    return tier * 6 + level


def badge_from_subrank(index: int) -> int:
    """Turn a linear subrank count back into a badge level."""
    if index <= 0:
        return 0

    tier = (index - 1) // 6

    return tier * 10 + index - tier * 6


def label(badge: int | None, path: Path | None = None) -> str | None:
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
