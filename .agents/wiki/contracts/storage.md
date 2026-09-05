---
status: active
scope: where the config, the archive, the parquet stores, and the API caches live
first_seen: 2026-07-08
last_confirmed: 2026-08-10
---

# Storage

## User config

`config.toml` lives in the user config directory: `~/.config/deadlock-matches/` on Linux and `%APPDATA%\deadlock-matches\` on Windows. `deadlock config` prints the path. Every CLI run writes a commented starter config when the file does not exist (`config.ensure_config`). The starter excludes the movement table (`exclude = ["movement"]`) and pins the detected time zone.

The `[accounts]` table holds `name = <steam32 id>` pairs. It is the only accepted shape, and a plain list exits with the expected form. The `[players.<Hero>]` tables hold the tracked players per hero. The config lives outside the repository on purpose. Never hardcode or commit player names or ids.

## Data and cache directories

Data and cache directories come from `paths.py`: `~/.local/share` and `~/.cache` on Linux, or `%LOCALAPPDATA%` on Windows.

| Path | Holds |
| --- | --- |
| `~/.local/share/deadlock-matches/matches/` | the archive of raw match bodies, the only irreplaceable data |
| `~/.local/share/deadlock-matches/parquet/` | your own tables |
| `~/.local/share/deadlock-matches/parquet-players/` | the tracked-player tables and the `downloads` ledger |
| `~/.local/share/deadlock-matches/api` | immutable API bodies, gzipped, such as per-build asset snapshots |
| `~/.cache/deadlock-matches/api` | analytics, leaderboards, and match histories, one-day max age |

## The Steam cache

`extract.default_cache()` finds Steam's cache. On Linux it checks the native `~/.steam`, `~/.local/share/Steam`, and the flatpak location. On Windows it reads the registry `SteamPath` or the default install. See [Steam cache and API](../patterns/steam-cache.md) for how entries appear and disappear.

## Local Steam accounts

`deadlock accounts` lists the Steam accounts on this PC that ran Deadlock. The `userdata/` folder names are Steam32 ids. The account and profile names come from `loginusers.vdf`. The archived game count comes with the first and last game day. It prints a paste-ready `[accounts]` block with neutral main and altN names. `extract.steam_accounts()` is the underlying reader.

The suggested names are deliberately not the Steam account names. The Steam account names are half of the login credentials, and config names print in report headers. In the output, "Account name" is the private login and "Profile name" is the public persona, which are Steam's own terms.
