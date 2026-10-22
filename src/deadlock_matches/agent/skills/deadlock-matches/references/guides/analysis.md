---
status: active
scope: ad-hoc polars over the parquet tables, the caveats that bite most, how to present results, and where the data lives
first_seen: 2026-07-08
last_confirmed: 2026-10-02
---

# Analysis

Prefer `deadlock sync` plus polars over looping protobufs for win rates, damage totals, souls curves, and item timing. Run a quick `deadlock history` first. A data report checks the parquet schema before it reads and rebuilds a drifted store, so the tables are then fresh. `deadlock sync --full` forces a full rebuild.

For any count, rate, or total over your own matches, call `queries.summarize()` on a metric view. Do not join `players` to `matches` by hand, and do not write your own win rate. Drop to `scan()` only when the column you need is on none of the views.

```python
from deadlock_matches import queries

queries.summarize(
    queries.my_games, by="hero", measures=["games", "wins", "win_rate"]
).collect()
```

[Queries](../contracts/queries.md) is the full helper catalog. [Parquet tables](../contracts/tables.md) lists the tables, the layout on disk, and the read-time labels. `deadlock schema <table>` prints the columns and `deadlock schema --views` prints what `summarize` accepts.

## Caveats

The CLI commands and the `queries` helpers already apply every per-table caveat. Relaying their output or reusing a helper needs nothing more. Read the pattern page for a table in [the knowledge index](../index.md) before you hand-write raw polars against it. The four that bite most:

- `soul_sources`: the in-game number is `souls + souls_orbs`. Always sum both. See [Soul sources](../patterns/soul-sources.md)
- `damage` holds final totals and is safe to sum by source. `damage_sources` and `damage_targets` are cumulative snapshots, so a sum across `time_stamp_s` overcounts about 5 times. Filter `target_account_id.is_not_null()` for hero damage and never sum `category == "total"` rows with detail rows. See [Damage tables](../patterns/damage.md)
- `stats` holds per-sample snapshots. Take the last sample per `match_id` and `account_id`, not `max()`. Snapshot kills and deaths drift from the scoreboard, so use the `deaths` table for the real count. See [Stats snapshots](../patterns/stats.md)
- `damage_sources` and `soul_sources` samples are sparse and `damage_sources` is right-aligned. Never diff them by hand. Use the `*_intervals` helpers

## Ad-hoc rules

Keep it cheap. One exploratory session cost about 5 scripts and 3 avoidable errors before these rules existed.

- write one scratch script and iterate on it. Do not create a new file per step
- run `deadlock schema <table>` for exact column names before writing a join. The damage keys are `account_id` (the dealer) and `target_player_slot`, and there is no `dealer_slot`
- print compact aggregates (`group_by().agg()`), never per-game dumps. A 30-row table repr burns context and gets truncated. `pl.Config.set_tbl_width_chars(240)` up front avoids re-runs for hidden columns
- run scripts from the repo root with an absolute script path. A `cd` into the scratchpad breaks the `uv run` environment
- cast unsigned columns to signed (`.cast(pl.Int32)`) before a subtraction, because polars wraps around instead of going negative
- sort explicitly before printing or asserting on order. Row order after a join or a group_by is not stable

The protobuf modules stay the tool for per-match detail that the tables do not carry. See [Match metadata](../contracts/match-metadata.md).

## Presenting results

For per-day or per-interval summaries, render an aligned table with one row per period. Use columns like Day, Games, W, L, Win rate, Net, and Cumulative net. Right-align the numbers and sign the net columns (+3 / -1). Say which time zone groups the periods. End with a one-line overall summary ("26 games, 20-6, 76.9% win rate, +14 net"). Do not dump raw dataframe reprs at the user. `deadlock winrate` prints the weekly version of the table ready-made, and `--by day` prints daily rows. Relay its output instead of rebuilding the table.

## Where the data is

- the archive under `~/.local/share/deadlock-matches/matches/` is the only irreplaceable data. Cache-touching commands print an `archive:` line. Mention it when asked about backups
- a match is cached by viewing it in game (Escape, then Account in the top right, then click the game in match history). Playing alone does not cache it. If a recent match is missing, tell the user to open it in match history and rerun
- `extract.iter_matches()` snapshots the cache into the archive first and then iterates the archive. Prefer it over `iter_meta_files`
- other players' bodies land in the same archive through `players.match_info(match_id)`, and their tables live under the sibling `parquet-players/` directory

[Storage](../contracts/storage.md) lists every path. [Steam cache and API](../patterns/steam-cache.md) explains eviction, the Zstandard switch, and the API cache tiers.
