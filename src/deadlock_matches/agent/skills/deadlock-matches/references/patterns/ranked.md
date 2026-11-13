---
status: active
scope: the queue split at build 6652, the seasons, Rank Points, badges, and the season rules
first_seen: 2026-07-27
last_confirmed: 2026-11-14
---

# Ranked

## Why this page exists

Ranked Season One changed what `match_mode 1` means and added a flat point scale that is easy to misread. `deadlock rank`, `deadlock match`, `deadlock winrate`, and `record_games.net_points` with its three shares already apply every rule below.

## `match_mode 1` means two things

First seen 2026-07-27. Extended 2026-08-10.

`match_mode 1` was the ranked queue until build 6652 (2026-07-30 12:04 UTC). It is the unranked Standard queue after that build. `matches.ranked_type` is the discriminator. It is null on every game before 6652, `0` for unranked, and `1` for Ranked.

The standing filter is ranked play, which reads `match_mode in (1, 4)`, `game_mode 1`, and `ranked_type` not `0`. That filter gives one continuous competitive record across both eras. Null `ranked_type` counts as ranked because those games predate the field.

The CLI flags map onto the enums this way. `--standard` selects the unranked queue `(1, 1, ranked_type 0)`. `--all` reads Ranked and Standard together `((1, 4), 1)` with the `ranked_type` check lifted. `--ranked` is a hidden alias of the default. `--placement`, `--street-brawl`, and `--private-lobby` select `(8, 1)`, `(1, 4)`, and `(2, 1)`. Storage stays cumulative, and modes never mix unless the filters are explicitly lifted.

`winrate --by mode` groups by `ranked_type` too. It prints Standard as two rows, `Standard (ranked)` and `Standard (unranked)`, so the two queues never share a win rate.

The download side cannot span the older queue. Match-history rows carry no `ranked_type`, so `deadlock download` fetches Ranked by default and one explicit mode otherwise.

Recheck when a new season changes the queue enums.

## Seasons are split by rank interval

First seen 2026-11-14. Verified against 1,262 Pre-Season, 344 Beta Season 1, and 28 Beta Season 2 games.

`matches.rank_interval` is the season discriminator. Beta Season 1 is interval 1 and ran 2026-07-30 17:00 UTC to 2026-11-05 20:00 UTC. Beta Season 2 is interval 2 and started at that moment. The ranked games before build 6652 carry a null interval and are the Pre-Season. An unranked Standard game carries interval 0.

`seasons.known` reads the seasons from `v1/assets/ranked-seasons`, with `seasons.SHIPPED` for a failed request. `queries.season_context` keeps ranked play to one season inside `mode_filter`, and it never narrows another mode. The library default is every season. The CLI default is `seasons.current`, the newest season that has started, so a report without a flag reads the current season alone.

`--season` takes `current`, a season number, `pre`, or `all`. A season next to another mode flag is an error. `deadlock rank` reads one season at a time, because Rank Points and placements reset between seasons.

Season 2 changed three numbers. `base_win_loss_point_grant` is 350, so streaks 2 and 3 are assigned 420 and 440. Subrank VI is 1,500 points wide, so a tier spans 6,500. A placement win banks 175. `seasons.Season` carries the grant and the subrank width, `record_games` reads the grant per game through `queries.records.BASE_POINT_GRANTS`, and the `deadlock rank` footer reads the width.

Unlocking Season 2 needs `min_hero_unlock_points` 35 instead of `min_hero_wins`, and no stored field says what a hero unlock point is. The `deadlock rank` eligibility panel still counts 15 wins per hero. Whether the panel matches the Season 2 rule is an open question as of 2026-11-14.

Recheck when a season starts, and add its row to `seasons.SHIPPED`.

## Rank Points sit on one flat scale

First seen 2026-08-10. Verified against real Ranked games.

`player_rank_initial_flat_progress` and `player_rank_final_flat_progress` sit on one flat scale. The widths below are the Beta Season 1 scale, and Season 2 narrowed subrank VI. Every tier spans 7,000 points. Subranks I to V are 1,000 points wide and VI is 2,000. A badge floor is `(tier - 1) * 7000 + (level - 1) * 1000`. The formula was verified against the observed point spans of all 42 stored badges. Never use `% 1000`, because it misreads every VI subrank.

Eternus is the exception. Its subranks are percentile based, so no point formula places a player inside tier 11. The `deadlock rank` footer shows points with no subrank progress for Eternus.

Never derive a badge from points to label a player. `player_rank_initial_display_rank` is the authoritative stored rank and the only thing to label. Only the starting rank is recorded, so a promotion first shows on the next game.

A win applies `player_rank_desired_progress_change` exactly. The amount scales with `player_rank_initial_win_streak`, the streak carried in. A loss can be clamped at the subrank floor. The applied change is then 0 or a partial drop to the floor, the assigned change stays full, and `player_rank_consumed_demotion_protection` is true. Always report the applied difference, and give the assigned figure only as context.

Placement games carry `display_rank` 0 and 0 points, and `player_rank_initial_calibration_games` counts down. A placement win banks +125 and a placement loss costs nothing. Outcome 5 (not scored) moves nothing. Placement games add nothing to a net points total because the placement bank resets every game.

`record_games.net_points` sums `final_flat_progress - initial_flat_progress` over scored games, so it counts what a game applied and never the assigned change that a floor clamped away.

Recheck when a season changes the subrank widths or the placement bank.

## Net points split three ways

First seen 2026-11-02. Verified against 315 placed Ranked games in interval 1.

A win at streak 0 or 1 is assigned exactly 300, the `base_win_loss_point_grant` in the season asset. Streaks 2 to 5 are assigned 370, 390, 410, and 430 at every rank from Acolyte to Mystic. Every loss is assigned -300 except one reduced to -150. Every gap between the applied and the assigned change falls on a game with `player_rank_consumed_demotion_protection` true.

`record_games` splits `net_points` on those facts. `streak_points` sums what wins were assigned above the base grant of their season, 300 in interval 1 and 350 in interval 2. `shield_points` sums the applied minus the assigned change on the shield games. `result_points` is the remainder, so the three always add up to the net. `deadlock winrate` prints Streak and Shields columns and a Points line under Overall. It dropped the Cumulative net column to keep the row width.

Recheck when a season changes `base_win_loss_point_grant`, or when a win or a game without a shield shows a gap between the applied and the assigned change.

## Season One rules

First seen 2026-08-10.

Beta Season 1 ran 2026-07-30 to 2026-11-05. Unlocking Ranked needs 60 account wins, 3 heroes at 15 wins each, 8 placement matches, and a solo or duo queue. The numbers come from `v1/assets/ranked-seasons` through `cli.rank.season_rules`, with `SEASON_FALLBACK` shipped for a failed request.

The solo or duo rule exists only in that season asset. The per-player party field was dropped from match metadata on 2026-03-12, so party size is not checkable from the tables. See [Matches and players](matches-and-players.md).

An account with zero stored Ranked games prints the eligibility panel instead of the rank table. The panel counts scored wins from the local archive, Standard and Ranked, so unarchived games are not counted and the printed note says so.

Recheck when a season changes the unlock rules.

## Season One has two intervals

First seen 2026-10-01.

The `v1/assets/ranked-seasons` payload fetched 2026-10-01 splits `season_1` into two intervals. Interval 1 runs 2026-07-30 17:00 UTC to 2026-10-08 21:00 UTC with `leaderboard_id` 1001. Interval 2 runs 2026-10-08 21:00 UTC to 2028-01-01 08:00 UTC with `leaderboard_id` 1002. A new field `base_win_loss_point_grant` is 300. `calibration_matches` is 8 and `valid_party_sizes` is [1, 2].

The payload fetched 2026-11-14 replaced that layout. Interval 2 now belongs to a separate `season_2` entry that started 2026-11-05 20:00 UTC, and Season 1 keeps interval 1 alone. Points and placements did reset at the boundary. See the section on seasons above.

## Leaderboard badges stopped

First seen 2026-08-10.

The per-hero leaderboard endpoint stopped serving the badge fields after the 2026-07-30 update. `players.pool_members` still carries the ledger `rank`, but no report prints it, because a stored ladder rank only ages.

Recheck when the leaderboard endpoint serves badges again.
