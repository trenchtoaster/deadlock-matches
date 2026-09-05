---
status: active
scope: the `damage`, `damage_sources`, and `damage_targets` tables
first_seen: 2026-07-08
last_confirmed: 2026-08-10
---

# Damage tables

## Why this page exists

Three tables describe damage, and only one of them is safe to sum. Every overcount that an agent produced against these tables came from summing the wrong one. `damage_source_games`, `hero_damage_games`, `source_totals`, `source_intervals`, `enemy_damage_totals`, and `enemy_damage_intervals` apply the rules below.

## `damage` is the totals table

First seen 2026-07-18.

`damage` holds one row per dealer, source, and target with the final match-end totals and no time axis. A plain sum by source is safe. Reach for it for any "how much damage from X" number, never for `damage_sources`. `stat` names the figure (damage, healing, mitigated, and so on).

The `damage_source_games` view aggregates it per source, `hero_damage_games` per dealer and target, and `queries.source_totals` is the frame under them.

## Detail rows against total rows

First seen 2026-07-27.

`category` splits the screen-level `total` rows (exactly "Bullet", "Ability", "Melee", and "Misc") from the `gun`, `ability`, and `item` detail rows. Summing totals with details double-counts.

"UnknownAbility" looks like a total but is a real detail row. It is ability damage that the game never resolved to a source class, and its label is "Unknown ability". With it counted, detail sums match the total rows in every player-game but one.

`delivery` groups detail rows for gun-against-spirit questions. The values are `gun`, `gun_proc` (on-hit items like Mystic Shot, Headhunter, and Toxic Bullets, even when spirit typed), `ability`, and `spirit_proc`. Gun headshots are the `_crit` source, for example "Promises Kept (crit)". `with_delivery` resolves each item through the exported `item_history` era live at match start. A weapon-slot item is `gun_proc`, labeled "Items (bullet procs)", and anything else is `spirit_proc`, labeled "Items (standalone)". `BULLET_PROC_OVERRIDES` keeps Siphon Bullets as `gun_proc` because it sits in the vitality slot and procs on hit. Mercurial Magnum's on-cast proc is standalone but its until-next-reload bonus rides on bullets. The matrix reports both under one `upgrade_ethereal_bullets` line, so it is grouped by its primary mechanic.

`damage_category()` is a pure expression: `citadel_weapon*` is gun, `upgrade_*` is item, the `TOTAL_ROWS` names are total, and everything else is ability.

## Filter to hero targets

First seen 2026-07-08.

Always filter `target_account_id.is_not_null()` for hero damage. A null target is a non-player (creeps and objectives, raw slot 0). Without the filter, farm damage inflates every source. Creep headshots once made gun-crit look 9 times larger than body damage. Hero-only detail sums reconcile with snapshot `player_damage`.

On `damage_sources` the same split is the `vs_heroes` column.

## Healing rows

First seen 2026-07-08.

Healing rows (`stat == "healing"`) contain no base hero regen and no fountain regen. Verified: `player_healing` equals the source sum in every player-game checked. Item regen is included and credited to the item, for example Fortitude and Radiant or Mystic Regeneration.

A source in a player's block does not imply ownership. Spirit Shredder Bullets grants allies spirit lifesteal, so its class lands in non-owner blocks. Ivy's Kudzu tether splits credit between Ivy and each tethered player.

The healing report reconciles exactly with the scoreboard: `player_healing` with the source sum, `heal_prevented` with the prevented table, and the self against teammate split with `self_healing` and `teammate_healing` in `stats`.

## `damage_sources` is the timeline table

First seen 2026-07-08.

`damage_sources` holds the damage table's sources over time, cumulative per dealer, source, and stat sample, like the in-game damage graph. The `damage` column is a running total. Summing a source across its `time_stamp_s` rows multiplies by the sample count. The overcount is about 5 times. It was seen 2026-07-18.

For a total, take the last sample per source, use the `damage` table, or summarize the `damage_source_games` view. For a timeline, use `queries.source_intervals` or `damage_intervals`. They diff the table into the view behind `deadlock match --damage` and reproduce the in-game tooltip exactly.

The table is summed over targets with a `vs_heroes` split instead of per-target rows. It has the same `category` and `delivery` columns, so keep the total-against-detail filter. Samples are sparse, about 3 minutes apart plus match end. The protobuf arrays are right-aligned to `sample_time_s`, and the export already handles the alignment. The final sample equals the `damage` table value.

Never sum cumulative `damage_sources` across sources per timestamp yourself. Each source samples at its own times, so the sum sawtooths and undercounts. The attempt on 2026-07-08 read about 55% low.

## `damage_targets` has the same trap

First seen 2026-07-18.

`damage_targets` is per enemy over time. Hand-summing it across `time_stamp_s` multiplies by the sample count, the same overcount of about 5 times. Use `enemy_damage_totals` for totals and `enemy_damage_intervals` for timelines only.

## Rate families on `damage_source_games`

First seen 2026-07-15.

Two families of rate sit on the view and they divide by different things. `per_game`, `per_min`, `per_1k`, and `per_min_owned` divide by the games, minutes, souls, or owned minutes of the group. `per_window_game`, `per_window_min`, and `share` divide by every game of the hero that the view covers. That denominator is why heal-prevented per game counts the games that prevented nothing.

`per_min` on `damage_by_source` divides a row by the combined minutes of the games where that source appeared, not all scoped minutes. The change landed 2026-07-15 so that a rare item reads as its real rate. Item rows carry a zero-amount row in a game where the item was owned and dealt nothing, so `per_1k` divides by every soul spent. `games` and `minutes` read those rows out.

## Exact per-item and per-ability damage

First seen 2026-07-08.

The exact per-item and per-ability damage lives in `match_info.damage_matrix`. `damage.damage_from_source()` reproduces the in-game post-match number. The damage keys are `account_id` for the dealer and `target_player_slot`. There is no `dealer_slot`.
