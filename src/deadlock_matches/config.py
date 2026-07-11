"""Read and create the gitignored config.toml at the repo root."""

from __future__ import annotations

import datetime as dt
import os
import tomllib
import zoneinfo
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.toml"


def _config(path: str | Path | None = None) -> dict[str, Any]:
    """Parse config.toml, or {} when the file is missing.

    - invalid TOML exits with the line number
    """
    path = Path(path) if path else CONFIG_PATH

    if not path.exists():
        return {}

    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        msg = f"{path.name} is not valid TOML: {e}"

        raise SystemExit(msg) from e


def _accounts_table(path: str | Path | None) -> dict[str, Any]:
    """Read the [accounts] table from config.toml, {} when unset.

    - anything but a table (like accounts = [42]) exits with the expected shape
    """
    accounts = _config(path).get("accounts") or {}

    if not isinstance(accounts, dict):
        msg = "config.toml accounts must be an [accounts] table of name = id pairs"
        raise SystemExit(msg)

    return accounts


def config_accounts(path: str | Path | None = None) -> list[int] | None:
    """Read the default Steam32 account IDs from the gitignored config.toml at the repo root.

    - accounts is an [accounts] table of name = id pairs
    - several accounts mean the union, every one counts as you
    """
    return [int(a) for a in _accounts_table(path).values()] or None


def config_account_names(path: str | Path | None = None) -> dict[str, int]:
    """Read the name = id pairs from the [accounts] table."""
    return {name: int(a) for name, a in _accounts_table(path).items()}


def format_accounts(ids: Iterable[int], path: str | Path | None = None) -> str:
    """Format account IDs for report headers, swapping in config names where known."""
    names = {a: name for name, a in config_account_names(path).items()}

    return ", ".join(names.get(int(a), str(a)) for a in ids)


def config_players(hero: str, path: str | Path | None = None) -> dict[str, int]:
    """Selected {player: account_id} comparison targets for a hero from config.toml.

    Reads the [players.<hero>] table and matches the hero name case-insensitively.
    """
    by_hero = _config(path).get("players") or {}

    for name, ids in by_hero.items():
        if name.lower() == hero.lower():
            return {player: int(a) for player, a in ids.items()}

    return {}


def config_exclude(path: str | Path | None = None) -> set[str]:
    """Table names the export skips, from the exclude list in config.toml."""
    return {str(t) for t in _config(path).get("exclude") or []}


def ensure_config(path: str | Path | None = None) -> None:
    """Write a starter config.toml to fill in when none exists yet.

    - the movement table is excluded by default because it tracks movement
      per second per game
    """
    path = Path(path) if path else CONFIG_PATH

    if path.exists():
        return

    starter = f"""# tables the export skips. movement is one row per player per second,
# delete it from this list to export it. the per minute movement_intervals
# table always builds
exclude = ["movement"]

# matches group into local days in this zone
timezone = "{_detect_timezone()}"

# your Steam32 account IDs. `deadlock accounts` lists the ones on this PC.
# the name is yours to pick and works anywhere --account does, like --account main
[accounts]
# main = 111222333
# "old alt" = 123456789

# the players every comparison runs against, per hero: top ladder accounts, rivals,
# one-tricks. compare, movement, builds, and item read only games downloaded from the
# players listed here. `deadlock leaderboard --hero X` prints paste-ready lines, then
# `deadlock download --hero X` fetches their recent games - nothing is ever downloaded
# from the leaderboard on its own. removing a line here removes the player from every
# comparison, the downloaded data just stops being read.
# the player name is just a label for the reports, paste their real name or make one up.
# quotes around hero and player names are always safe, and required when a name has spaces.
# [players."Mirage"]
# "someplayer" = 111222333
#
# [players."Grey Talon"]
# "Other Player" = 444555666
"""
    path.write_text(starter, encoding="utf-8")


def _detect_timezone() -> str:
    """Guess the local zone from the OS, stdlib only.

    - TZ env var, then the /etc/localtime symlink, then Debian's /etc/timezone,
      each validated against the zoneinfo database
    - falls back to the current fixed UTC offset ("+08:00"), which polars accepts, and
      only DST zones on Windows lose anything by that
    """
    candidates = [os.environ.get("TZ")]

    localtime = Path("/etc/localtime")
    if localtime.is_symlink():
        target = localtime.readlink().as_posix()
        if "zoneinfo/" in target:
            candidates.append(target.split("zoneinfo/", 1)[1])

    etc_tz = Path("/etc/timezone")
    if etc_tz.is_file():
        candidates.append(etc_tz.read_text(encoding="utf-8").strip())

    for c in candidates:
        if not c:
            continue

        try:
            zoneinfo.ZoneInfo(c)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError, KeyError):
            continue

        return c

    offset = dt.datetime.now().astimezone().strftime("%z")

    return f"{offset[:3]}:{offset[3:]}" if offset else "UTC"


def config_timezone(path: str | Path | None = None) -> str:
    """Timezone for grouping matches by local day.

    Uses config.toml's timezone if set. The starter config pins the detected
    zone at creation, so this only falls back to detection for hand-written
    configs that left it out.
    """
    if tz := _config(path).get("timezone"):
        return tz

    return _detect_timezone()
