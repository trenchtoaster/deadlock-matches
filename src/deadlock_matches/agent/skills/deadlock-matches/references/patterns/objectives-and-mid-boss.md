---
status: active
scope: the `objectives` and `mid_boss` tables
first_seen: 2026-07-08
last_confirmed: 2026-09-06
---

# Objectives and mid boss

## Why this page exists

Both tables look complete and both have fields that the metadata never fills. `queries.with_objective_labels` and the `deadlock match --teams` log apply the rules below.

## Objective lanes are empirical

First seen 2026-07-08.

`objectives` holds one row per team objective with `team`, `objective_id` (raw `ECitadelTeamObjective`), `destroyed_time_s` (null when it survived), `first_damage_time_s`, and the player and creep damage split. `queries.with_objective_labels` adds `objective` (Guardian, Walker, Base Guardians, Shrine, Patron, Weakened Patron) and `lane` as a color. The engine lane ids 1, 3, and 4 map to yellow, blue, and green. The mapping was derived empirically and verified three ways against attacker positions on 2026-07-07.

## Objective damage fields

First seen 2026-07-11.

`player_damage` is total hero damage, gun and spirit combined. `player_spirit_damage` is the spirit portion, a subset that never exceeds it, verified across the whole archive. Both are per objective and summed over all attackers. No per-player split exists in the metadata.

The proto fields `player_damage_mitigated` and `creep_damage_mitigated` are zero on every objective ever checked. They are dead fields, so do not hunt for them.

## Only one claiming team per boss kill

First seen 2026-07-08.

`mid_boss` holds one row per midboss (Rejuvenator) kill with `destroyed_time_s`, `team_killed`, and `team_claimed`. The two teams differ when the boss was stolen.

The in-game reward has been multi-part across patches. Mid-2025 dropped 3 crystals, and later patches dropped one crystal that grants 3 shared revive credits. The protobuf only ever records one claiming team per boss kill. A split pickup is not representable, so never present `team_claimed` as "got all the rejuvs". Claims per team is the only trustworthy Rejuvenator metric.

## Rift wins and urn runs come from treasure gains

First seen 2026-07-11.

No objective row records an Unstable Rift win or a Soul Urn delivery. `deadlock match --teams` reads a rift win from the flat team-wide treasure gain. It reads an urn delivery from the personal treasure gain, which names the runner.

## Revives consumed is not exported

First seen 2026-07-08.

Revives consumed, computed as `max(snapshot deaths) - scoreboard deaths` per player, is deliberately not exported. 7% of those ticks provably cannot be Rejuvenator revives, because some players have more ticks than own-team claims. Do not present the difference as a revive count.

## Objective rules changed on 2026-06-30

First seen 2026-07-11.

`deadlock match --teams` only decodes matches on the 2026-06-30 rework build (`RIFT_ERA_START` in `queries/objectives.py`). Older eras ran different objective rules.

Recheck when a patch reworks the objectives again.
