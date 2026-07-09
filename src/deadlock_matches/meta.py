"""Item win rate and synergy analytics for each hero from the deadlock-api.

- compute functions are pure and take already-downloaded rows so they can be tested
- the get_* helpers go through api.get_json (network + disk cache)
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from deadlock_matches import api, items

RANKS = {
    "initiate": 1,
    "seeker": 2,
    "alchemist": 3,
    "arcanist": 4,
    "ritualist": 5,
    "emissary": 6,
    "archon": 7,
    "oracle": 8,
    "phantom": 9,
    "ascendant": 10,
    "eternus": 11,
}


def min_badge(rank: str) -> int | None:
    """Minimum average badge value for a rank name, None for 'all'."""
    if rank.lower() == "all":
        return None

    tier = RANKS.get(rank.lower())

    if tier is None:
        known = ", ".join(r.capitalize() for r in RANKS)
        msg = f"Unknown rank {rank!r}, ranks: {known} or all"
        raise ValueError(msg)

    return tier * 10 + 1


def _stamp(day: str) -> int:
    """Unix timestamp for the start of a YYYY-MM-DD day."""
    d = dt.date.fromisoformat(day)

    return int(dt.datetime(d.year, d.month, d.day, tzinfo=dt.UTC).timestamp())


def _filters(badge: int | None, since: str | None, until: str | None = None) -> str:
    """Extra query parameters for the analytics endpoints."""
    extra = ""

    if badge is not None:
        extra += f"&min_average_badge={badge}"

    if since is not None:
        extra += f"&min_unix_timestamp={_stamp(since)}"

    if until is not None:
        extra += f"&max_unix_timestamp={_stamp(until)}"

    return extra


def get_item_stats(
    hero_id: int, badge: int | None = None, since: str | None = None
) -> list[dict[str, Any]]:
    """Download win, loss, and buy time rows for each item on a hero."""
    return api.get_json(
        f"v1/analytics/item-stats?hero_id={hero_id}" + _filters(badge, since), max_age=api.DAY
    )


def get_hero_stats(
    badge: int | None = None,
    since: str | None = None,
    until: str | None = None,
    bucket: str | None = None,
) -> list[dict[str, Any]]:
    """Win and loss rows for each hero, optionally split into buckets.

    bucket is an API grouping: avg_badge for one row per hero per badge level,
    start_time_day/week/month for one row per hero per period.
    """
    query = _filters(badge, since, until).removeprefix("&")

    if bucket is not None:
        query = f"bucket={bucket}" + (f"&{query}" if query else "")

    path = "v1/analytics/hero-stats" + (f"?{query}" if query else "")

    return api.get_json(path, max_age=api.DAY)


def hero_meta(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Win rate, pick rate, and matches per hero from hero-stats rows.

    Pick rate approximates the share of matches the hero appears in, from
    the hero's cut of the 12 hero slots per match.
    """
    total = sum(r["matches"] for r in rows)
    out = [
        {
            "hero_id": r["hero_id"],
            "matches": r["matches"],
            "win_rate": _wr(r),
            "pick_rate": 100 * 12 * r["matches"] / total if total else 0.0,
        }
        for r in rows
    ]

    out.sort(key=lambda x: -x["win_rate"])

    return out


def bucket_meta(rows: list[dict[str, Any]], hero_id: int | None = None) -> list[dict[str, Any]]:
    """Matches per bucket from bucketed hero-stats rows (badge levels or time periods).

    - without hero_id each row is the whole pool: matches counts whole matches
      and share is the bucket's cut of all matches
    - with hero_id: the hero's matches, win rate, and pick rate inside each bucket
    """
    pool: dict[int, dict[str, int]] = {}

    for r in rows:
        agg = pool.setdefault(r["bucket"], {"matches": 0, "hero_wins": 0, "hero_matches": 0})
        agg["matches"] += r["matches"]

        if hero_id is not None and r["hero_id"] == hero_id:
            agg["hero_wins"] += r["wins"]
            agg["hero_matches"] += r["matches"]

    all_matches = sum(a["matches"] for a in pool.values())
    out = []

    for bucket, a in sorted(pool.items()):
        if hero_id is None:
            out.append(
                {
                    "bucket": bucket,
                    "matches": round(a["matches"] / 12),
                    "share": 100 * a["matches"] / all_matches if all_matches else 0.0,
                }
            )
        else:
            hero_row = {"wins": a["hero_wins"], "matches": a["hero_matches"]}
            out.append(
                {
                    "bucket": bucket,
                    "matches": a["hero_matches"],
                    "win_rate": _wr(hero_row),
                    "pick_rate": 100 * 12 * a["hero_matches"] / a["matches"]
                    if a["matches"]
                    else 0.0,
                }
            )

    return out


def hero_baseline(rows: list[dict[str, Any]], hero_id: int) -> dict[str, Any] | None:
    """Win rate and match count for one hero from hero-stats rows."""
    for r in rows:
        if r["hero_id"] == hero_id:
            return {"win_rate": _wr(r), "matches": r["matches"]}

    return None


def get_item_pairs(
    hero_id: int, badge: int | None = None, since: str | None = None
) -> list[dict[str, Any]]:
    """Win/loss rows for each pair of items on a hero (comb=2)."""
    return api.get_json(
        f"v1/analytics/item-permutation-stats?hero_id={hero_id}&comb=2" + _filters(badge, since),
        max_age=api.DAY,
    )


def _wr(row: dict[str, Any]) -> float:
    """Win rate as a percent."""
    return 100 * row["wins"] / row["matches"] if row["matches"] else 0.0


def rank_items(stats_rows: list[dict[str, Any]], min_matches: int = 2000) -> list[dict[str, Any]]:
    """Items ranked by win rate, joined to names, filtered by sample size.

    Items with fewer than min_matches games are dropped.
    """
    im = items.item_map()

    out = []
    for r in stats_rows:
        it = im.get(r["item_id"])

        if not it or r["matches"] < min_matches:
            continue

        out.append(
            {
                "name": it.name,
                "cost": it.cost,
                "slot": it.slot,
                "tier": it.tier,
                "win_rate": _wr(r),
                "matches": r["matches"],
                "buy_min": r["avg_buy_time_s"] / 60,
            }
        )

    out.sort(key=lambda x: -x["win_rate"])

    return out


def verdict(
    stats_rows: list[dict[str, Any]], item_name: str, min_matches: int = 2000
) -> dict[str, Any]:
    """Judge one item by win rate and its edge over items at the same cost.

    Comparing to items of the same cost roughly controls for buy timing, since
    price gates when a slot becomes affordable.
    """
    item = items.item_by_name(item_name)
    if item is None:
        msg = f"unknown item: {item_name!r}"
        raise ValueError(msg)

    ranked = rank_items(stats_rows, min_matches)
    mine = next((r for r in ranked if r["name"] == item.name), None)

    if mine is None:
        return {"name": item.name, "matches": 0, "note": "not enough games"}

    peers = [r["win_rate"] for r in ranked if r["cost"] == item.cost and r["name"] != item.name]
    peer_avg = sum(peers) / len(peers) if peers else mine["win_rate"]

    return {
        "name": item.name,
        "cost": item.cost,
        "win_rate": mine["win_rate"],
        "matches": mine["matches"],
        "buy_min": mine["buy_min"],
        "peer_cost_avg": peer_avg,
        "edge_vs_peers": mine["win_rate"] - peer_avg,
    }


def synergies(
    pair_rows: list[dict[str, Any]],
    stats_rows: list[dict[str, Any]],
    item_name: str,
    min_matches: int = 1500,
    top: int = 10,
) -> dict[str, Any]:
    """Items often bought together with one item, ranked by the win rate change.

    The API returns each pair once per purchase order, so both orderings are
    merged before anything else. vs_solo is the pair win rate minus the item's
    solo win rate. Pairs below min_matches are dropped because small samples
    produce meaningless swings.
    """
    im = items.item_map()

    item = items.item_by_name(item_name)
    if item is None:
        msg = f"unknown item: {item_name!r}"
        raise ValueError(msg)

    solo = next((_wr(r) for r in stats_rows if r["item_id"] == item.id), None)
    if solo is None:
        return {"solo": None, "pairs": []}

    merged: dict[int, dict[str, int]] = {}
    for r in pair_rows:
        ids = r["item_ids"]

        if item.id not in ids:
            continue

        other = ids[0] if ids[1] == item.id else ids[1]
        agg = merged.setdefault(other, {"wins": 0, "losses": 0, "matches": 0})
        agg["wins"] += r["wins"]
        agg["losses"] += r["losses"]
        agg["matches"] += r["matches"]

    pairs = []
    for other, agg in merged.items():
        it = im.get(other)

        if not it or agg["matches"] < min_matches:
            continue

        pairs.append(
            {
                "name": it.name,
                "cost": it.cost,
                "pair_win_rate": _wr(agg),
                "vs_solo": _wr(agg) - solo,
                "matches": agg["matches"],
            }
        )

    pairs.sort(key=lambda x: -x["vs_solo"])

    return {"solo": solo, "pairs": pairs[:top]}
