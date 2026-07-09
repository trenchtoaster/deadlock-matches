"""HTTP client for the deadlock-api, with two storage tiers.

Immutable bodies (match metadata) persist in the data directory next to the
match archive, since the parquet-players tables rebuild from them. Everything
else is a real cache under the cache directory: entries expire by file age
(max_age) and an expired entry is still served when the network is down.

Endpoints in use, one named wrapper each:

- v1/leaderboard/{region} -> players.leaderboard
- v1/leaderboard/{region}/{hero_id} -> players.hero_leaderboard
- v1/players/{account_id}/match-history -> players.match_history
- v1/matches/{match_id}/metadata -> players.match_metadata (backfill + ground truth for extract.py)
- v1/analytics/item-stats?hero_id= -> meta.get_item_stats
- v1/analytics/item-permutation-stats?hero_id=&comb=2 -> meta.get_item_pairs
- v1/analytics/hero-stats -> meta.get_hero_stats
- v1/assets/heroes -> assets.refresh_heroes
- v1/assets/items/by-type/{kind} -> assets.refresh_items / refresh_abilities

Full API surface: https://api.deadlock-api.com/docs
"""

from __future__ import annotations

import collections
import json
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Any

from deadlock_matches import paths

BASE = "https://api.deadlock-api.com"
CACHE_DIR = paths.cache_dir() / "api"
DATA_DIR = paths.data_dir() / "deadlock-matches/api"

DAY = 86_400

fetch_counts: collections.Counter[str] = collections.Counter()


def _filename(path: str) -> str:
    """Flatten a request path into one file name."""
    return path.replace("/", "_").replace("?", "_").replace("&", "_") + ".json"


def cache_path(path: str) -> Path:
    """Cache file for a request path, whose mtime records when it was downloaded."""
    return CACHE_DIR / _filename(path)


def data_path(path: str) -> Path:
    """Permanent file for a request path, for bodies that never change."""
    return DATA_DIR / _filename(path)


def _expired(file: Path, max_age: float | None) -> bool:
    """Whether a stored body is older than its lifetime."""
    if max_age is None:
        return False

    return time.time() - file.stat().st_mtime > max_age


def get_json(
    path: str, *, use_cache: bool = True, max_age: float | None = None, permanent: bool = False
) -> Any:
    """GET json from the API, with a disk cache.

    - max_age is the cache lifetime in seconds, None never expires
    - permanent stores the body in the data directory instead and never
      refetches, for immutable responses like match metadata
    - an expired entry is still served when the network is down
    - fetch_counts tallies cached and downloaded responses for progress reporting
    """
    target = data_path(path) if permanent else cache_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    if permanent and not target.exists() and cache_path(path).exists():
        shutil.move(cache_path(path), target)

    if permanent:
        max_age = None

    if use_cache and target.exists() and not _expired(target, max_age):
        fetch_counts["cached"] += 1
        return json.loads(target.read_text(encoding="utf-8"))

    req = urllib.request.Request(f"{BASE}/{path}", headers={"User-Agent": "deadlock-matches/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r)
    except OSError:
        if use_cache and target.exists():
            fetch_counts["cached"] += 1
            return json.loads(target.read_text(encoding="utf-8"))

        raise

    fetch_counts["downloaded"] += 1
    target.write_text(json.dumps(data), encoding="utf-8")

    return data


def get_bytes(url: str) -> bytes | None:
    """Download the raw bytes at a full URL, or None when it cannot be reached."""
    req = urllib.request.Request(url, headers={"User-Agent": "deadlock-matches/1.0"})

    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()

    except OSError:
        return None
