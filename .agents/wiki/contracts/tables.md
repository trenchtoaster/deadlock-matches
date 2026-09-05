---
status: active
scope: the parquet tables, their layout on disk, and the rules the exporter and the readers follow
first_seen: 2026-07-08
last_confirmed: 2026-08-10
---

# Parquet tables

## The tables

`matches`, `players`, `stats`, `soul_sources`, `item_events`, `accolades`, `buffs`, `stacks`, `custom_stats`, `damage`, `damage_sources`, `damage_targets`, `objectives`, `mid_boss`, `movement`, `movement_intervals`, `deaths`, and `hero_xp_rewards`. `deadlock schema <table>` prints the columns of any of them. `deadlock schema --views` prints the metric views that `summarize` accepts.

The committed asset history exports as `item_history`, `item_component_history`, the `hero_*_history` and `ability_*_history` tables, `rank_history`, and `statue_history`. The tracked-player store adds the `downloads` ledger. `schemas.TABLES` is the authoritative list.

Every table carries `start_time` in UTC, and the player-grain tables carry `hero_id`. Time or hero scoping on a raw scan therefore needs no join to `matches` or `players`. Scans also expose a hive `month` column ("YYYY-MM"). A filter on `month` or `start_time` reads only the matching month files.

Other players' games are the same tables under the sibling `parquet-players/` directory. Read them with `queries.scan(table, players.PLAYERS_PARQUET_DIR)`. See [Tracked players](../patterns/tracked-players.md).

## Layout on disk

Tables live in `~/.local/share/deadlock-matches/parquet/`, one `month=YYYY-MM/data.parquet` per table and month in the hive layout. `--archive` and `--parquet` point any command at non-default directories.

## Labels are read-time fields

Labels are not parquet columns. `players.hero` comes from `hero_id`. Damage `source_name` comes from `source_class`. `item_events.imbued_ability` comes from `imbued_ability_id`. The stack class and name come from `ability_id`, and the accolade stat name from `accolade_id`. The fixed mappings resolve the same way: soul `source_name` from `source`, `players.lane` from `assigned_lane`, objective `objective` and `lane` from `objective_id`, and buff `buff` and `level` from `type`.

Use the label helpers in [Queries](queries.md) rather than joining or persisting these yourself. Aggregate damage on `source_class` first, then attach `source_name` to the reduced result. The historical item `item`, cost, tier, and slot stay materialized on purpose.

## The exporter is faithful, the queries judge

`export.py` builds the tables from a faithful decode only. Judgment lives in the `queries` package. Queries never manufacture a missing column. An old protobuf becomes real nulls only when the exporter rebuilds it.

## Schema drift and rebuilds

Data reports check the physical parquet schema before reading and rebuild a drifted store even when Steam yielded no new cache entry. A quick `deadlock history` first therefore guarantees fresh tables. `deadlock sync --full` forces a full rebuild.

A schema change needs no manual step. `export.schema_drift` compares every month file against `schemas.py` in both stores. It reads footers only. A change that only removes columns reshapes the parquet files in place. A missing table or a newly required column triggers the full archive rebuild automatically. The rebuild prints archive progress every 50 files and ends with one "Rebuilt all tables" line.

Never hand-patch a drifted month file. Reshapes replace each file atomically, and rebuilds stream bounded batches of matches, so both stay recoverable and memory bounded at any archive size. The tracked-player store redownloads bodies that the archive lacks.

A report rebuild preserves the account filter recorded by the existing main export when config has no `[accounts]` table. It never broadens the store to every archived match. A `downloads.parquet` ledger identifies a tracked-player store even at a custom `--parquet` path, so it uses the tracked rebuild path. An explicit `deadlock sync` still filters to the config accounts. It refuses to run without an `[accounts]` table and refuses an `--account` id that is not in it.

## Engine and ordering

Importing the package pins the polars engine affinity to streaming in `engine.py`, so every collect stays memory bounded on the big tables.

Do not rely on output row order after a join or a group_by. Sort explicitly before printing or asserting on order. Use `maintain_order=True` only when the query needs the original group order. Inside an aggregation, make order-dependent intent explicit. When `first()` means "earliest", sort after any join that can disturb order, or use a `sort_by(...)` or min-key expression inside the group. Float sums can also differ in the last bits between runs.

## Time zones

`config.config_timezone()` gives the zone for grouping matches into local days. The starter config pins the detected zone at creation. Always `convert_time_zone()` with it before `.dt.date()`. `start_time` is UTC, so a late-night session splits across days otherwise.
