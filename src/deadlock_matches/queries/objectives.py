"""Unstable Rift wins and Soul Urn deliveries read from the treasure soul source."""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any

import polars as pl

from deadlock_matches.queries.core import player_rows, scan, table_exists
from deadlock_matches.queries.labels import GoldSource
from deadlock_matches.queries.stats import custom_stats

if TYPE_CHECKING:
    from pathlib import Path


RIFT_ERA_START = dt.datetime(2026, 6, 30, 10, 7, 19, tzinfo=dt.UTC)
"""Release of client build 6601, the Unstable Rift rework in the deadlock-api version timeline.

- earlier matches ran the old urn-KOTH rules with a different bounty
- the build and its date come from snapshots.client_version_dates
"""

RIFT_SHARE_BASE = 247
RIFT_SHARE_PER_MIN = 37
RIFT_START_MIN = 13

URN_BOUNTY_BASE = 250
URN_BOUNTY_PER_MIN = 70
URN_FIRST_SPAWN_MIN = 10


def rift_minute(share: int) -> float:
    """Recover the capture minute from a rift share of souls."""
    return (share - RIFT_SHARE_BASE) / RIFT_SHARE_PER_MIN + RIFT_START_MIN


def urn_minute(bounty: int) -> float:
    """Recover the spawn minute from an urn runner bounty."""
    return (bounty - URN_BOUNTY_BASE) / URN_BOUNTY_PER_MIN


def detect_rift(gains: list[int], team_size: int, comeback: int, duration_s: int) -> int | None:
    """Detect a rift win in this snapshot window from the shared team payout.

    - a rift win pays every player on the winning team the same souls at once
    """
    modal = max(set(gains), key=gains.count)
    modal_count = gains.count(modal)

    if modal_count < 5 or modal_count < team_size - 1:
        return None

    minute = rift_minute(modal - comeback)

    if abs(minute - round(minute)) > 0.05:
        return None

    if not RIFT_START_MIN - 0.5 <= minute <= duration_s / 60 + 1:
        return None

    return modal


def detect_urn(
    gains: list[int], hero_names: list[str], shared: int, duration_s: int
) -> tuple[str, int] | None:
    """Detect an urn delivery in this window and name the runner.

    - the runner banks the largest treasure gain once any shared rift payout is set aside
    """
    top_gain, runner = max(zip(gains, hero_names, strict=True))
    bounty = top_gain - shared

    if bounty < URN_BOUNTY_BASE + URN_BOUNTY_PER_MIN * (URN_FIRST_SPAWN_MIN - 0.5):
        return None

    if urn_minute(bounty) > duration_s / 60 + 2:
        return None

    return runner, bounty


def income_events(
    row: dict[str, Any], parquet_dir: str | Path | None = None
) -> list[tuple[int, str]]:
    """List every Unstable Rift win and Soul Urn delivery in the match.

    - both pay into the treasure soul source
    - a rift win pays the whole team at once, a comeback win adds the Comeback Gold Koth stat
    - an urn delivery pays one runner
    - only games on the rework build are read, earlier eras ran other rules
    """
    if row["start_time"] < RIFT_ERA_START:
        return []

    if not table_exists("soul_sources", parquet_dir):
        return []

    match_id = row["match_id"]

    roster = (
        player_rows(parquet_dir)
        .filter(pl.col("match_id") == match_id)
        .select("account_id", "team", "hero")
        .collect()
    )
    team_size = dict(roster.group_by("team").len().iter_rows())

    treasure = (
        scan("soul_sources", parquet_dir)
        .filter(pl.col("match_id") == match_id, pl.col("source") == int(GoldSource.TREASURE))
        .select("account_id", "time_stamp_s", "souls", "souls_orbs")
        .sort("account_id", "time_stamp_s")
        .with_columns((pl.col("souls") + pl.col("souls_orbs")).alias("total"))
        .with_columns(
            pl.col("total").diff().over("account_id").fill_null(pl.col("total")).alias("gain")
        )
        .filter(pl.col("gain") > 0)
        .collect()
        .join(roster, on="account_id")
    )

    if treasure.is_empty():
        return []

    comeback = comeback_by_window(match_id, roster, parquet_dir)

    windows = (
        treasure.group_by("team", "time_stamp_s")
        .agg(pl.col("gain"), pl.col("hero"))
        .sort("time_stamp_s")
    )

    events = []

    for w in windows.iter_rows(named=True):
        team, t = w["team"], w["time_stamp_s"]
        actor = "your team" if team == row["team"] else "enemy team"
        c = comeback.get((team, t), 0)

        payout = detect_rift(w["gain"], team_size.get(team, 6), c, row["duration_s"])

        if payout is not None:
            behind = " while behind" if c else ""
            events.append((t, f"{actor} wins an Unstable Rift{behind} (+{payout:,} souls each)"))

        urn = detect_urn(w["gain"], w["hero"], payout or 0, row["duration_s"])

        if urn is not None:
            runner, bounty = urn
            events.append((t, f"{actor} delivers the Soul Urn ({runner}, +{bounty:,} souls)"))

    return events


def comeback_by_window(
    match_id: int, roster: pl.DataFrame, parquet_dir: str | Path | None = None
) -> dict[tuple[int, int], int]:
    """Read the comeback souls for each team and snapshot from the rift Koth stat."""
    if not table_exists("custom_stats", parquet_dir):
        return {}

    koth = custom_stats(
        stat="Comeback Gold Koth", final=False, matches=[match_id], parquet_dir=parquet_dir
    ).collect()

    if koth.is_empty():
        return {}

    windows = (
        koth.join(roster.select("account_id", "team"), on="account_id")
        .sort("account_id", "time_stamp_s")
        .with_columns(
            pl.col("value").diff().over("account_id").fill_null(pl.col("value")).alias("inc")
        )
        .filter(pl.col("inc") > 0)
        .group_by("team", "time_stamp_s")
        .agg(pl.col("inc").first().alias("comeback"))
    )

    return {
        (t, ts): c for t, ts, c in windows.select("team", "time_stamp_s", "comeback").iter_rows()
    }
