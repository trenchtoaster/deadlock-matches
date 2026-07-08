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


def assets_history_dir() -> Path:
    """Dated asset snapshots, one folder per refresh date."""
    return data_dir() / "deadlock-matches/assets"
