"""Download matches from other players and build the parquet-players tables."""

from __future__ import annotations

import datetime as dt
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

from deadlock_matches import api, config, export, extract, heroes, paths, queries, schemas

if TYPE_CHECKING:
    from collections.abc import Collection, Iterator, Sequence

    from deadlock_matches.extract import MatchInfo

REGIONS = ("Europe", "NAmerica", "Asia", "SAmerica", "Oceania")
PARQUET_DIR = paths.data_dir() / "deadlock-matches/parquet-players"


def leaderboard(region: str) -> list[dict[str, Any]]:
    """Ranked ladder entries for a region (one of REGIONS)."""
    lb = api.get_json(f"v1/leaderboard/{region}", max_age=api.DAY)

    return lb.get("entries", lb) if isinstance(lb, dict) else lb


def hero_leaderboard(region: str, hero_id: int) -> list[dict[str, Any]]:
    """Per-hero leaderboard entries for a region (rank is the hero rank)."""
    lb = api.get_json(f"v1/leaderboard/{region}/{hero_id}", max_age=api.DAY)

    return lb.get("entries", lb) if isinstance(lb, dict) else lb


def top_players(
    hero_id: int,
    regions: Sequence[str] = REGIONS,
    limit: int = 8,
    *,
    unambiguous: bool = True,
) -> list[dict[str, Any]]:
    """Top players of a hero from the per-hero leaderboards, best hero rank first.

    Pools the regional hero boards, so the same rank appears once per region.
    unambiguous keeps only entries that resolve to a single account ID, since
    players with lots of smurfs expose many candidate IDs with no way to pick one.
    """
    out = []
    for region in regions:
        for e in hero_leaderboard(region, hero_id):
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


def ladder_positions(hero_id: int, regions: Sequence[str] = REGIONS) -> dict[int, dict[str, Any]]:
    """Map account IDs to their current spot on the per hero leaderboards.

    - pools every region and keeps the best rank per account
    - skips entries that resolve to more than one account
    - comes back empty when the leaderboards are unreachable
    """
    spots: dict[int, dict[str, Any]] = {}

    for region in regions:
        try:
            entries = hero_leaderboard(region, hero_id)
        except OSError:
            continue

        for e in entries:
            ids = e.get("possible_account_ids") or []

            if len(ids) != 1:
                continue

            spot = {"name": e.get("account_name"), "rank": e["rank"], "region": region}

            if ids[0] not in spots or e["rank"] < spots[ids[0]]["rank"]:
                spots[ids[0]] = spot

    return spots


def match_history(account_id: int) -> list[dict[str, Any]]:
    """List the recent matches for a player, by account ID."""
    d = api.get_json(f"v1/players/{account_id}/match-history", max_age=api.DAY)

    return d.get("matches", d) if isinstance(d, dict) else d


def _body_path(match_id: int, archive_dir: str | Path) -> Path | None:
    """Locate the archived body for a match.

    - downloads the raw metadata when the match is not archived yet
    """
    path = extract.match_path(archive_dir, match_id)

    if path is not None:
        return path

    download_metadata([match_id], archive_dir)

    return extract.match_path(archive_dir, match_id)


def match_info(match_id: int, archive_dir: str | Path = extract.ARCHIVE_DIR) -> MatchInfo | None:
    """Load the MatchInfo for a match, either archived or downloaded on demand."""
    path = _body_path(match_id, archive_dir)

    if path is None:
        return None

    return extract.load(path)


def salts(match_id: int) -> dict[str, Any] | None:
    """Return the metadata and replay salts for a match."""
    try:
        return api.get_json(f"v1/matches/{match_id}/salts", use_cache=False)

    except OSError:
        return None


def recent_hero_matches(account_id: int, hero_id: int, n: int = 10) -> list[dict[str, Any]]:
    """List the N most recent ranked match-history rows for a player on a hero."""
    ms = [
        m
        for m in match_history(account_id)
        if m.get("hero_id") == hero_id and m.get("match_mode") == 1
    ]
    ms.sort(key=lambda m: -m["start_time"])

    return ms[:n]


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
    """Look up rows for the tracked players themselves in the downloaded tables, one row per match and player.

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


def pool_members(
    hero: str,
    parquet_dir: str | Path | None = None,
    config_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Summarize the comparison pool of a hero with one entry per tracked player.

    - the pool is the [players.<hero>] table in config.toml, matched to the
      downloads ledger by account id
    - games counts downloaded matches on the hero, 0 before any download
    - rank is the best ladder rank seen at download time
    """
    watchlist = config.config_players(hero, config_path)

    if not watchlist:
        return []

    hero_id = heroes.hero_id_by_name(hero)
    parquet_dir = PARQUET_DIR if parquet_dir is None else Path(parquet_dir)
    stats: dict[int, dict[str, Any]] = {}

    if queries.table_exists("downloads", parquet_dir):
        ledger = (
            queries.scan("downloads", parquet_dir)
            .filter(
                pl.col("hero_id") == hero_id,
                pl.col("account_id").is_in(list(watchlist.values())),
            )
            .group_by("account_id")
            .agg(
                pl.col("match_id").n_unique().alias("games"),
                pl.col("rank").min().alias("rank"),
                pl.col("downloaded_at").max().alias("downloaded_at"),
            )
            .collect()
        )
        stats = {r["account_id"]: r for r in ledger.iter_rows(named=True)}

    return [
        {
            "name": name,
            "account_id": a,
            "games": stats.get(a, {}).get("games", 0),
            "rank": stats.get(a, {}).get("rank"),
            "downloaded_at": stats.get(a, {}).get("downloaded_at"),
        }
        for name, a in watchlist.items()
    ]


def pool_games(
    hero: str,
    parquet_dir: str | Path | None = None,
    config_path: str | Path | None = None,
) -> pl.LazyFrame:
    """List the pool of a hero as one downloads ledger row per downloaded game.

    - keeps match_id, account_id, rank, and downloaded_at
    - comes back empty when nothing is tracked or downloaded yet
    """
    watchlist = config.config_players(hero, config_path)
    parquet_dir = PARQUET_DIR if parquet_dir is None else Path(parquet_dir)

    if not watchlist or not queries.table_exists("downloads", parquet_dir):
        return pl.LazyFrame(
            schema={
                "match_id": pl.Int64,
                "account_id": pl.Int64,
                "rank": pl.Int64,
                "downloaded_at": pl.Datetime("us", "UTC"),
            }
        )

    hero_id = heroes.hero_id_by_name(hero)

    return (
        queries.scan("downloads", parquet_dir)
        .filter(
            pl.col("hero_id") == hero_id,
            pl.col("account_id").is_in(list(watchlist.values())),
        )
        .select("match_id", "account_id", "rank", "downloaded_at")
        .unique(subset=["match_id", "account_id"])
    )


def pool_builds(
    hero: str,
    parquet_dir: str | Path | None = None,
    config_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Collect one build dict per downloaded pool game from the item_events table.

    - reads item_events, so it works offline from past downloads
    - each build carries the config player label, the win, and the buy
      sequence in build_order shape
    """
    parquet_dir = PARQUET_DIR if parquet_dir is None else Path(parquet_dir)

    if not queries.table_exists("item_events", parquet_dir):
        return []

    watchlist = config.config_players(hero, config_path)
    labels = {a: name for name, a in watchlist.items()}
    events = (
        pool_games(hero, parquet_dir, config_path)
        .join(queries.scan("item_events", parquet_dir), on=["match_id", "account_id"])
        .filter(pl.col("item").is_not_null(), pl.col("cost") > 0)
        .join(
            queries.scan("players", parquet_dir).select("match_id", "account_id", "won"),
            on=["match_id", "account_id"],
        )
        .sort("match_id", "account_id", "game_time_s")
        .collect()
    )

    builds: dict[tuple[int, int], dict[str, Any]] = {}

    for r in events.iter_rows(named=True):
        key = (r["match_id"], r["account_id"])
        b = builds.setdefault(
            key,
            {
                "match_id": r["match_id"],
                "account_id": r["account_id"],
                "player": labels.get(r["account_id"]),
                "win": r["won"],
                "seq": [],
            },
        )
        b["seq"].append(
            {
                "min": round(r["game_time_s"] / 60, 1),
                "name": r["item"],
                "tier": r["tier"],
                "slot": r["slot"],
                "cost": r["cost"],
                "sold": bool(r["sold_time_s"]),
            }
        )

    return list(builds.values())


def download_matches(
    tracked: list[dict[str, Any]],
    hero_id: int,
    n: int = 10,
    archive_dir: str | Path = extract.ARCHIVE_DIR,
) -> list[dict[str, Any]]:
    """Download recent ranked games from tracked players, one row per (match, player).

    - tracked rows need account_id and name, leaderboard entries also carry rank/region
    - bodies land in the archive as raw .bin files, a shared match downloads once
    - downloaded_at is the mtime of the body file, which re-runs never touch
    """
    rows = []

    for t in tracked:
        for m in recent_hero_matches(t["account_id"], hero_id, n):
            match_id = m["match_id"]
            path = _body_path(match_id, archive_dir)

            if path is None:
                continue

            rows.append(
                {
                    "match_id": match_id,
                    "account_id": t["account_id"],
                    "player": t.get("name"),
                    "hero_id": hero_id,
                    "rank": t.get("rank"),
                    "region": t.get("region"),
                    "downloaded_at": dt.datetime.fromtimestamp(path.stat().st_mtime, dt.UTC),
                }
            )

    return rows


def matches_by_id(
    match_ids: Sequence[int], archive_dir: str | Path = extract.ARCHIVE_DIR
) -> list[dict[str, Any]]:
    """Download rows for specific match IDs straight into the archive.

    account_id/hero_id/rank/region come back null since no tracked player brought
    the match in. The body carries all 12 players, so every one lands in the tables
    and match --hero picks any of them. Unreachable ids are skipped.
    """
    rows = []

    for match_id in match_ids:
        path = _body_path(match_id, archive_dir)

        if path is None:
            continue

        rows.append(
            {
                "match_id": match_id,
                "account_id": None,
                "player": None,
                "hero_id": None,
                "rank": None,
                "region": None,
                "downloaded_at": dt.datetime.fromtimestamp(path.stat().st_mtime, dt.UTC),
            }
        )

    return rows


def _merge_downloads(out_dir: Path, download_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold new download rows into the existing ledger and keep the earliest download per key."""
    existing = out_dir / "downloads.parquet"
    old = pl.read_parquet(existing).to_dicts() if existing.exists() else []

    merged: dict[tuple[int, int, int], dict[str, Any]] = {}

    for r in old + download_rows:
        key = (r["match_id"], r["account_id"], r["hero_id"])

        if key not in merged or r["downloaded_at"] < merged[key]["downloaded_at"]:
            merged[key] = r

    return sorted(
        merged.values(),
        key=lambda r: (r["match_id"], r["account_id"] is None, r["account_id"] or 0),
    )


def _decode_bodies(match_ids: list[int], archive_dir: str | Path) -> Iterator[MatchInfo]:
    """Decode the stored body for each match id in order and skip any that fail."""
    for match_id in match_ids:
        try:
            info = match_info(match_id, archive_dir)

        except Exception:
            continue

        if info is not None:
            yield info


def download_metadata(match_ids: Sequence[int], archive_dir: str | Path) -> tuple[int, list[int]]:
    """Download the raw metadata for each match into the archive as a .bin.

    - returns how many landed and the match ids the API could not provide
    - the .meta.bz2 comes from the Valve replay server, falling back to the API
    """
    written = 0
    missing: list[int] = []

    for match_id in match_ids:
        if extract.has_match(archive_dir, match_id):
            continue

        info = salts(match_id)

        if info is None or "metadata_salt" not in info:
            missing.append(match_id)
            continue

        url = info.get("metadata_url")
        body = (api.get_bytes(url) if url else None) or api.get_bytes(
            f"{api.BASE}/v1/matches/{match_id}/metadata/raw"
        )

        if body is None:
            missing.append(match_id)
            continue

        extract.store_meta(archive_dir, match_id, info["metadata_salt"], body, url)
        written += 1

    return written, missing


def _store_counts(out_dir: Path, exclude: Collection[str], downloads_n: int) -> dict[str, int]:
    """Row totals per match table plus the downloads ledger size."""
    counts: dict[str, int] = {}

    for name in schemas.TABLES:
        if name not in schemas.PARTITIONED or name in exclude:
            continue

        if queries.table_exists(name, out_dir):
            counts[name] = queries.scan(name, out_dir).select(pl.len()).collect().item()

    counts["downloads"] = downloads_n

    return counts


def write_player_tables(
    download_rows: list[dict[str, Any]],
    out_dir: str | Path | None = None,
    exclude: Collection[str] = (),
    archive_dir: str | Path = extract.ARCHIVE_DIR,
) -> dict[str, int]:
    """Materialize downloaded matches into their own parquet directory plus the downloads ledger.

    - downloads accumulates across runs and the earliest downloaded_at wins per (match, player, hero)
    - match bodies are immutable so only match_ids not already built get decoded and appended
    - a legacy single-file store is re-laid-out into partitions first, without decoding anything
    - a schema drift rebuilds from the stored bodies into a staging area and swaps it in,
      carrying any match that cannot be decoded forward so live tables are never lost
    - nothing is pruned, so player history builds up across runs
    """
    out_dir = PARQUET_DIR if out_dir is None else Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    downloads = _merge_downloads(out_dir, download_rows)
    wanted = sorted({r["match_id"] for r in downloads})

    if export.is_legacy_layout(out_dir):
        export.migrate_to_partitions(out_dir, exclude)

    if export.schema_drift(out_dir, exclude):
        export.rebuild_drifted_partitions(_decode_bodies(wanted, archive_dir), out_dir, exclude)

    exported = export.exported_match_ids(out_dir)
    new_ids = [m for m in wanted if m not in exported]

    export.export_infos(_decode_bodies(new_ids, archive_dir), out_dir, exclude)

    schemas.conform("downloads", downloads).write_parquet(out_dir / "downloads.parquet")

    return _store_counts(out_dir, exclude, len(downloads))
