"""Resolve asset files, preferring the writable user store over the bundled seed."""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from deadlock_matches import paths

SEED_DIR = Path(__file__).parent / "data"


def store_dir() -> Path:
    """User asset store, where refresh and backfill write."""
    return paths.data_dir() / "deadlock-matches" / "assets"


def seed_path(name: str) -> Path:
    """Bundled seed file shipped inside the package."""
    return SEED_DIR / name


def read_path(name: str) -> Path:
    """Asset file to read, the user store when it exists, else the bundled seed."""
    stored = store_dir() / name

    return stored if stored.exists() else seed_path(name)


def write_path(name: str) -> Path:
    """Asset file to write, always the user store, with its parent created."""
    target = store_dir() / name
    target.parent.mkdir(parents=True, exist_ok=True)

    return target


def is_source_checkout() -> bool:
    """Return whether the package runs from a deadlock-matches source checkout.

    - true only when the nearest pyproject.toml above it names deadlock-matches
    """
    import tomllib

    for parent in SEED_DIR.parents:
        pyproject = parent / "pyproject.toml"

        if pyproject.is_file():
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

            return data.get("project", {}).get("name") == "deadlock-matches"

    return False


@functools.cache
def load_map(
    name: str,
    key: str,
    from_record: Callable[[dict[str, Any]], Any],
    path: Path | None = None,
) -> dict[Any, Any]:
    """Load a json asset file into a dict keyed by one record field."""
    src = Path(path) if path is not None else read_path(name)
    records = json.loads(src.read_text(encoding="utf-8"))

    return {rec[key]: from_record(rec) for rec in records}


@functools.cache
def name_index(
    load: Callable[[Path | None], dict[Any, Any]],
    normalize: Callable[[str], str],
    path: Path | None = None,
) -> dict[str, tuple[Any, ...]]:
    """Group the values of a loaded asset map by their normalized display name."""
    index: dict[str, tuple[Any, ...]] = {}

    for value in load(path).values():
        wanted = normalize(value.name)
        index[wanted] = (*index.get(wanted, ()), value)

    return index


_CACHES: list[Callable[[], None]] = [load_map.cache_clear, name_index.cache_clear]


def register_cache(clear: Callable[[], None]) -> None:
    """Add a lookup cache to the set clear_maps empties."""
    _CACHES.append(clear)


def clear_maps() -> None:
    """Empty every cached asset lookup, for use after a snapshot refresh."""
    for clear in _CACHES:
        clear()
