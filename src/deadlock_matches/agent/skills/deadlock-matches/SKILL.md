---
name: deadlock-matches
description: Decode and analyze Deadlock match metadata from the Steam httpcache (the .meta.bz2 protobufs uploaded to statlocker). Use to answer questions about the user's matches, item value, top-player builds, or farm/combat pacing, or to extend this repo's tooling.
---

# Deadlock match metadata

Reads match metadata from Steam's HTTP cache and compares the user's games against the players they track. Answer with the CLI first. Write Python only when no command answers it.

## Run the CLI

An installed tool puts `deadlock` on PATH (`command -v deadlock`). In a source clone, prefix `uv run` from the repo root. Run `deadlock <command> --help` for the flags.

- match ids and recent games: `deadlock history`
- one game: `deadlock match [ID] [--hero H]` with a view flag such as `--souls`, `--damage`, `--items`, or `--combat`
- win rates and trends: `deadlock winrate`. Never compute a win rate by hand
- Ranked points and rating: `deadlock rank`
- archive reports for one hero: `damage`, `healing`, `souls`, `combat`, `movement`, `deaths`, and `laning`
- the tracked players: `deadlock compare <souls|damage|healing|combat|movement> --hero H` and `builds`
- offline cards and public stats: `item`, `hero`, `ability`, and `meta`
- the tracked pool: `leaderboard`, then a paste into `config.toml`, then `download`
- refresh and inspect: `sync`, `assets`, and `schema`

[Commands](references/contracts/commands.md) holds the full table, the per-command rules, and the `match` view flags. Read it before an unfamiliar command.

A match is cached only when the user opens it in the in-game match history. When a recent match is missing, tell the user to open it there and rerun.

## Config

- "your games" means every account in `[accounts]` of `config.toml`. When the table is empty, run `deadlock accounts` and offer to fill it in
- `--hero` is always explicit. Take it from the question or from recent `history` output
- never hardcode or commit player names or ids. Read them through `config.config_players()`
- group by local day with `config.config_timezone()`, because `start_time` is UTC

[Config and accounts](references/guides/config.md) covers `--account`, the tracked players, and the comparison pool.

## Custom analysis

For a count, rate, or total over your matches, call `queries.summarize()` on a metric view. `deadlock schema --views` lists the views, and `deadlock schema <table>` lists the columns. The CLI and the helpers already apply the data traps. Read the pattern page in [the index](references/index.md) before you write raw polars against a table. The traps that bite most:

- the in-game soul figure is `souls + souls_orbs`
- `damage_sources` and `damage_targets` are cumulative, so a plain sum overcounts about 5 times
- take the last `stats` sample per match and account, not `max()`
- never diff sparse samples by hand; use the `*_intervals` helpers

[Analysis](references/guides/analysis.md) holds the scratch-script rules, the results table layout, and the data paths.

## Present results

Render an aligned table with one row per period, signed net columns, and the time zone named. End with one summary line. Relay `deadlock winrate` output instead of rebuilding it.

## Extend the code

Read [Module map](references/contracts/module-map.md) first, and keep [Queries](references/contracts/queries.md) current when you add a helper. Record a new verified trap as a dated entry on its pattern page in the same commit as the fix.
