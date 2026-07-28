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
- `players`: one row per player per match, with `hero_id`, `won`, and `assigned_lane`. `queries.player_rows()` adds the current hero display name as `hero` and the starting lane color as `lane`.
- `stats`: cumulative stat snapshots, every 3 minutes through 15:00 and every 5 minutes after, plus one at match end.
- `soul_sources`: souls per income source per snapshot. Parquet stores the `source` id; `queries.with_soul_source_name()` adds the readable slug.
- `item_events`: item purchases, with historical item names, prices, and tiers merged in from the cached API data. Prices reflect the patch each match was played on; the current imbued-ability name is derived from `imbued_ability_id` at read time.
- `buffs`: the buffs each player ended the match with, one row per pickup type. `queries.with_buff_labels()` adds the buff family and statue level from the class name. Permanent statue buffs and temporary bridge buffs are told apart by the `permanent` column. `statue_history` holds the per-pickup values by patch.
- `stacks`: the final counters from stacking abilities and items, one row per counter per player. Parquet stores `ability_id`; `queries.with_stack_labels()` adds its current class and display name.
- `custom_stats`: the named stat counters the game tracks but never shows, one row per stat per player per snapshot with the family and name split out. Examples include parries, accuracy against heroes, damage by range, comeback souls, and per-hero counters.
- `damage`: damage, healing, and mitigation per source and target. Parquet stores stable `source_class`; `queries.hero_damage()` and `queries.with_damage_source_name()` add current labels such as Dust Devil or "Promises Kept (crit)". `queries.damage_category()` distinguishes match-screen totals from individual sources.
- `damage_sources`: the same sources over time, cumulative like the in-game damage graph. Summed over targets, split into hero targets and everything else.
- `mid_boss`: one row per midboss kill, with when it died, which team killed it, and which team claimed the Rejuvenator.
- `movement`: the position of every player, health percent, and movement state (sliding, dashing, ziplining, in combat or not) for every second of the match. The starter config excludes it because it is larger than every other table combined. Delete it from `exclude` if you want exact position or nearby-player queries.
- `deaths`: one row per death with the time, position, killer, and respawn timer. Joined to `movement`, this answers things like "was I alone when I died" or "how many enemies killed me".

The tables do not cover everything Valve stores yet. The full structure is `CMsgMatchMetaDataContents` in [`protos/citadel_gcmessages_common.proto`](../protos/citadel_gcmessages_common.proto). This is a work in progress, and new columns and tables get added as more of that data turns out to be interesting to query.

`deadlock download --hero` builds the same tables for matches from other players in the `parquet-players/` directory: the players tracked under `[players.<Hero>]` in config, plus any account or match id you pass to `--account` / `--match`. Normal matchmaking is downloaded by default; `--street-brawl` and `--private-lobby` explicitly fetch those modes. The layout is identical, so query patterns work on their games too. An extra `downloads` table records which player each match came from, their rank at the time, and when it was retrieved. A match pulled by id has no player, so those columns are null.

The archive, player tables, and downloads ledger retain every fetched mode. Query views and comparison-pool readers apply `match_mode == Matchmaking` and `game_mode == Normal` by default at read time, so old Street Brawl or scrim rows remain inspectable without contaminating normal-matchmaking statistics.

## Query Patterns

Questions like these are a few lines of polars each:

- what is my win rate per hero?
- what is my accuracy? headshot rate? is it improving over time?
- when do I usually buy an item, and do I win more when I get it early?
- has my farm at 10 minutes improved recently?

`deadlock_matches.queries` gives you two ways in. Start from a metric view for any count, rate, or total. Drop to a frame when you want the rows themselves.

### Metric views

A metric view declares which dimensions you can group by and which measures you can aggregate, so `queries.summarize()` writes the join and the aggregation for you. `deadlock schema --views` lists every view with its arguments, dimensions, and measures.

- `my_games`: one row per normal-matchmaking match you played by default, with the local day for grouping by session. Pass mode arguments or use `queries.mode_context` for Street Brawl/Private Lobby.
- `record_games`: one row per match in the winrate window. Its wins count matches where `my_games` counts account-games. Its readable `match_mode` and `game_mode` dimensions back `deadlock winrate --by mode`; pass `None` for both mode filters to summarize every stored mode.
- `stat_snapshots`: the selected-mode `stats` table collapsed to each player-game's last sample before anything is summed. Normal matchmaking is the default when it selects games itself; an explicit `games=` frame is trusted as-is. That collapse is what stops cumulative snapshots from being added up by accident. Net worth, damage, accuracy, headshot rate, and the K/D/A counters.
- `hero_damage_games`, `damage_source_games`, `soul_source_games`, `movement_games`, `combat_games`, `buff_games`, `stack_games`: the views behind the damage, souls, movement, combat, and buff reports.
- `compare_intervals`, `cumulative_marks`, `milestone_games`: gains per interval, totals at a mark, and the minute a net worth was first reached.

### Frames

- `queries.scan("damage")` to read any table by name.
- `queries.player_rows()` to read `players` with the current hero display name.
- `queries.view_frame(queries.my_games())` for the rows behind a view instead of an aggregate.
- `queries.final_stats()` for the last stats snapshot of every player in every match. Opponents included.
- item and death helpers for the frames behind those CLI reports.

Every query in the module is a lazy polars plan and all collections use the streaming engine. Nothing is read until `.collect()`, the plan prunes the scan down to the columns and rows it actually touches, and memory stays bounded at any archive size. Keep your own queries lazy from `scan()` to `.collect()` and they get the same treatment.

Labels are deliberately not stored in match parquet. Hero, damage/healing source, imbued abilities, stack, and accolade labels resolve from their stable IDs or engine classes when queried, so an asset refresh fixes match displays without a full archive rebuild. The fixed mappings work the same way: soul source slugs, lane colors, objective names, and buff family/level all derive from the stored ids at read time, so a mapping fix is a code edit rather than a rebuild. Aggregate on the stable key first and attach the label to the reduced frame when writing a new aggregate query.

Here is the general shape. A rate like `win_rate` is total wins over total scored games at whatever grain you ask for. It is never the mean of per-day rates. Measures come back raw. A rate is a proportion and scaling it to a percent is yours to do where you print:

```python
import datetime as dt

import polars as pl

from deadlock_matches import queries

hero = "Mirage"
main = 111222333
since = dt.date(2026, 7, 1)

winrate_by_day = (
    queries.summarize(
        queries.my_games,
        by="day",
        measures=["games", "win_rate"],
        filters={"hero": hero},
        accounts=[main],
    )
    .filter(pl.col("day") >= since)
    .sort("day")
    .collect()
)
```

`filters` takes a value or a list of values per dimension, and a range is a `.filter()` on the result. For rows rather than an aggregate, `queries.view_frame(queries.my_games(accounts=[main]))` builds the frame itself.

For more examples, browse `notebooks/getting_started.py` in this repository.
