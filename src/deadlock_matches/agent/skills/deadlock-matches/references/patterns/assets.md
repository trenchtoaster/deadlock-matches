---
status: active
scope: the assets API data (heroes, items, abilities) and what it does not contain
first_seen: 2026-07-08
last_confirmed: 2026-08-10
---

# Assets

## Why this page exists

The assets API answers most tuning questions, and a handful of in-game numbers exist nowhere in it. Several formulas below were measured in the sandbox against live damage. `deadlock hero`, `deadlock ability`, and the `Hero`, `Item`, and `Ability` helpers apply them.

## Read the description, not the name

First seen 2026-07-08.

`Item.description` is the cleaned tooltip and says what an item actually does. `Hero.stats` has base stats. Use both instead of guessing from names.

`Item.properties` has the actual stat grants, for example `{tech_power: 18, bonus_health: 75}`. Negatives are real tradeoffs, like Glass Cannon's -13% health. `Hero.scaling_stats` is the spirit scaling of base stats for 12 heroes, for example Vindicta bullet damage +0.022 per spirit.

## Weapon records

First seen 2026-07-08.

Weapon records in `abilities.json` carry `weapon` gun stats: `bullet_damage`, `clip_size`, falloff and crit ranges, and dps. Weapon distances are game units (inches). Divide by 39.37 (`queries.movement.UNITS_PER_METER`) for the meters the game shows. Promises Kept falloff 787 to 2264 units equals the in-game card's 20 m to 58 m. The card verified the conversion. Ability `properties` distances are already meters.

## Vyper's crit scale is missing

First seen 2026-07-08.

Vyper's in-game "Crit Bonus Scale: -30%" exists nowhere in the assets API. The gun record says the standard 1.65 crit bonus, and no -30 or 0.7 field exists in any Vyper record. Checked 2026-07-07. Do not hunt for it. Do not confuse it with `crit_damage_received_scale`, which scales the crits a hero receives: Seven 0.45, Mo & Krill 0.8, Rem 0.9.

Recheck when the assets API adds a per-hero crit field.

## Ability tuning and tier math

First seen 2026-07-08.

Ability tuning numbers sit on `Ability`. `properties` holds base values, with unit strings like "20m" already parsed to numbers. `scaling` says which stat a property scales with and by how much. `upgrades` holds the per-tier bonus entries, and `type: add_to_scale` changes the scaling, not the base. `stat(name, tier)` and `spirit_scale(name, tier)` do the tier math. Dust Devil verified them against deadlock.wiki (65 base, +60 at T1, scale 0.3 to 1.3 at T3). `ability_by_name(name, hero_id)` raises `ValueError` on a name that several heroes own, because every hero has a "Melee". `for_hero(hero_id)` and `hero_gun(hero_id)` list them.

## Hero level scaling and breakpoints

First seen 2026-07-08.

Hero level scaling sits on `Hero`. `level_up` holds the per-boon stat increments, `levels` the soul thresholds per level, and `purchase_bonuses` the shop tier bonuses. `base_health(level)`, `spirit_power(level)`, and `level_for_souls(souls)` compute expected base health and spirit at any point in a match, because the snapshot stats carry each player's `level`.

`Hero.stats_at(souls)` and `boon_stats(level)` return level, health, spirit, bullet damage bonus, light and heavy melee, and ability points and unlocks. `deadlock hero <name> --souls N` (or `--level N`) prints them with gun dps. Melee boons: the per-boon melee increment applies to light melee, and heavy keeps the hero's base heavy to light ratio, mostly 2.32. Wiki confirmed: Mirage +1.58 light and +3.67 heavy per boon.

## Shop investment spikes

First seen 2026-07-08.

`Hero.cost_bonuses` and `investment_bonus(slot, spent)` are the shop's souls-invested bonus curve, the graph above each category. The steps are deliberately uneven. 4,800 invested is a designed power spike in every category. Spirit gives +19 spirit power there against +4 and +7 for the neighbors, weapon gives +28%, and vitality gives +18. Spirit spikes again at 28,800 (+25).

## Weapon scaling, sandbox verified

First seen 2026-07-11. Verified against live damage 2026-07-10.

`base_weapon_damage_increase` abilities (Gutshot, Ira Domini, Consecrating Grenade, Witching Hour) consume bonus weapon damage in percent points. The points are item percent plus weapon investment percent from `cost_bonuses`, with boons excluded. Gutshot measured 85/115 bare and 126/202 at 58 points (Weighted Shots 40 plus 18 for its own 3,200 souls invested), exactly `value + scale * points`. `deadlock ability --weapon` resolves this.

Kinetic Carbine is different. Actual damage is `5 + 2.75 * full burst`. A full burst is 5 bullets (`burst_shot_count` in the raw API weapon_info, while the bundled weapon record says `bullets: 1`) times bullet damage including boons times `(1 + weapon %)`. Measured 99/223/151/351 across boons and Weighted Shots. Boons multiply with items. The in-game tooltip model (2.80) overshoots actual damage by about 2%, so the ability card leaves Carbine symbolic on purpose. `bullet_damage` (Hellfire Salvo) and `weapon_damage_scale` (Sleight of Hand, Infernal Brand) are still unmeasured.

Recheck when a patch touches the weapon damage formula.

## Melee scaling, sandbox verified

First seen 2026-07-11.

Bashdown measurements (93/200/143/306) matched the bundled model within 1.2. The spirit part is `35 + 1.1 * spirit`. The melee part is `0.5 * heavy`, with heavy keeping the hero ratio through boons. That formula is the `--melee` derivation rule, now proven in game.

The melee stat gains half the weapon investment percent. The Crushing Fists case fits `1 + 22% melee + 27% = 54% / 2` exactly, which is the wiki's "melee scales with weapon damage by 50%". The stat-screen melee number that `--melee` takes already includes it. On-hit riders are not in the stat. Crushing Fists' `bonus_heavy_melee_damage: 25` is a separate 1.25 multiplier on heavy hits that applies after ability scaling. It is in the same category as crit and out of scope for the resolver.

## Patch drift and the committed history

First seen 2026-07-10.

The committed history parquets (`deadlock assets --backfill`) version every patch era, so as-of consumers (`item_events` pricing, `hero_scaling`, `ability_upgrades`, the `--as-of` cards) read the tuning live at match time. The bare `Hero`, `Item`, and `Ability` helpers without a `when` describe the current patch only.

`deadlock assets --backfill --confirm` overwrites the committed parquets by rescanning every build since `assets.snapshots.HISTORY_START`. The scan is cached and near free. Review the diff before committing. There is deliberately no date flag on the CLI, because a narrowed scan truncates the earlier eras. `start_date` exists only as a library parameter for tests.

The assets API can lag a patch by a day or so. The `Live data` line of `deadlock assets` says which build the data is from and whether it trails the installed client.

## No cast events exist

First seen 2026-07-08.

No cast events exist anywhere in the metadata. `player.ability_stats` is only the handful of stacking items and abilities. Those counters are Trophy Collector trophies, Glass Cannon stacks, Sticky Bomb bonus, Restorative Locket charges, and Guided Owl and Assassinate counters. It is exported as the `stacks` table and shown by `match --stacks`. `custom_user_stats` is the named counter pool behind `custom_stats`, see [Custom stats](custom-stats.md).

Active item presses (Debuff Remover), stuns, and debuff windows live only in replay demos, which nothing in this project parses. Do not promise cast counts.

The wire `ability_id` is the murmur2 string token of the engine class name. `abilities.string_token` and `class_by_token` do the mapping, and the assets API ids are the same hash, so ids resolve with no lookup table.

## Skill rating names change

First seen 2026-08-10.

`skill_rating.label(52)` is "Mystic II" on the current names, with Roman subranks I to VI and tiers from `data/skill_rating.json`, refreshed by `deadlock assets`. `label_asof(badge, at)` and `era_labels()` resolve names through the committed rank history instead, which is what a historical badge needs. Season One renamed tiers 3 to 7 on 2026-07-31.

Engine class names like `mirage_tornado` never change, while display names do. `abilities.label()` maps a damage-source class name to the current display name.
