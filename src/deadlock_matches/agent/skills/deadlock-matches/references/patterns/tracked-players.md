---
status: active
scope: the `parquet-players/` store that `deadlock download` writes for other players
first_seen: 2026-07-08
last_confirmed: 2026-09-06
---

# Tracked players

## Why this page exists

Other players' games live in the same tables under a sibling directory, plus a `downloads` ledger. The ledger holds more than the comparison pool, and that difference is where a comparison goes wrong. `players.pool_members`, `pool_games`, `pool_builds`, and `tracked_player_games` apply the rules below.

## Same tables, sibling directory

First seen 2026-07-08.

`deadlock download --hero X` writes the same tables to the sibling `parquet-players/` directory. The API json is field-identical to the local decode, so every query pattern for your own tables applies unchanged. Read with `queries.scan(table, players.PLAYERS_PARQUET_DIR)`.

A re-run skips persisted match bodies but still hits the leaderboard and match-history endpoints and rebuilds every table.

## Check coverage before you download

First seen 2026-07-08.

Another session or agent may share these directories and may download at the same time. Check first:

```python
scan("downloads", players.PLAYERS_PARQUET_DIR).group_by("player").agg(
    pl.col("downloaded_at").max(), pl.col("match_id").max()
)
```

Join `matches` for the latest game date. Download only when the window you need is absent.

## The ledger

First seen 2026-07-11.

The `downloads` table records which player's history brought each match in, their rank and region at download time, and `downloaded_at`, which doubles as the patch era. A null rank means the player was never on the leaderboard at download. A later download refreshes only the rank, the region, and a missing name on the ledger rows through `ladder_positions`. The tables are a chosen sample, not the full history of those players. Check `downloaded_at` before comparing across patches.

The ledger holds more than the comparison pool. Old `--account` downloads and `--match` rows stay forever. The CLI comparisons read only accounts currently under `[players.<Hero>]` in `config.toml`. `players.pool_games` applies that filter. Reuse it instead of scanning the raw ledger when the question is about the pool.

`matches_by_id` rows carry a null account and hero, because no tracked player brought them in. `tracked_player_games(names, hero=, since=)` is the downloads to players to matches join by ledger name, case insensitive, with a local `day` column. It intentionally exposes every stored mode.

## Finding an off-ladder account id

First seen 2026-07-11.

A player who is not on the leaderboard still has an account id, which is the steam64 in the Steam profile URL minus `extract.STEAM64_BASE` (76561197960265728). A match you shared with the player already holds the exact id in the `players` table, so read it there when you can.

## The pool is ranked play by default

First seen 2026-07-27.

The pool readers enforce ranked play at read time by default, Standard before build 6652 and Ranked after it. Unranked, New Player Placement, Street Brawl, and scrim rows therefore cannot leak into a comparison. See [Ranked](ranked.md).

Nothing is ever downloaded from the leaderboard on its own. Every downloaded player was named by the user, in `[players.<Hero>]` or through `--account`. Deleting a config line removes the player from every comparison without touching data.
