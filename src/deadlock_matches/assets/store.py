"""Resolve asset files, preferring the writable user store over the bundled seed."""

from __future__ import annotations

from pathlib import Path

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
