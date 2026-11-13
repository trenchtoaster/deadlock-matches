---
status: active
scope: the `soul_sources` table of income per source per snapshot
first_seen: 2026-07-08
last_confirmed: 2026-09-06
---

# Soul sources

## Why this page exists

`soul_sources` holds one row per income source per snapshot. The parquet stores the `source` id, and `queries.with_soul_source_name` adds `source_name` (troopers, jungle, breakables, and so on). The `soul_source_games` view and the `queries` soul helpers already apply every rule below. The rules matter for ad-hoc polars.

## The in-game number is `souls + souls_orbs`

First seen 2026-07-08.

Always sum both columns. `souls` is the guaranteed portion. `souls_orbs` is the deniable flying-orb portion that the player secured. They are two different quantities, so do not conflate them.

The design ratio is the share of a trooper bounty placed in the orb. It was 40% before the 2026-06-30 patch and 50% after it, per the patch notes. The secured share, `souls_orbs / (souls + souls_orbs)`, is lower because orbs get denied or missed. Measured medians run about 27% before the patch and 30% after, and individual matches swing past 40%.

Never pin a fixed figure. The sum-both rule is invariant, while the magnitude drifts by patch and by how well the player confirms orbs.

Recheck when a patch changes the orb share in the notes.

## Gross souls against net worth

First seen 2026-07-08.

The Total that the soul views print is gross souls earned. Net worth adds the starting souls and subtracts what each death cost. The two figures never match, so name which one a report shows.

A per-source `/game` row divides by the games that recorded that source, not by every game in the window. A rare source therefore reads as its real rate.

## Denies are team-shared income

First seen 2026-07-11.

Source 7, screen label "Denies", is team-shared income. Every teammate gets about 9 to 10 souls per denied orb, and the source hits zero only when the whole team never denies. A check across the archive found that the flat `souls_denied` equals it exactly and its `souls_orbs` is always 0.

A player with 0 scoreboard denies still earns these souls. Never read source 7 as personal denying. The scoreboard `denies` column is the personal count.

## Same clock as `stats`

First seen 2026-07-11.

`soul_sources` samples ride the `stats` snapshot clock. See [Stats snapshots](stats.md) for the cadence and the interval alignment. Soul composites forward-fill each source on its own clock inside `compare_intervals`.

## Source ids follow the protobuf enum

First seen 2026-07-08.

Soul source ids follow the protobuf `EGoldSource` enum through `queries.GoldSource`, tested against it. A mapping fix or a new Valve value is a code edit, never a rebuild.

`Comeback Gold Koth` in `custom_stats` is the only metadata trace of the Unstable Rift. See [Custom stats](custom-stats.md).
