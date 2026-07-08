"""Minute-by-minute stat curves from a match's cumulative stats snapshots.

- accepts local protobuf players and the api's json players (same shape)
- values between snapshots are linearly interpolated, and checkpoints past a
  player's last snapshot come back None instead of extrapolating
- composite stats split income by source: farm (troopers/jungle/treasure/
  breakables/denies), combat (kill+assist souls), objectives, souls (net worth)
- gold source composites read each snapshot's gold_sources list because
  breakable crates (source 12) have no flat gold_* field at all
"""

from __future__ import annotations

import statistics as st
from dataclasses import dataclass
from enum import IntEnum
from itertools import pairwise
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence


class GoldSource(IntEnum):
    """Income source IDs in snapshot gold_sources rows (protobuf EGoldSource)."""

    PLAYERS = 1
    LANE_CREEPS = 2
    NEUTRALS = 3
    BOSSES = 4
    TREASURE = 5
    ASSISTS = 6
    DENIES = 7
    TEAM_BONUS = 8
    ABILITY_ASSASSINATE = 9
    ITEM_TROPHY_COLLECTOR = 10
    ITEM_CULTIST_SACRIFICE = 11
    BREAKABLE = 12
    ITEM_GOOSE_EGG = 13


@dataclass(frozen=True)
class Stat:
    """A named stat, either flat snapshot fields to sum or gold sources to filter on."""

    description: str
    fields: tuple[str, ...] = ()
    sources: tuple[GoldSource, ...] = ()

    @classmethod
    def from_sources(cls, description: str, *sources: GoldSource) -> Stat:
        """Builds a Stat that sums souls from the listed income sources."""
        return cls(description, sources=sources)

    @classmethod
    def from_fields(cls, description: str, *fields: str) -> Stat:
        """Builds a Stat that sums the listed snapshot fields."""
        return cls(description, fields=fields)


STATS = {
    "farm": Stat.from_sources(
        "souls from troopers, jungle, boxes, urns, and denies",
        GoldSource.LANE_CREEPS,
        GoldSource.NEUTRALS,
        GoldSource.TREASURE,
        GoldSource.DENIES,
        GoldSource.BREAKABLE,
    ),
    "troopers": Stat.from_sources("souls from lane troopers", GoldSource.LANE_CREEPS),
    "jungle": Stat.from_sources("souls from neutral camps", GoldSource.NEUTRALS),
    "breakables": Stat.from_sources("souls from boxes and statues", GoldSource.BREAKABLE),
    "treasure": Stat.from_sources("souls from urns", GoldSource.TREASURE),
    "combat": Stat.from_fields(
        "souls from hero kills and assists", "gold_player", "gold_player_orbs"
    ),
    "catch_up": Stat.from_sources("team catch-up souls", GoldSource.TEAM_BONUS),
    "other": Stat.from_sources(
        "souls from Trophy Collector, sacrifices, goose eggs, and Assassinate",
        GoldSource.ITEM_TROPHY_COLLECTOR,
        GoldSource.ITEM_CULTIST_SACRIFICE,
        GoldSource.ITEM_GOOSE_EGG,
        GoldSource.ABILITY_ASSASSINATE,
    ),
    "objectives": Stat.from_fields(
        "souls from bosses and objectives", "gold_boss", "gold_boss_orb"
    ),
    "souls": Stat.from_fields("total net worth", "net_worth"),
}


def _field(obj: Any, key: str, default: Any = None) -> Any:
    """Read one field off a dict or a protobuf message."""
    if isinstance(obj, dict):
        val = obj.get(key)
        return default if val is None else val

    return getattr(obj, key, default)


def _value(snap: Any, stat: str) -> float:
    """A snapshot's value for a raw field or a named stat from STATS."""
    spec = STATS.get(stat)

    if spec and spec.sources:
        total = 0
        for g in _field(snap, "gold_sources", ()) or ():
            if _field(g, "source", GoldSource.PLAYERS) in spec.sources:
                total += (_field(g, "gold", 0) or 0) + (_field(g, "gold_orbs", 0) or 0)

        return total

    fields = spec.fields if spec else (stat,)

    return sum(_field(snap, f, 0) or 0 for f in fields)


def snapshots(player: Any, stat: str) -> list[tuple[float, float]]:
    """Sorted (time_s, value) points for one stat, anchored at (0, 0).

    Player blocks can be dicts or protobufs. stat is a raw snapshot field,
    a composite, or a gold source group.
    """
    pts = sorted(
        (_field(s, "time_stamp_s", 0), _value(s, stat)) for s in _field(player, "stats", ()) or ()
    )

    return [(0, 0)] + pts


def stat_at(player: Any, stat: str, time_s: float) -> float | None:
    """Cumulative stat value at game time time_s, interpolated, or None past match end."""
    pts = snapshots(player, stat)

    if len(pts) < 2 or time_s > pts[-1][0]:
        return None

    for (t0, v0), (t1, v1) in pairwise(pts):
        if t0 <= time_s <= t1:
            if t1 == t0:
                return float(v1)

            return v0 + (v1 - v0) * (time_s - t0) / (t1 - t0)

    return None


def curve(player: Any, stat: str, minutes: Sequence[int]) -> list[float | None]:
    """Stat values at each checkpoint minute for one player."""
    return [stat_at(player, stat, m * 60) for m in minutes]


def median_curve(players: Sequence[Any], stat: str, minutes: Sequence[int]) -> list[dict[str, Any]]:
    """Median stat value at each checkpoint across a set of player games.

    Games that ended before a checkpoint drop out of that point's median
    instead of dragging it down, so n shrinks as minutes go up.
    """
    rows = []
    for m in minutes:
        vals = [v for p in players if (v := stat_at(p, stat, m * 60)) is not None]
        rows.append({"min": m, "value": st.median(vals) if vals else None, "n": len(vals)})

    return rows


def compare(
    mine: Sequence[Any], theirs: Sequence[Any], stat: str, minutes: Sequence[int]
) -> list[dict[str, Any]]:
    """Median curves side by side, gap = me minus them at each checkpoint."""
    rows = []
    for a, b in zip(
        median_curve(mine, stat, minutes), median_curve(theirs, stat, minutes), strict=True
    ):
        gap = None if a["value"] is None or b["value"] is None else a["value"] - b["value"]

        rows.append(
            {
                "min": a["min"],
                "me": a["value"],
                "me_n": a["n"],
                "them": b["value"],
                "them_n": b["n"],
                "gap": gap,
            }
        )

    return rows


def interval_rates(rows: Sequence[dict[str, Any]], key: str) -> list[float | None]:
    """Gain per minute inside each checkpoint interval of a compare table.

    Intervals touching a None checkpoint come back None. key picks the
    column to differentiate ("me", "them" or "value").
    """
    out: list[float | None] = []
    prev_min, prev_val = 0, 0.0

    for r in rows:
        val = r[key]

        if val is None or prev_val is None:
            out.append(None)
        else:
            out.append((val - prev_val) / (r["min"] - prev_min))

        prev_min, prev_val = r["min"], val

    return out
