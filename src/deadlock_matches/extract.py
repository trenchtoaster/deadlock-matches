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


def installed_client_version(cache_dir: str | Path = DEFAULT_CACHE) -> int | None:
    """Read the installed Deadlock client build from steam.inf, None without an install.

    - the Steam root sits two levels above the httpcache
    - checks the root plus every library folder listed in libraryfolders.vdf
    - ClientVersion uses the same numbering as the asset history client_version
    - Steam updates steam.inf before a post-patch match can be played
    """
    root = Path(cache_dir).parent.parent
    libraries = [root]
    vdf = root / "steamapps/libraryfolders.vdf"

    if vdf.is_file():
        listed = re.findall(
            r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="replace")
        )
        libraries.extend(Path(p) for p in listed)

    for library in libraries:
        inf = library / "steamapps/common/Deadlock/game/citadel/steam.inf"

        if not inf.is_file():
            continue

        for line in inf.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("ClientVersion="):
                return int(line.removeprefix("ClientVersion=").strip())

    return None


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
    """Copy match entries out of the live cache so Steam eviction cannot lose them."""
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


def archived_match_ids(archive_dir: str | Path = ARCHIVE_DIR) -> set[int]:
    """Return the match ids already saved as .bin files in the archive."""
    return {int(p.name.split("_")[0]) for p in Path(archive_dir).glob("*.bin")}


def match_path(archive_dir: str | Path, match_id: int) -> Path | None:
    """Return the archived .bin path for a match id."""
    return next(Path(archive_dir).glob(f"{match_id}_*.bin"), None)


def has_match(archive_dir: str | Path, match_id: int) -> bool:
    """Return True when a .bin for this match id is already archived."""
    return match_path(archive_dir, match_id) is not None


def store_meta(
    archive_dir: str | Path, match_id: int, salt: int, meta_bz2: bytes, url: str | None = None
) -> None:
    """Write a downloaded .meta.bz2 body into the archive as a cache-shaped {match_id}_{salt}.bin.

    - the header line is the download url when it names the canonical path,
      the bare path otherwise, and parse_cache_file reads either form
    - a url header carries the replay cluster like a copied cache entry
    - the salt matches the httpcache filename, so the same match from both sources is one file
    """
    archive_dir = Path(archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)

    path = f"/1422450/{match_id}_{salt}.meta.bz2"
    header = url if url and path in url else path
    dest = archive_dir / f"{match_id}_{salt}.bin"
    tmp = dest.with_name(f"{dest.name}.tmp")
    tmp.write_bytes(f"{header}\n".encode() + meta_bz2)
    tmp.replace(dest)


def iter_matches(
    cache_dir: str | Path = DEFAULT_CACHE, archive_dir: str | Path = ARCHIVE_DIR
) -> Iterator[Path]:
    """Sync the live cache into the archive and then yield every archived match in descending match_id order."""
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


PARTY_FIELD = 16


def _read_varint(data: bytes, i: int) -> tuple[int, int]:
    """Decode one varint starting at i and return (value, next index)."""
    value = 0
    shift = 0

    while True:
        byte = data[i]
        i += 1
        value |= (byte & 0x7F) << shift
        shift += 7

        if not byte & 0x80:
            return value, i


def player_party(player: Any) -> int | None:
    """Read the party id from field 16 (currently removed).

    Valve dropped the field mid-March 2026, so it survives only as an
    unknown field on older archived matches. 0 = queued solo, players
    sharing a nonzero id queued together, None = the field is gone.
    """
    data = player.SerializeToString()
    i = 0

    while i < len(data):
        tag, i = _read_varint(data, i)
        number, wire_type = tag >> 3, tag & 7

        if wire_type == 0:
            value, i = _read_varint(data, i)

            if number == PARTY_FIELD:
                return value

        elif wire_type == 1:
            i += 8

        elif wire_type == 2:
            length, i = _read_varint(data, i)
            i += length

        elif wire_type == 5:
            i += 4

        else:
            return None

    return None


def custom_stats(info: MatchInfo) -> dict[int, list[tuple[int, str | None, str, int]]]:
    """Resolve custom stat ids through the match registry and return each player as (time, group, stat, value) snapshot rows."""
    id_to_name = {reg.id: reg.name for reg in info.custom_user_stats}
    resolved: dict[int, list[tuple[int, str | None, str, int]]] = {}

    for player in info.players:
        rows: list[tuple[int, str | None, str, int]] = []

        for snap in player.stats:
            for stat in snap.custom_user_stats:
                name = id_to_name.get(stat.id)

                if name is None:
                    continue

                group, _, stat_name = name.partition("##")

                if stat_name:
                    rows.append((snap.time_stamp_s, group, stat_name, stat.value))
                else:
                    rows.append((snap.time_stamp_s, None, name, stat.value))

        resolved[player.account_id] = rows

    return resolved


def from_api_json(match_info: dict[str, Any]) -> MatchInfo:
    """Parse the API match_info json into the same MatchInfo the cache files yield.

    Verified identical, field for field, to what the cache files yield. Wire
    fields our .proto does not define yet are dropped, which the cache path
    cannot read either.
    """
    return json_format.ParseDict(match_info, MatchInfo(), ignore_unknown_fields=True)
