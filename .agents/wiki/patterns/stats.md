---
status: active
scope: the `stats` table of per-sample snapshots
first_seen: 2026-07-08
last_confirmed: 2026-09-06
---

# Stats snapshots

## Why this page exists

`stats` holds one row per player per sample, not one row per player. Every entry below is a way the snapshots disagree with the scoreboard, and every one has a helper that already handles it. `stat_snapshots` and `queries.final_stats()` apply the last-sample collapse.

## Take the last sample, never `max()`

First seen 2026-07-25.

Collapse each match and player to the last sample by `time_stamp_s`. Most columns only climb, so `max()` and `last()` agree on them. `net_worth`, `max_health`, `weapon_power`, and `tech_power` fall after a death loss or a sold item, so their peak is not their final value.

On 2026-07-26, `players.net_worth` matched `last()` on 61 of the 62 disagreeing player-games and matched `max()` on none.

Every measure on `stat_snapshots` carries a semiadditive window, so the view collapses each player-game before anything is summed.

## The sample clock

First seen 2026-07-11.

Sample times are exact and identical in every archived match. Samples land every 3 minutes through 15:00 (180, 360, ..., 900) and every 5 minutes from 20:00 on (1200, 1500, ...). One final off-grid sample lands at match end. `soul_sources` and `custom_stats` ride the same clock. `damage_sources` does not, because it has its own per-source clock of about 3 minutes with no late-game switch.

The two grids share 900, so 5-minute intervals align exactly from 15:00 on. Before that, gains land in the interval that holds the recording sample. The printed 0-5, 5-10, and 10-15 rows really cover 0-3, 3-9, and 9-15. An interval finer than the local cadence forward-fills, so it prints zero-gain rows and then a lump.

Snapshot timestamps skew a few seconds early against event times. A death at t=182 lands in the t=180 snapshot. Use a tolerance of about 10 seconds when bucketing events into snapshot windows.

Recheck when a patch changes the snapshot cadence.

## Lane result at the mark

First seen 2026-07-08.

The lane net at a mark reads off the stats snapshots. It sums both duos and subtracts the enemy side from the player's side. A net above 0 is a won lane. The default mark is 9 minutes, which sits on the 3-minute cadence. A mark off the cadence reads the last snapshot inside it.

`deadlock laning` buckets the player's own deaths in the window at 0, 1, 2-3, and 4 or more. It calls an ally fed at 4 or more deaths. Games with an ally abandon leave the teammate tables, because a leaver feeds by definition.

## Snapshot kills drift from the scoreboard

First seen 2026-07-27.

Snapshot `kills` drifts from the scoreboard in roughly a third of player-games, by 1 to 4 either way. The cause is the Rejuvenator mechanic. Killing a player who holds a Rejuvenator credit is not an official kill. The HUD shows no kill and the killer gets no souls, but the engine still fires the hero-kill event. The engine event is why on-kill effects still trigger. Examples are Shiv's Killing Blow reset, the Grey Talon, Mo & Krill, and Vindicta ultimate stacks, and Drifter's Bloodscent. The live snapshot counters ride the engine event while the scoreboard counts only official kills.

Nothing is reversed, so the drift lands on opposite teams. Measured across single-claim matches, the revived side carries the death drift (44.2% of player-games, mean +0.51, against 8.2% for the other team). The killing side carries the kill drift (31.1% over, mean +0.31, against -0.11). Matches with no mid boss kill barely drift at any length (2.5% to 5.6%).

Counting `deaths` rows by `killer_account_id` matches the scoreboard on 10,313 of 10,332 player-games, so that is the kill source that `match_intervals` uses. The drift is not a post-victory artifact. The final sample lands exactly at match end in 14,760 of 14,760 player-games, so nothing scores after it.

One residual is open, in that the claiming team also runs slightly under on kills (13.1%, mean -0.11). Three explanations are ruled out. It is not post-victory scoring, and it is not a winner effect, because claiming and lost reads -0.02 while non-claiming and won reads +0.35, so it tracks the claim and not the result. It is also not the revive rolling back the revived player's own counters, because revived and non-revived claiming-team players under-count identically (-0.105 against -0.119). The effect is team level and tracks the Rejuvenator claim, and its cause is unknown.

Recheck when a patch changes the Rejuvenator revive rules.

## Snapshot deaths count self-revives

First seen 2026-07-08.

Snapshot `deaths` also counts Rejuvenator self-revives, which the scoreboard leaves out. The overcount is 1 to 3 in about 26% of player-games. 93% of the extra ticks follow an own-team Rejuvenator claim, carry no `gold_death_loss`, and have no `death_details` entry. The `deaths` table, exported from `player.death_details`, matches the scoreboard exactly. Use it for the real count.

## Net worth trails the scoreboard

First seen 2026-07-27.

Snapshot `net_worth` trails the scoreboard on 22.8% of player-games. It is always low and nearly always trivially so. The median gap is -11 souls, or 0.025% of net worth. 303 player-games pass 100 souls, 6 pass 1,000, and the maximum is 2,457. The cause is not an early last snapshot, because the final sample lands exactly at match end in 14,760 of 14,760 player-games. The gap is income that settles in the final instant. Take `players.net_worth` for a final figure.

## Creep kills are lane creeps only

First seen 2026-07-08.

Snapshot `creep_kills` counts lane creeps only. The scoreboard `last_hits` counts creeps, neutrals, and more. Never compare snapshot `creep_kills` to a last-hits figure. The top-level `player.last_hits` is the real one.

## Renamed and derived columns

First seen 2026-07-08.

The protobuf `gold_*` fields are exported as `souls_*`. Accuracy is `shots_hit / (shots_hit + shots_missed)`. Headshot rate is `hero_bullets_hit_crit / (hero_bullets_hit + hero_bullets_hit_crit)`.

Polars keeps Boolean and unsigned dtypes through aggregation, so a subtraction wraps around instead of going negative. Cast to signed with `.cast(pl.Int32)` first.
