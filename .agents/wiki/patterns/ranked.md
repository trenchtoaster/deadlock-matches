---
status: active
scope: the queue split at build 6652, Rank Points, badges, and the Season One rules
first_seen: 2026-07-27
last_confirmed: 2026-08-10
---

# Ranked

## Why this page exists

Ranked Season One changed what `match_mode 1` means and added a flat point scale that is easy to misread. `deadlock rank`, `deadlock match`, `deadlock winrate --ranked`, and `record_games.net_points` already apply every rule below.

## `match_mode 1` means two things

First seen 2026-07-27. Extended 2026-08-10.

`match_mode 1` was the ranked queue until build 6652 (2026-07-30 12:04 UTC). It is the unranked Standard queue after that build. `matches.ranked_type` is the discriminator. It is null on every game before 6652, `0` for unranked, and `1` for Ranked.

The standing filter is ranked play. It reads `match_mode in (1, 4)`, `game_mode 1`, and `ranked_type` not `0`. That filter gives one continuous competitive record across both eras. Null `ranked_type` counts as ranked because those games predate the field.

The CLI flags map onto the enums this way. `--standard` selects the unranked queue `(1, 1, ranked_type 0)`. `--ranked` selects Ranked Season One alone `(4, 1)`. `--placement`, `--street-brawl`, and `--private-lobby` select `(8, 1)`, `(1, 4)`, and `(2, 1)`. Storage stays cumulative, and modes never mix unless the filters are explicitly lifted.

`winrate --by mode` groups by `ranked_type` too. It prints Standard as two rows, `Standard (ranked)` and `Standard (unranked)`, so the two queues never share a win rate.

The download side cannot span the older queue. Match-history rows carry no `ranked_type`, so `deadlock download` fetches Ranked by default and one explicit mode otherwise.

Recheck when a new season changes the queue enums.

## Rank Points sit on one flat scale

First seen 2026-08-10. Verified against real Ranked games.

`player_rank_initial_flat_progress` and `player_rank_final_flat_progress` sit on one flat scale. Every tier spans 7,000 points. Subranks I to V are 1,000 points wide and VI is 2,000. A badge floor is `(tier - 1) * 7000 + (level - 1) * 1000`. The formula was verified against the observed point spans of all 42 stored badges. Never use `% 1000`, because it misreads every VI subrank.

Eternus is the exception. Its subranks are percentile based, so no point formula places a player inside tier 11. The `deadlock rank` footer shows points with no subrank progress for Eternus.

Never derive a badge from points to label a player. `player_rank_initial_display_rank` is the authoritative stored rank and the only thing to label. Only the starting rank is recorded, so a promotion first shows on the next game.

A win applies `player_rank_desired_progress_change` exactly. The amount scales with `player_rank_initial_win_streak`, the streak carried in. A loss can be clamped at the subrank floor. The applied change is then 0 or a partial drop to the floor, the assigned change stays full, and `player_rank_consumed_demotion_protection` is true. Always report the applied difference, and give the assigned figure only as context.

Placement games carry `display_rank` 0 and 0 points, and `player_rank_initial_calibration_games` counts down. A placement win banks +125 and a placement loss costs nothing. Outcome 5 (not scored) moves nothing. Placement games add nothing to a net points total because the placement bank resets every game.

`record_games.net_points` sums `final_flat_progress - initial_flat_progress` over scored games, so it counts what a game applied and never the assigned change that a floor clamped away.

Recheck when a season changes the subrank widths or the placement bank.

## Season One rules

First seen 2026-08-10.

Beta Season 1 runs 2026-07-30 to 2026-10-08. Unlocking Ranked needs 60 account wins, 3 heroes at 15 wins each, 8 placement matches, and a solo or duo queue. The numbers come from `v1/assets/ranked-seasons` through `cli.rank.season_rules`, with `SEASON_FALLBACK` shipped for a failed request.

The solo or duo rule exists only in that season asset. The per-player party field was dropped from match metadata on 2026-03-12, so party size is not checkable from the tables. See [Matches and players](matches-and-players.md).

An account with zero stored Ranked games prints the eligibility panel instead of the rank table. The panel counts scored wins from the local archive, Standard and Ranked, so unarchived games are not counted and the printed note says so.

Recheck when the season end date passes.

## Leaderboard badges stopped

First seen 2026-08-10.

The per-hero leaderboard endpoint stopped serving the badge fields after the 2026-07-30 update. `players.pool_members` still carries the ledger `rank`, but no report prints it, because a stored ladder rank only ages.

Recheck when the leaderboard endpoint serves badges again.
