---
status: active
scope: the Steam httpcache, the local archive, and the deadlock-api client
first_seen: 2026-07-08
last_confirmed: 2026-08-10
---

# Steam cache and API

## Why this page exists

The Steam cache is the only place a new match appears, and its eviction and encoding have both changed. `extract.iter_matches`, `extract.archive`, `download_metadata`, and `api.get_json` apply the rules below.

## The encoding switched to Zstandard

First seen 2026-07-31.

Match entries live at `replay###.valve.net/1422450/<match_id>_<salt>.meta.bz2`. Despite the unchanged suffix, Valve switched new responses to Zstandard in July 2026. Detect the `BZh` or Zstandard magic, decompress accordingly, then parse `CMsgMatchMetaData`.

Recheck when a fresh entry fails to decompress.

## Eviction is LRU churn, not age

First seen 2026-07-08.

The cache only holds matches that this client downloaded. The httpcache caps at 10,000 entries shared with all Steam HTTP traffic. Entries carry max-age of one year, so nothing times out, and re-viewing a match refreshes its slot. A measurement on 2026-07-08 found that a days-old match that was never reopened was evicted while a months-old one survived.

A match is cached by viewing it in game (Escape, then Account in the top right, then click the game in match history). Playing alone does not cache it. If a recent match does not appear, tell the user to open it in match history and rerun.

Valve's replay servers still serve evicted `.meta.bz2` files months later, over plain HTTP only, and HTTPS fails.

## The archive is the only irreplaceable data

First seen 2026-07-08.

`extract.iter_matches()` snapshots everything into the archive first and then iterates the archive. Prefer it over `iter_meta_files`, which reads the live cache only. Cache-touching commands print an `archive:` line. Mention it when asked about backups.

## One body per match

First seen 2026-07-20.

The archive keeps one body per match. A match downloaded without salts lands as `<match_id>_0.bin`, and the next cache sync replaces it with the real-salt copy. `extract.archived_match_bodies()` maps match id to body path in a single directory scan. Use it, or `archived_match_ids()`, for any per-id loop. `match_path` and `has_match` glob the whole directory per call and are for single lookups only.

Bodies for other players download the same way. `players.match_info(match_id)` reads the archive `.bin` or downloads the raw `.meta.bz2` through `download_metadata` (salts, then the Valve replay server, then `metadata/raw`). Bodies always come from the raw `.meta.bz2`, never from the json metadata endpoint. Raw keeps unknown wire fields that the API json cannot carry. The raw body is how the removed party field was recovered.

## deadlock-api is ground truth for decode changes

First seen 2026-07-08.

`v1/matches/{id}/metadata` returns the identical `match_info` that the decoder produces, cross-checked field for field with zero diffs. `v1/matches/{id}/metadata/raw` backfills matches that Steam evicted before the archive caught them. `download_metadata` calls it. `v1/players/{id}/match-history` scoreboard fields equal the protobuf top-level player fields exactly, and win is `match_result == player_team`. Very recent matches lag there by hours, so the local cache is fresher.

## Two API cache tiers

First seen 2026-07-08.

Immutable bodies, such as per-build asset snapshots, persist gzipped under `~/.local/share/deadlock-matches/api`. Everything else (analytics, leaderboards, match histories) is cached under `~/.cache/deadlock-matches/api` with a one-day max age. Expired entries refetch and are still served when the network is down. `deadlock assets` always refetches.

Each flag combination on the analytics endpoints is its own URL, cached up to a day, so counts drift between fetches.

## Rate limits

First seen 2026-07-20.

A 429 from the API raises `api.RateLimited` carrying the Retry-After wait. Download paths sleep through waits up to 60 seconds and defer the remaining ids on a longer one. Sync prints the deferred count and a rerun continues where it stopped.
