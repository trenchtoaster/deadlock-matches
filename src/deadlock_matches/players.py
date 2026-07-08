"""Fetch and analyze matches from other players, from leaderboard lookups to parquet tables."""

from __future__ import annotations

import datetime as dt
import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

from deadlock_matches import api, config, export, extract, items, paths, queries, schemas

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

REGIONS = ("Europe", "NAmerica", "Asia", "SAmerica", "Oceania")
PARQUET_DIR = paths.data_dir() / "deadlock-matches/parquet-players"


def leaderboard(region: str) -> list[dict[str, Any]]:
    """Ranked ladder entries for a region (one of REGIONS)."""
    lb = api.get_json(f"v1/leaderboard/{region}", max_age=api.DAY)

    return lb.get("entries", lb) if isinstance(lb, dict) else lb


def find_player(name: str, regions: Sequence[str] = REGIONS) -> list[dict[str, Any]]:
    """Ladder entries whose account_name contains name (case-insensitive)."""
    low = name.lower()

    hits = []
    for region in regions:
        hits.extend(
            {**e, "region": region}
            for e in leaderboard(region)
            if low in (e.get("account_name") or "").lower()
        )

    return hits


def top_mains(
    hero_id: int,
    regions: Sequence[str] = REGIONS,
    limit: int = 8,
    *,
    unambiguous: bool = True,
) -> list[dict[str, Any]]:
    """Best players whose top hero is hero_id, ranked by ladder position.

    unambiguous keeps only entries that resolve to a single account ID, since
    players with lots of smurfs expose many candidate IDs with no way to pick one.
    """
    out = []
    for region in regions:
        for e in leaderboard(region):
            heroes_list = e.get("top_hero_ids") or []
            if heroes_list[:1] != [hero_id]:
                continue

            ids = e.get("possible_account_ids") or []
            if unambiguous and len(ids) != 1:
                continue

            out.append(
                {
                    "name": e["account_name"],
                    "rank": e["rank"],
                    "region": region,
                    "account_id": ids[0] if ids else None,
                }
            )

    out.sort(key=lambda x: x["rank"])

    return out[:limit]


def match_history(account_id: int) -> list[dict[str, Any]]:
    """A player's recent matches, by account ID."""
    d = api.get_json(f"v1/players/{account_id}/match-history", max_age=api.DAY)

    return d.get("matches", d) if isinstance(d, dict) else d


def match_metadata(match_id: int) -> dict[str, Any]:
    """Full match_info for a match ID."""
    return api.get_json(f"v1/matches/{match_id}/metadata", permanent=True)["match_info"]


def recent_hero_matches(account_id: int, hero_id: int, n: int = 10) -> list[dict[str, Any]]:
    """The n most recent ranked match-history rows for a player on a hero."""
    ms = [
        m
        for m in match_history(account_id)
        if m.get("hero_id") == hero_id and m.get("match_mode") == 1
    ]
    ms.sort(key=lambda m: -m["start_time"])

    return ms[:n]


def build_order(
    match_info: dict[str, Any], account_id: int, min_cost: int = 0
) -> dict[str, Any] | None:
    """Items one player bought and kept, in buy order with names and timing.

    Works on a match_info dict from the api. Entries that don't
    resolve to a shop item (ability rank-ups) are dropped, and min_cost
    drops items cheaper than that.
    """
    im = items.item_map()

    me = next((p for p in match_info["players"] if p["account_id"] == account_id), None)
    if me is None:
        return None

    seq = []
    for it in sorted(me["items"], key=lambda x: x["game_time_s"]):
        item = im.get(it["item_id"])

        if not item or not item.cost or item.cost < min_cost:
            continue

        seq.append(
            {
                "min": round(it["game_time_s"] / 60, 1),
                "name": item.name,
                "tier": item.tier,
                "slot": item.slot,
                "cost": item.cost,
                "sold": bool(it.get("sold_time_s", 0)),
            }
        )

    return {
        "win": me["team"] == match_info["winning_team"],
        "kda": (me["kills"], me["deaths"], me["assists"]),
        "seq": seq,
    }


def player_builds(
    account_id: int, hero_id: int, n: int = 10, min_cost: int = 0
) -> list[dict[str, Any]]:
    """The n most recent ranked builds for a player on a hero, win and loss.

    min_cost passes through to build_order.
    """
    builds = []
    for m in recent_hero_matches(account_id, hero_id, n):
        try:
            b = build_order(match_metadata(m["match_id"]), account_id, min_cost)
        except Exception:
            continue

        if b:
            b["match_id"] = m["match_id"]
            builds.append(b)

    return builds


def player_timelines(account_id: int, hero_id: int, n: int = 10) -> list[dict[str, Any]]:
    """A player's own player blocks (stats snapshots included) from recent ranked games."""
    out = []
    for m in recent_hero_matches(account_id, hero_id, n):
        try:
            info = match_metadata(m["match_id"])
        except Exception:
            continue

        me = next((p for p in info["players"] if p["account_id"] == account_id), None)
        if me:
            out.append(me)

    return out


def download_builds(
    players: dict[str, int], hero_id: int, n: int = 20, path: str | Path | None = None
) -> dict[str, Any]:
    """Pull n games each for a set of players into one saved snapshot (all items kept).

    players maps player_name -> account_id. Saves {player: {account_id,
    builds:[...]}} to path so every later analysis reads the same snapshot
    instead of hitting the API again. path=None skips saving.
    """
    data = {}
    for name, aid in players.items():
        data[name] = {"account_id": aid, "builds": player_builds(aid, hero_id, n=n, min_cost=0)}

    out = {"hero_id": hero_id, "players": data}

    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(out), encoding="utf-8")

    return out


def load_builds(path: str | Path) -> dict[str, Any]:
    """Read a build snapshot written by download_builds."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def flatten_builds(
    data: dict[str, Any], *, win: bool | None = None
) -> list[tuple[str, dict[str, Any]]]:
    """Flatten a download_builds snapshot to (player, build) pairs.

    win=True keeps only wins, False only losses, None everything.
    """
    return [
        (name, b)
        for name, pdata in data["players"].items()
        for b in pdata["builds"]
        if win is None or b["win"] == win
    ]


def item_frequency(builds: list[dict[str, Any]], *, include_sold: bool = False) -> dict[str, Any]:
    """Item frequency, median buy time, and slot/tier across a set of builds.

    Sold items (transient lane flex) are excluded by default so the result
    reflects the kept build. include_sold counts them too, for the full
    purchase order.
    """
    n = len(builds)
    freq: Counter[str] = Counter()
    times: defaultdict[str, list[float]] = defaultdict(list)
    last_step: dict[str, dict[str, Any]] = {}

    for b in builds:
        steps = [s for s in b["seq"] if include_sold or not s.get("sold")]

        for step in {s["name"]: s for s in steps}.values():
            freq[step["name"]] += 1
            times[step["name"]].append(step["min"])
            last_step[step["name"]] = step

    rows = []
    for name, c in freq.most_common():
        rows.append(
            {
                "name": name,
                "percent": round(100 * c / n) if n else 0,
                "count": c,
                "median_min": round(st.median(times[name])),
                "slot": last_step[name]["slot"],
                "tier": last_step[name]["tier"],
            }
        )

    return {"n": n, "items": rows}


def tracked_player_games(
    names: Sequence[str] | None = None,
    hero: str | None = None,
    since: dt.date | None = None,
    parquet_dir: str | Path | None = None,
    tz: str | None = None,
) -> pl.LazyFrame:
    """Look up tracked players' own rows in the downloaded tables, one row per match and player.

    - names match the downloads table case-insensitively, None keeps every tracked player
    - joins players and matches, so hero, won, team and the local day come along
    - since keeps matches from that local day onward
    """
    parquet_dir = PARQUET_DIR if parquet_dir is None else Path(parquet_dir)
    tz = config.config_timezone() if tz is None else tz

    tracked = (
        queries.scan("downloads", parquet_dir).select("match_id", "account_id", "player").unique()
    )

    if names is not None:
        wanted = [n.lower() for n in names]
        tracked = tracked.filter(pl.col("player").str.to_lowercase().is_in(wanted))

    games = (
        tracked.join(queries.scan("players", parquet_dir), on=["match_id", "account_id"])
        .join(queries.scan("matches", parquet_dir), on="match_id")
        .with_columns(pl.col("start_time").dt.convert_time_zone(tz).alias("start_local"))
        .with_columns(pl.col("start_local").dt.date().alias("day"))
    )

    if hero is not None:
        games = games.filter(pl.col("hero") == hero)

    if since is not None:
        games = games.filter(pl.col("day") >= since)

    return games


def download_matches(
    tracked: list[dict[str, Any]], hero_id: int, n: int = 10
) -> list[dict[str, Any]]:
    """Query the API for recent ranked games from tracked players, one row per (match, player).

    tracked rows need account_id and name, and leaderboard entries also carry
    rank/region. Bodies persist in the API data directory (a match two tracked
    players share is only downloaded once), and downloaded_at comes from the
    body file's mtime, so re-runs keep the original download time.
    """
    rows = []

    for t in tracked:
        for m in recent_hero_matches(t["account_id"], hero_id, n):
            match_id = m["match_id"]

            try:
                match_metadata(match_id)
            except Exception:
                continue

            mtime = api.data_path(f"v1/matches/{match_id}/metadata").stat().st_mtime
            rows.append(
                {
                    "match_id": match_id,
                    "account_id": t["account_id"],
                    "player": t.get("name"),
                    "hero_id": hero_id,
                    "rank": t.get("rank"),
                    "region": t.get("region"),
                    "downloaded_at": dt.datetime.fromtimestamp(mtime, dt.UTC),
                }
            )

    return rows


def write_player_tables(
    download_rows: list[dict[str, Any]],
    out_dir: str | Path | None = None,
    assets_history: Path | None = None,
    exclude: Collection[str] = (),
) -> dict[str, int]:
    """Materialize downloaded matches into their own parquet directory, the standard tables plus downloads.

    - downloads accumulates across runs: new rows merge with the existing table,
      earliest downloaded_at winning per (match, player, hero)
    - the match tables fully rebuild from the stored API bodies for every
      match in downloads, downloading any body that went missing again
    - exclude skips tables by name, the same list export_all takes
    """
    out_dir = PARQUET_DIR if out_dir is None else Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    existing = out_dir / "downloads.parquet"
    old = pl.read_parquet(existing).to_dicts() if existing.exists() else []

    merged: dict[tuple[int, int, int], dict[str, Any]] = {}
    for r in old + download_rows:
        key = (r["match_id"], r["account_id"], r["hero_id"])

        if key not in merged or r["downloaded_at"] < merged[key]["downloaded_at"]:
            merged[key] = r

    downloads = sorted(merged.values(), key=lambda r: (r["match_id"], r["account_id"]))

    infos = []
    for match_id in sorted({r["match_id"] for r in downloads}):
        try:
            infos.append(extract.from_api_json(match_metadata(match_id)))
        except Exception:
            continue

    tables = export.build_tables(infos, assets_history, exclude)
    tables["downloads"] = schemas.conform("downloads", downloads)

    counts = {}
    for name, df in tables.items():
        df.write_parquet(out_dir / f"{name}.parquet")
        counts[name] = len(df)

    for name in exclude:
        (out_dir / f"{name}.parquet").unlink(missing_ok=True)

    return counts
