"""HTTP client for the deadlock-api, with two storage tiers.

- immutable bodies (per-build asset snapshots) live gzipped in the data directory
- everything else expires by file age in the cache directory, stale entries still serve offline
- cache files untouched for 30 days purge on the first request of a process

Endpoints in use, one named wrapper each:

- v1/leaderboard/{region} -> players.leaderboard
- v1/leaderboard/{region}/{hero_id} -> players.hero_leaderboard
- v1/players/{account_id}/match-history -> players.match_history
- v1/matches/{match_id}/salts -> players.salts
- v1/matches/{match_id}/metadata/raw -> players.download_metadata, when the replay server lacks a match
- v1/analytics/item-stats?hero_id= -> meta.get_item_stats
- v1/analytics/item-permutation-stats?hero_id=&comb=2 -> meta.get_item_pairs
- v1/analytics/hero-stats -> meta.get_hero_stats
- v1/assets/heroes -> assets.refresh_heroes
- v1/assets/items/by-type/{kind} -> assets.refresh_items / refresh_abilities
- v1/assets/ranks -> assets.refresh_skill_rating
- v1/assets/accolades -> assets.refresh_accolades
- v1/assets/misc-entities -> assets.refresh_statues
- v1/assets/steam-info/all -> assets.client_version_dates
- the assets endpoints above with ?client_version= -> assets backfill, permanent per build

Full API surface: https://api.deadlock-api.com/docs
"""

from __future__ import annotations

import collections
import gzip
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

from deadlock_matches import paths

BASE = "https://api.deadlock-api.com"
CACHE_DIR = paths.cache_dir() / "api"
DATA_DIR = paths.data_dir() / "deadlock-matches/api"

DAY = 86_400
PRUNE_AGE = 30 * DAY

fetch_counts: collections.Counter[str] = collections.Counter()


def _filename(path: str) -> str:
    """Flatten a request path into one file name."""
    return path.replace("/", "_").replace("?", "_").replace("&", "_") + ".json"


def cache_path(path: str) -> Path:
    """Cache file for a request path, whose mtime records when it was downloaded."""
    return CACHE_DIR / _filename(path)


def data_path(path: str) -> Path:
    """Permanent file for a request path, stored gzipped since the body never changes."""
    return DATA_DIR / (_filename(path) + ".gz")


def _read_body(file: Path) -> Any:
    """Parse a stored response body, gzipped or plain by suffix."""
    if file.suffix == ".gz":
        return json.loads(gzip.decompress(file.read_bytes()))

    return json.loads(file.read_text(encoding="utf-8"))


def _write_body(file: Path, data: Any) -> None:
    """Write a response body the way its suffix says."""
    if file.suffix == ".gz":
        file.write_bytes(gzip.compress(json.dumps(data).encode()))
    else:
        file.write_text(json.dumps(data), encoding="utf-8")


def _expired(file: Path, max_age: float | None) -> bool:
    """Whether a stored body is older than its lifetime."""
    if max_age is None:
        return False

    return time.time() - file.stat().st_mtime > max_age


_pruned = False


def _prune_cache() -> None:
    """Delete cached responses untouched for PRUNE_AGE, once per process.

    - only walks the flat CACHE_DIR, the data directory and the match archive stay out
    - only deletes v1*.json names, the shape this module writes
    """
    global _pruned

    if _pruned:
        return

    _pruned = True

    if not CACHE_DIR.is_dir():
        return

    cutoff = time.time() - PRUNE_AGE

    for f in CACHE_DIR.glob("v1*.json"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)


def get_json(
    path: str, *, use_cache: bool = True, max_age: float | None = None, permanent: bool = False
) -> Any:
    """GET json from the API, with a disk cache.

    - max_age is the cache lifetime in seconds, None never expires
    - permanent stores the body gzipped in the data directory and never refetches
    - use_cache=False bypasses the store, nothing is read or written
    - an expired entry is still served when the network is down
    - fetch_counts tallies cached and downloaded responses for progress reporting
    """
    _prune_cache()

    target = data_path(path) if permanent else cache_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    if permanent and not target.exists() and cache_path(path).exists():
        _write_body(target, _read_body(cache_path(path)))
        cache_path(path).unlink()

    if permanent:
        max_age = None

    if use_cache and target.exists() and not _expired(target, max_age):
        fetch_counts["cached"] += 1
        return _read_body(target)

    req = urllib.request.Request(f"{BASE}/{path}", headers={"User-Agent": "deadlock-matches/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except OSError:
        if use_cache and target.exists():
            fetch_counts["cached"] += 1
            return _read_body(target)

        raise

    fetch_counts["downloaded"] += 1

    if use_cache:
        _write_body(target, data)

    return data


def get_bytes(url: str) -> bytes | None:
    """Download the raw bytes at a full URL, or None when it cannot be reached."""
    req = urllib.request.Request(url, headers={"User-Agent": "deadlock-matches/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()

    except OSError:
        return None
