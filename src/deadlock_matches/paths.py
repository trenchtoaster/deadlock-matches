"""Where user data and caches live on Linux and Windows."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    """~/.local/share on Linux, %LOCALAPPDATA% on Windows."""
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")

    return Path.home() / ".local/share"


def cache_dir() -> Path:
    """~/.cache/deadlock-matches on Linux, LOCALAPPDATA/deadlock-matches/cache on Windows."""
    if sys.platform == "win32":
        return data_dir() / "deadlock-matches/cache"

    return Path.home() / ".cache/deadlock-matches"


def tilde(path: str | Path) -> str:
    """Shorten a path under the home directory to a ~ prefix for printing."""
    p = Path(path).resolve()
    home = Path.home().resolve()

    if p.is_relative_to(home):
        return "~/" + p.relative_to(home).as_posix()

    return str(p)
