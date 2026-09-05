---
status: active
scope: the `movement`, `movement_intervals`, and `deaths` tables
first_seen: 2026-07-08
last_confirmed: 2026-09-06
---

# Movement and deaths

## Why this page exists

`movement` is the one table a user can turn off, and its alignment differs from the damage matrix. `deaths` is the death record that matches the scoreboard. `queries.movement_intervals`, `movement_profile`, `movement_games`, `my_deaths`, and `death_context` apply the rules below.

## `movement` is opt-out

First seen 2026-07-08.

The config exclude list turns `movement` off, and the starter config excludes it. The table is about 330 KB and about 26,000 rows per match, and it was about 85% of export time before vectorization. When `movement.parquet` does not exist, `queries.table_exists("movement")` is False and `deadlock deaths` drops its context columns instead of failing. Check `table_exists` before `death_context`.

## The track and its alignment

First seen 2026-07-08.

Every player's per-second track comes from `match_info.match_paths`. `x` and `y` are world units. `health_percent` runs 0 to 100 and is 0 while dead. `combat_type` is out, player, enemy_npc, or neutral. `move_type` is normal, ability, ability_debuff, ground_dash, slide, rope_climbing, ziplining, in_air, or air_dash.

The track is left-aligned, unlike the damage matrix. The sample index is the game second. Verified against death positions: the median error is about 209 units at offset 0 and about 8,000 one second off. Trailing samples past `duration_s` are end-screen noise and are dropped at export.

Positions are quantized to a per-player 14-bit bounding box, so there is about 200 units of jitter, and there is no z. Velocity is the distance between consecutive seconds. Clamp respawn and zipline teleport spikes before averaging.

Weapon and world distances are game units (inches). Divide by 39.37, which is `queries.movement.UNITS_PER_METER`, for the meters the game shows.

## Movement varies by hero

First seen 2026-07-08.

Movement-tech profiles (slide percent, dashes per minute, air dashes per minute) vary strongly by hero. Normalize per hero, or compare within a hero, before comparing players.

## `movement_intervals` is always built

First seen 2026-07-11.

`movement_intervals` is built even when `movement` is excluded. It holds one row per player per minute of counts from alive seconds. The counts are `alive_s`, `moving_s`, `stationary_s` (steps under 40 units), `slide_s`, `in_air_s`, `zipline_s`, and `combat_s` (fighting players). `dashes` and `air_dashes` count transitions into the state. `distance` is in world units and skips zipline seconds and teleport-sized jumps. It is about 60 times smaller than `movement`.

The rows are counts, not percents, so any bucketing that is a whole number of minutes sums exactly. Steps and transitions are computed on the whole 1 Hz sequence before the minute grouping, so sums reproduce whole-match numbers exactly. The `movement_games` view aggregates the rows per game, and `queries.movement_intervals` and `queries.movement_profile` derive the percents. The slide, air, zipline, and fighting percents divide by alive seconds, while the stationary percent divides by moving seconds.

## `deaths` matches the scoreboard

First seen 2026-07-08.

`deaths` holds one row per death from `player.death_details`: `game_time_s`, `time_to_kill_s`, `death_duration_s` (the respawn timer), `killer_account_id` (null for a non-player), and the death and killer `x`, `y`, and `z`. It is the death record that matches the scoreboard. Snapshot `deaths` overcounts, see [Stats snapshots](stats.md).

Join to `movement` at `game_time_s` to count allies and enemies within a radius at the moment of death. About 2,000 units is in the fight. Enemies with `combat_type == "player"` in the preceding seconds were participants, not bystanders.
