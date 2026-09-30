---
status: active
scope: the `custom_stats` table, the named counter pool behind `--combat`
first_seen: 2026-07-11
last_confirmed: 2026-10-01
---

# Custom stats

## Why this page exists

`custom_user_stats` on the wire is a pool of named counters whose ids change per match. The `combat_games` view pivots the fight counters out of it per game, and `queries.custom_stats` collapses to final values by default, with `final=False` for the snapshot rows. Both apply the rules below.

## Shape

First seen 2026-07-11.

The table holds one row per stat per player per snapshot, cumulative like the `stats` table. Absent means zero, because the game only emits nonzero counters.

Wire stat ids are registered per match. The same name lands at different ids in different matches, and the hero and mode mix changes which ids exist. The export resolves ids through each match's own registry in `extract.custom_stats`, so the table only carries names. Never aggregate raw protobuf custom stats by id.

Names namespace as `Group##Stat`, split into the `group` and `stat` columns. A bare name like `Parry Success` keeps a null group. New groups appear as Valve adds them. Per-hero counters like `Celeste##RadiantDaggerTimeAt_N_stacks` are uptime seconds per stack count. Consumers must stay name agnostic. The pool held 73 names as of 2026-07.

Recheck when the archive shows a group name that no consumer knows.

## The `Bullet Stats` percents are not counters

First seen 2026-07-11.

Every family is a cumulative count except the `Bullet Stats` groups. The `Bullet Stats` values are percents recomputed per snapshot and non-monotonic on the wire. Never diff them. Recompute a windowed rate from the `Enemy Hero Accuracy` counts instead.

## Parry counts include Counterspell

First seen 2026-07-11.

`Parry Success` counts more than melee duels. Counterspell upgrades parry into a 0.8 second spell parry, and every ability or item hit that it blocks increments the counter. Owners average 13.0, 21% of owner games clear 20, and the maximum is 335. Non-owners reach at most 22 in 9,462 player-games. Any value past about 22 is a Counterspell game. Rebuttal only makes real parries more frequent through parry cooldown reduction. Join `item_events` before reading a big number, and exclude Counterspell and Rebuttal games to read manual parries.

## Range bands

First seen 2026-07-11.

The `* Dist` groups are damage by range band in meters, with buckets at 10, 20, 30, 40, 50, 75, 100, and Infinite. Melee and item damage carry no range family, so the outgoing buckets sum to slightly under snapshot `player_damage`.

## Comeback souls

First seen 2026-07-11.

`Comeback Gold Koth` is the only metadata trace of the Unstable Rift. It is a flat amount to each player on one team per rift. `Comeback Gold Urn` died with the 2026-06-30 patch that rethemed KOTH.

## Unspent balances

First seen 2026-07-11.

`Unspent Gold Minutes` and `Unspent AP Minutes` are balance-times-minutes integrals. Divide by match minutes for the average unspent balance.

## Pickup counters

First seen 2026-07-11.

`PowerUp Gold`, `PowerUp Permanent`, and `PowerUp Temp` are pickup counters for own pickups only. `power_up_buffs` also includes teammates' shared permanent buffs. Buff questions belong to the `buffs` table, aggregated by the `buff_games` view, and to `match --buffs`. `stack_games` does the same for `stacks`. `--combat` skips these counters.

## Incoming fire has no per-enemy split

First seen 2026-07-11.

The incoming counters cover the whole enemy team combined. No per-enemy split exists on the wire, so never present incoming fire as one enemy's aim.

## Where the permanent buffs came from

First seen 2026-07-11.

The buff source split reads three places. Statues come from the `PowerUp` custom stats, a sinner jackpot counts 4 from accolade 14, and a mid boss kill counts 2 team-wide. The rest is urn runs and light melee jackpots. `buff_games` and `buffs.count` have no time axis. For timing, read `buff_pickups` or `buff_intervals`, below.

## Statue pickup times

First seen 2026-10-01.

Client build 6712 added `PowerUpBuff.pickup_times_s` and `pickup_stat_values`. Match 108628471 on 2026-09-29 is the first archived body that carries them. None of the 1855 older bodies do.

The `buff_pickups` table holds one row per permanent statue pickup. `pickup` is the 0-based order within the type, because two pickups can share a second. `value` is the stat granted, in the statue catalog unit: percent, flat health, or move speed in engine units. The identity is match_id, account_id, type, and pickup.

Rows exist only from build 6712 on. Older matches and the timed bridge buffs have none, so `buffs.count` stays the authoritative total. On the archive checked 2026-10-01, the list length equals `buffs.count` on 830 of 830 permanent buff rows. All 56 bridge buff rows have empty lists. The recorded values equal the statue catalog value for the era.

`queries.buff_intervals` splits one player's pickups per interval and buff family. An empty frame means the match records no pickup times, not zero pickups. `deadlock match --buffs` sums the recorded values into Gained and falls back to the statue history era for older matches. A buff type with any pickup missing its recorded stat falls back to the statue history too.

Recheck when a match body carries pickup times on a bridge buff.

## All-target accuracy

First seen 2026-07-11.

The wire has no trooper, neutral, or objective split for accuracy, only heroes against everything else. Non-hero targets get hit at about a 92% median, so the familiar all-target accuracy reads much higher than the against-hero rate. The `--combat` view prints both so the against-hero rate never reads as a bug.
