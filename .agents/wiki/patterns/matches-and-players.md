---
status: active
scope: the `matches` and `players` tables, one row per match and one row per match and player
first_seen: 2026-07-08
last_confirmed: 2026-09-06
---

# Matches and players

## Why this page exists

`matches` and `players` are the two tables that every own-game view joins. The fields below look simple and are not. Each entry names the view or helper that already applies the rule. Read the entry only when you hand-write polars against the raw table.

## Two mode enums, both filtered

First seen 2026-07-27.

`matches.match_mode` and `matches.game_mode` are two separate wire enums. A mode filter must set both.

| Mode | match_mode | game_mode |
| --- | --- | --- |
| Standard | 1 (protobuf name `Unranked`) | 1 |
| Ranked | 4 | 1 |
| New Player Placement | 8 | 1 |
| Street Brawl | 1 | 4 |
| Private Lobby (scrims, FACEIT) | 2 | 1 |

The trap is `game_mode`. Street Brawl is a different map and ruleset, and it still carries `match_mode == 1`. A filter on `match_mode` alone mixes Street Brawl into Standard.

The own-game views and `players.pool_games`, `pool_members`, and `pool_builds` apply ranked play at read time by default. That default spans both queue eras. See [Ranked](ranked.md) for the build 6652 split and `ranked_type`.

`queries.mode_context`, `my_games(match_mode=, game_mode=, ranked=)`, and the CLI flags `--standard`, `--ranked`, `--placement`, `--street-brawl`, and `--private-lobby` select one mode without merging. `--calibration` remains an alias for `--placement`. Storage retains every mode. `None` on `match_mode` or `game_mode` lifts that half of the filter, and `ranked=None` lifts the queue split.

Readable names come off the compiled protobuf enum through `queries.match_mode_name`, `queries.game_mode_name`, `extract.MATCH_MODES`, and `extract.GAME_MODES`. Never hardcode a dict of names.

Recheck when Valve adds a mode or when a protobuf update renames the enum.

## Team badge averages

First seen 2026-08-10.

`matches.average_badge_team0` and `average_badge_team1` hold each team's average skill rating as a badge level. The level is `tier * 10 + subrank`, so `95` is Phantom V.

Season One renamed tiers 3 to 7 on 2026-07-31. `queries.skill_rating` uses the current names only, so it mislabels every earlier badge. `queries.skill_rating_asof("average_badge_team0")` maps each row through the names in effect when the match was played.

Every match after build 6652 carries explicit `0/0` averages, so the two fields are dead after that build. Season One Ranked records every player's actual starting badge in `players.player_rank_initial_display_rank` instead. The record queries rebuild the lobby average from it as the mean subrank of the placed players (badge above 0). The average is null when fewer than 6 of 12 players are placed. `record_games` prefers the published pair and falls back to the computed average, so the Lobby column spans both eras.

The first verified Standard match after the update (96478283) carried `0/0` averages, so do not treat a Standard lobby badge as a ranked skill reading.

Recheck when a season renames tiers or when Valve starts to publish the averages again.

## Lane ids and post-game awards

First seen 2026-07-08.

`players.assigned_lane` holds raw lane ids 1, 4, and 6. `queries.with_lane_name` and `player_rows` add `lane` as the color. Yellow is west, blue is center, and green is east. The mapping was verified against movement geometry.

`players.mvp_rank` holds the post-game award. `1` is the match MVP and is always on the winning team. `2` and `3` are Key Player, and `3` is usually the best player on the losing team. `0` is no award.

Your own games aggregate through the `my_games` view, or `record_games` for the winrate window. `queries.player_rows()` reads the table with the current `hero` display name and the lane color. The post-game stat cards live in the `accolades` table, which backs `deadlock match --accolades`.

## Accolades hold stats no other table has

First seen 2026-07-08.

The `accolades` table records the value and the grading threshold of each post-game stat award. The stars shown equal the threshold plus 1. The award names come from the bundled `accolades.json`.

No other table records the gun, melee, and ability kill splits. The same holds for the close-range and long-range kills and damage, the killstreak kills, first blood, the urn deliveries, and the barrier absorption. Read them from `accolades` or from `deadlock match --accolades`.

## Per-player outcome

First seen 2026-07-31.

`players.player_match_outcome` is authoritative per player. `1` is a win, `2` a loss, `3` penalized, `4` penalized party, and `5` not scored. `won` follows it when present. The scored-game measures exclude outcome 5 even when the rest of the match remains scored.

`matches.ranked_type` and `rank_interval`, and the `players.player_rank_*` start and final progress, expected change, calibration, demotion protection, and win-streak columns arrived in the same update. See [Ranked](ranked.md) for how to read them.

`hero_xp_rewards` has one row per grant. `xp_grant` carries the amount and the reason is `0` win, `1` loss, or `2` award. A player can have both a win or loss grant and a separate award grant.

Recheck when the protobuf adds an outcome value.

## The party field is gone

First seen 2026-07-11.

`players.party` was `0` for a solo queue, and players who shared a nonzero id queued together. Ids never crossed teams.

Valve removed the field from the metadata on 2026-03-12, so it is null on everything after. deadlock-api also has null for every recent match. Older archived matches keep it as an unknown wire field that `extract.player_party` recovers. The API json path (`from_api_json`) drops unknown fields, so a match backfilled from the API is null regardless of age.

Consequence for Ranked: the season rule about solo or duo queue lives only in the season asset. Party size is not checkable from the tables and no report may claim it.

## Abandons and reconnects

First seen 2026-07-11.

`players.abandon_time_s` is the game time in seconds when the player got the abandon strike. Null means never flagged. The field does not mean the player stayed gone. A meaningful share of abandoners reconnect and keep playing.

Damage growth between samples after the abandon is the only valid reconnect signal. A disconnected player keeps earning passive souls, the queued build keeps auto-buying, and the idle hero gets farmed where it stands. Buys and deaths therefore prove nothing.

`queries.abandon_record` applies the rule. Use it instead of a hand-rolled check. It backs the winrate footer.

## Not scored

First seen 2026-07-11.

`matches.not_scored` is Valve's own flag. Two triggers are verified. The common one is a safe-to-leave after an early abandon, which produces short games. The other is a cheat conviction that voids a completed game. The one verified case was a full-length ranked game. The `Parry Success` and `Parry Miss` custom stats ran 43 to 81 successes for the convicted side against single digits for everyone else, which is the auto-parry shape.

The flag does not hide the result. `winning_team` stays set, match history still shows the win or loss, and `rewards_eligible` stays true. The most likely meaning is that the game applied no rating change. `deadlock winrate` leaves these games out of the table and reports them under it through `queries.unscored_record`.

Recheck when a not-scored game appears with neither trigger.
