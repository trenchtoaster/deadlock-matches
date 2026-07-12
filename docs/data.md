# Data Reference

This repo stores decoded Deadlock match metadata as parquet tables. The installed CLI includes the live data dictionary:

```bash
deadlock schema
deadlock schema players
deadlock schema players --sample
deadlock schema players --sample 10
```

Use `deadlock schema [table]` when you want the exact columns, data types, and descriptions for the version you have installed. Use `--sample` when you want to see real local rows before writing a query.

## Tables

- `matches`: one row per match.
- `players`: one row per player per match, with `hero`, `won`, and `lane` (the starting lane color).
- `stats`: cumulative stat snapshots, every 3 minutes through 15:00 and every 5 minutes after, plus one at match end.
- `soul_sources`: souls per income source per snapshot.
- `item_events`: item purchases, with names, prices, and tiers merged in from the cached API data. Prices reflect the patch each match was played on.
- `buffs`: the buffs each player ended the match with, one row per pickup type with the buff family and level. Permanent statue buffs and temporary bridge buffs are told apart by the `permanent` column. `statue_history` holds the per-pickup values by patch.
- `stacks`: the final counters from stacking abilities and items, one row per counter per player, with the class and display name resolved from the id.
- `custom_stats`: the named stat counters the game tracks but never shows, one row per stat per player per snapshot with the family and name split out. Examples include parries, accuracy against heroes, damage by range, comeback souls, and per-hero counters.
- `damage`: damage, healing, and mitigation per source and target, with the names you see in game like Dust Devil or "Promises Kept (crit)" for headshots. The totals from the match screen and the individual source rows have different `category` values, so filter to one or the other.
- `damage_sources`: the same sources over time, cumulative like the in-game damage graph. Summed over targets, split into hero targets and everything else.
- `mid_boss`: one row per midboss kill, with when it died, which team killed it, and which team claimed the Rejuvenator.
- `movement`: the position of every player, health percent, and movement state (sliding, dashing, ziplining, in combat or not) for every second of the match. The starter config excludes it because it is larger than every other table combined. Delete it from `exclude` if you want exact position or nearby-player queries.
- `deaths`: one row per death with the time, position, killer, and respawn timer. Joined to `movement`, this answers things like "was I alone when I died" or "how many enemies killed me".

The tables do not cover everything Valve stores yet. The full structure is `CMsgMatchMetaDataContents` in [`protos/citadel_gcmessages_common.proto`](../protos/citadel_gcmessages_common.proto). This is a work in progress, and new columns and tables get added as more of that data turns out to be interesting to query.

`deadlock download --hero` builds the same tables for matches from other players in the `parquet-players/` directory: the players tracked under `[players.<Hero>]` in config, plus any account or match id you pass to `--account` / `--match`. The layout is identical, so query patterns work on their games too. An extra `downloads` table records which player each match came from, their rank at the time, and when it was retrieved. A match pulled by id has no player, so those columns are null.

## Query Patterns

Questions like these are a few lines of polars each:

- what is my win rate per hero?
- what is my accuracy? headshot rate? is it improving over time?
- when do I usually buy an item, and do I win more when I get it early?
- has my farm at 10 minutes improved recently?

`deadlock_matches.queries` handles common joins and filters, so a query is mostly the aggregation. The helpers are ordinary Python functions, so inspect the module or use editor autocomplete for the current list. Stable starting points include:

- `queries.scan("damage")` to read any table by name.
- `queries.my_games()` for one row per match you played, with the local day for grouping by session.
- `queries.final_stats()` for final stats of every player in every match, including accuracy and headshot rate.
- item, damage, soul, death, movement, and record helpers for the frames behind CLI reports.

Every query in the module is a lazy polars plan and all collections use the streaming engine. Nothing is read until `.collect()`, the plan prunes the scan down to the columns and rows it actually touches, and memory stays bounded at any archive size. Keep your own queries lazy from `scan()` to `.collect()` and they get the same treatment.

Here is the general shape. Start from one of the helper frames, filter to the games you care about, then aggregate:

```python
import datetime as dt

import polars as pl

from deadlock_matches import queries

hero = "Mirage"
main = 111222333
since = dt.date(2026, 7, 1)

winrate_by_day = (
    queries.my_games(accounts=[main])
    .filter(pl.col("hero") == hero, pl.col("day") >= since)
    .group_by("day")
    .agg(
        pl.len().alias("games"),
        pl.col("won").mean().mul(100).round(1).alias("winrate"),
    )
    .sort("day")
    .collect()
)
```

For more examples, browse `notebooks/getting_started.py` in this repository. The notebook is a source-checkout reference, not something installed by the CLI.
