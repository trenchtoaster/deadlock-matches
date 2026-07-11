"""As-of lookup over the committed asset history tables."""

from __future__ import annotations

import datetime as dt
import functools
import json
from pathlib import Path
from typing import Any

import polars as pl

SCHEMA = {"from": pl.String, "build": pl.Int64, "id": pl.String, "record": pl.String}


def write(path: Path, states: list[dict[str, Any]]) -> None:
    """Write asset history states to a parquet table, one row per era per record."""
    rows = [
        {
            "from": s["from"],
            "build": s["build"],
            "id": rid,
            "record": json.dumps(rec, sort_keys=True),
        }
        for s in states
        for rid, rec in s["records"].items()
    ]
    pl.DataFrame(rows, schema=SCHEMA).write_parquet(path, compression="zstd")
    _table.cache_clear()


@functools.cache
def _table(path: Path) -> pl.DataFrame | None:
    """Return the committed history table, or None when no file ships or it has no rows."""
    if not Path(path).is_file():
        return None

    table = pl.read_parquet(path)

    return None if table.is_empty() else table


def has_history(path: Path) -> bool:
    """Return whether a committed history table ships at path."""
    return _table(path) is not None


def eras(path: Path) -> list[tuple[str, int]]:
    """Return the from datetime and build of each stored era from oldest to newest."""
    table = _table(path)

    if table is None:
        return []

    return table.select("from", "build").unique().sort("from").rows()


def _naive_utc(when: dt.datetime | dt.date) -> dt.datetime:
    """Turn a date or datetime into a naive UTC datetime matching the stored from strings."""
    if isinstance(when, dt.datetime):
        if when.tzinfo is not None:
            return when.astimezone(dt.UTC).replace(tzinfo=None)

        return when

    return dt.datetime(when.year, when.month, when.day)


def _chosen_from(froms: list[str], when: dt.datetime | dt.date) -> str:
    """Pick the latest era start on or before when, falling back to the earliest."""
    target = _naive_utc(when)
    ordered = sorted(froms, key=dt.datetime.fromisoformat)
    eligible = [f for f in ordered if dt.datetime.fromisoformat(f) <= target]

    return eligible[-1] if eligible else ordered[0]


def record_asof(
    path: Path, record_id: str | int, when: dt.datetime | dt.date
) -> dict[str, Any] | None:
    """Return the stored record for an id in effect at the given time.

    - latest era on or before `when`
    - times older than all history get the earliest era
    """
    table = _table(path)

    if table is None:
        return None

    rows = table.filter(pl.col("id") == str(record_id))

    if rows.is_empty():
        return None

    chosen = _chosen_from(rows.get_column("from").to_list(), when)

    return json.loads(rows.filter(pl.col("from") == chosen).item(0, "record"))


def read_states(path: Path) -> list[dict[str, Any]]:
    """Return every stored era as {from, build, records}, oldest first.

    Rebuilds the shape build_asset_history writes, so a backfill can resume from
    the last committed era instead of rescanning every client build.
    """
    table = _table(path)

    if table is None:
        return []

    out = []

    for (frm, build), group in table.sort("from").group_by(
        ["from", "build"], maintain_order=True
    ):
        records = {rid: json.loads(rec) for rid, rec in group.select("id", "record").iter_rows()}
        out.append({"from": frm, "build": build, "records": records})

    return out


def record_history(path: Path, record_id: str | int) -> list[tuple[str, int, dict[str, Any]]]:
    """Return each stored era as (from, build, record) for one id, oldest first."""
    table = _table(path)

    if table is None:
        return []

    rows = table.filter(pl.col("id") == str(record_id)).sort("from")

    return [
        (frm, build, json.loads(rec))
        for frm, build, rec in rows.select("from", "build", "record").iter_rows()
    ]


def records_asof(path: Path, when: dt.datetime | dt.date) -> dict[str, dict[str, Any]] | None:
    """Return every stored record in effect at the given time, keyed by id.

    Each era is a full snapshot, so this picks the one era live at when and
    decodes all of its records.
    """
    table = _table(path)

    if table is None:
        return None

    chosen = _chosen_from(table.get_column("from").unique().to_list(), when)
    rows = table.filter(pl.col("from") == chosen)

    return {rid: json.loads(rec) for rid, rec in rows.select("id", "record").iter_rows()}
