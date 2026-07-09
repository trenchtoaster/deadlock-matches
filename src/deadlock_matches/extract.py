"""Pulls the Deadlock match metadata protobufs out of the Steam httpcache."""

from __future__ import annotations

import bz2
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from google.protobuf import json_format

sys.path.insert(0, str(Path(__file__).parent / "gen"))

import citadel_gcmessages_common_pb2 as pb

from deadlock_matches import paths

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

MatchInfo = pb.CMsgMatchMetaDataContents.MatchInfo


def _linux_candidates() -> tuple[Path, ...]:
    """Steam httpcache locations on Linux, the native installs then flatpak."""
    return (
        Path.home() / ".steam/steam/appcache/httpcache",
        Path.home() / ".local/share/Steam/appcache/httpcache",
        Path.home() / ".var/app/com.valvesoftware.Steam/.local/share/Steam/appcache/httpcache",
    )


def _windows_candidates() -> tuple[Path, ...]:
    """Steam httpcache locations on Windows, the registry install path then the default."""
    found = []

    if sys.platform == "win32":
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                steam_path = winreg.QueryValueEx(key, "SteamPath")[0]
            found.append(Path(steam_path) / "appcache/httpcache")
        except OSError:
            pass

    found.append(Path("C:/Program Files (x86)/Steam/appcache/httpcache"))

    return tuple(found)


CACHE_CANDIDATES = _windows_candidates() if sys.platform == "win32" else _linux_candidates()


def default_cache(candidates: Sequence[Path] = CACHE_CANDIDATES) -> Path:
    """First Steam httpcache directory that exists, trying candidates in preference order."""
    for p in candidates:
        if p.is_dir():
            return p

    return candidates[0]


DEFAULT_CACHE = default_cache()
ARCHIVE_DIR = paths.data_dir() / "deadlock-matches/matches"
META_HOST = re.compile(rb"replay\d+\.valve\.net")
META_PATH = re.compile(rb"/1422450/(\d+)_(\d+)\.meta\.bz2")
DEADLOCK_APP_ID = "1422450"
STEAM64_BASE = 76561197960265728
LOGIN_BLOCK = re.compile(r'"(\d{17})"\s*\{([^{}]*)\}')
VDF_PAIR = re.compile(r'"([^"]+)"\s*"([^"]*)"')


@dataclass
class SteamAccount:
    """One Steam account found on this PC."""

    account_id: int
    login: str | None
    persona: str | None
    last_login: int


def _login_users(steam_root: Path) -> dict[int, dict[str, str]]:
    """Parse config/loginusers.vdf into {steam32: fields}, {} when Steam kept no logins."""
    vdf = steam_root / "config/loginusers.vdf"

    if not vdf.is_file():
        return {}

    users = {}
    for block in LOGIN_BLOCK.finditer(vdf.read_text(encoding="utf-8", errors="replace")):
        fields = dict(VDF_PAIR.findall(block.group(2)))
        users[int(block.group(1)) - STEAM64_BASE] = fields

    return users


def steam_accounts(cache_dir: str | Path = DEFAULT_CACHE) -> list[SteamAccount]:
    """List the Steam accounts on this PC that have run Deadlock, newest login first.

    - folder names under userdata/ are the Steam32 account IDs
    - a 1422450 folder inside means Deadlock ran on that account
    - login and persona names come from loginusers.vdf while Steam remembers the login
    """
    steam_root = Path(cache_dir).resolve().parent.parent
    userdata = steam_root / "userdata"

    if not userdata.is_dir():
        return []

    names = _login_users(steam_root)
    found = []

    for folder in userdata.iterdir():
        if not folder.name.isdigit() or folder.name == "0":
            continue

        if not (folder / DEADLOCK_APP_ID).is_dir():
            continue

        account_id = int(folder.name)
        fields = names.get(account_id, {})
        found.append(
            SteamAccount(
                account_id=account_id,
                login=fields.get("AccountName"),
                persona=fields.get("PersonaName"),
                last_login=int(fields.get("Timestamp", 0)),
            )
        )

    found.sort(key=lambda a: (-a.last_login, a.account_id))

    return found


def iter_meta_files(cache_dir: str | Path = DEFAULT_CACHE) -> Iterator[Path]:
    """Walk the httpcache and yield cache files that hold a match .meta.bz2."""
    cache_dir = Path(cache_dir)

    for path in cache_dir.rglob("*"):
        if not path.is_file():
            continue

        with path.open("rb") as f:
            head = f.read(1024)

        if META_PATH.search(head):
            yield path


def archive(cache_dir: str | Path = DEFAULT_CACHE, archive_dir: str | Path = ARCHIVE_DIR) -> int:
    """Copy match entries out of the live cache so Steam eviction can't lose them."""
    archive_dir = Path(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)

    new = 0
    for path in iter_meta_files(cache_dir):
        try:
            parsed = parse_cache_file(path)
        except ValueError:
            continue

        dest = archive_dir / f"{parsed.match_id}_{parsed.replay_salt}.bin"
        if not dest.exists():
            dest.write_bytes(path.read_bytes())
            new += 1

    return new


def iter_matches(
    cache_dir: str | Path = DEFAULT_CACHE, archive_dir: str | Path = ARCHIVE_DIR
) -> Iterator[Path]:
    """Sync the live cache into the archive, then yield every archived match in descending match_id order."""
    archive(cache_dir, archive_dir)

    yield from sorted(
        Path(archive_dir).glob("*.bin"), key=lambda p: int(p.name.split("_")[0]), reverse=True
    )


@dataclass(frozen=True)
class CacheFile:
    """One parsed .meta cache entry with its source URL and the protobuf body."""

    url: str
    match_id: int
    replay_salt: int
    raw: bytes


def parse_cache_file(path: str | Path) -> CacheFile:
    """Parse one cache file (or archived copy) to a CacheFile."""
    data = Path(path).read_bytes()

    m = META_PATH.search(data)
    if not m:
        msg = f"not a deadlock meta cache file: {path}"
        raise ValueError(msg)

    host = META_HOST.search(data)
    url = (host.group(0).decode() if host else "") + m.group(0).decode()

    start = data.find(b"BZh")
    if start < 0:
        msg = f"no bzip2 body in {path}"
        raise ValueError(msg)

    raw = bz2.BZ2Decompressor().decompress(data[start:])

    return CacheFile(url, int(m.group(1)), int(m.group(2)), raw)


def decode(protobuf_bytes: bytes) -> MatchInfo:
    """Parse a decompressed CMsgMatchMetaData body into a MatchInfo message."""
    meta = pb.CMsgMatchMetaData()
    meta.ParseFromString(protobuf_bytes)

    contents = pb.CMsgMatchMetaDataContents()
    contents.ParseFromString(meta.match_details)

    return contents.match_info


def load(path: str | Path) -> MatchInfo:
    """Read one cache file (or archived copy) straight to a MatchInfo."""
    return decode(parse_cache_file(path).raw)


def from_api_json(match_info: dict[str, Any]) -> MatchInfo:
    """Parse the API match_info json into the same MatchInfo the cache files yield.

    Verified identical, field for field, to what the cache files yield. Wire
    fields our .proto does not define yet are dropped, which the cache path
    cannot read either.
    """
    return json_format.ParseDict(match_info, MatchInfo(), ignore_unknown_fields=True)
