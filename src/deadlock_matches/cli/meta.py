"""The meta command, public hero trends from the deadlock-api."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from deadlock_matches import heroes, meta, skill_rating

if TYPE_CHECKING:
    import argparse

BUCKETS = {
    "rating": "avg_badge",
    "day": "start_time_day",
    "week": "start_time_week",
    "month": "start_time_month",
}


def _window(args: argparse.Namespace) -> str:
    """Build the since/until part of the header line."""
    parts = []

    if args.since:
        parts.append(f"since {args.since}")

    if args.until:
        parts.append(f"until {args.until}")

    return ", " + ", ".join(parts) if parts else ""


def meta_report(args: argparse.Namespace) -> None:
    """Print public hero win rates, pick rates, and match counts, whole pool or bucketed.

    - no flags: one row per hero, sorted by win rate
    - --by rating/day/week/month splits into skill rating or time buckets
    - --hero narrows the buckets to one hero and defaults --by to week
    """
    hero_id = None
    by = args.by

    if args.hero is not None:
        hero_id = heroes.hero_id_by_name(args.hero)

        if hero_id is None:
            print(f"Unknown hero: {args.hero}")
            return

        by = by or "week"

    try:
        badge = meta.min_badge(args.min_rating)
        rows = meta.get_hero_stats(
            badge=badge,
            since=args.since,
            until=args.until,
            bucket=BUCKETS[by] if by else None,
        )
    except ValueError as e:
        print(e)
        return

    if not rows:
        print("No data for that window")
        return

    scope = "all ratings" if badge is None else f"{args.min_rating}+ lobbies"
    subject = f"{args.hero} " if args.hero else ""
    print(f"{subject}public data ({scope}{_window(args)}, deadlock-api.com)\n")

    if by is None:
        print(f"  {'Hero':<16} {'Win rate':>8} {'Pick rate':>9} {'Matches':>10}")

        for r in meta.hero_meta(rows):
            name = heroes.hero_name(r["hero_id"])
            print(
                f"  {name:<16} {r['win_rate']:>7.1f}% {r['pick_rate']:>8.1f}% {r['matches']:>10,}"
            )

        return

    if by == "rating":
        head = "Rating"
        label = skill_rating.label
    else:
        head = by.capitalize()

        def label(bucket: int) -> str:
            return dt.datetime.fromtimestamp(bucket, dt.UTC).date().isoformat()

    table = meta.bucket_meta(rows, hero_id)

    if hero_id is None:
        print(f"  {head:<14} {'Matches':>10} {'Share':>6}")

        for r in table:
            print(f"  {label(r['bucket']):<14} {r['matches']:>10,} {r['share']:>5.1f}%")
    else:
        print(f"  {head:<14} {'Matches':>10} {'Win rate':>8} {'Pick rate':>9}")

        for r in table:
            print(
                f"  {label(r['bucket']):<14} {r['matches']:>10,} "
                f"{r['win_rate']:>7.1f}% {r['pick_rate']:>8.1f}%"
            )
