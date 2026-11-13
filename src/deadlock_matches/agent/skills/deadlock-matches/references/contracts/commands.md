---
status: active
scope: every CLI command, the question it answers, the rules `--help` does not carry, and the `match` view flags
first_seen: 2026-07-08
last_confirmed: 2026-10-02
---

# Commands

## Invoking the CLI

The examples call `deadlock <command>`, the name that an installed tool puts on PATH (`uv tool install deadlock-matches` is the recommended setup). A source clone has no `deadlock` on PATH, so prepend `uv run` from the repo root and `deadlock history` becomes `uv run deadlock history`. Check which case applies before you run a command. `command -v deadlock` finds an installed tool. Otherwise look for a `pyproject.toml` that names `deadlock-matches` in the working directory and use `uv run`. The ad-hoc Python in [Analysis](../guides/analysis.md) assumes a clone and runs scripts with `uv run` from the repo root.

## Common questions

Every command answers one question. Run `<command> --help` for the flags, the defaults, and the mode selectors. The table names the question each one answers and the rules that `--help` does not carry.

| Command | Answers | Notes |
| --- | --- | --- |
| `deadlock accounts` | Which Steam accounts on this PC played Deadlock | Prints a paste-ready `[accounts]` block. |
| `deadlock history [--days N] [--since DATE]` | What did I play, and what are the match ids | The source of the match id that `match` and `download` take. |
| `deadlock match [ID] [--ago N] [--hero H] [--interval N]` | What happened in one game | The scoreboard first, then one player split into 5-minute intervals. |
| `deadlock item "Name"` | What does this item do | The offline stat card. |
| `deadlock item "Name" --hero H [--min-rating R] [--since DATE]` | Is this item worth building on this hero | Your games and the public meta, with no stat card. |
| `deadlock builds --hero H` | What do the tracked players build on this hero | Offline from their downloaded games. |
| `deadlock compare souls --hero H [--milestones] [--against P]` | How does my income compare with the tracked players | `--milestones` flips to target timing. |
| `deadlock compare damage --hero H` | How does my damage compare | |
| `deadlock compare healing --hero H` | How does my healing and anti-heal compare | |
| `deadlock compare combat --hero H` | How does my aim and parrying compare | Whole-window counters. |
| `deadlock compare movement --hero H` | How does my pace compare, and who is in the pool | The audit view for whether the pool blends playstyles. |
| `deadlock leaderboard --hero H [--players N] [--matches N]` | Who are the current top players of this hero | Prints paste-ready `[players."<Hero>"]` lines. |
| `deadlock download --hero H [--account ID] [--match ID]` | Fetch tracked players' games into `parquet-players/` | |
| `deadlock winrate [--by day\|week\|month\|mode\|account] [--hero H]` | Am I winning, and how does it trend | The ready-made table for any win rate question. |
| `deadlock rank [--account A] [--days N]` | What did each Ranked game pay, and where is my rating | One line per game, oldest first. |
| `deadlock laning [--minutes N] [--hero H]` | Does winning lane or a feeding teammate decide my games | `match --laning` at archive scale. |
| `deadlock deaths [--hero H] [--radius N]` | How do I die, and to whom | The solo and outnumbered context needs exported movement. |
| `deadlock damage --hero H [--games N]` | Where does my damage come from across many games | `match --damage` at archive scale. |
| `deadlock healing --hero H` | Where does my healing come from, and what did my anti-heal deny | |
| `deadlock souls --hero H [--milestones] [--step N]` | Where do my souls come from, and when do I reach each mark | |
| `deadlock combat --hero H` | How is my aim, my range profile, and my parrying | |
| `deadlock movement --hero H` | How do I move across many games | |
| `deadlock hero NAME [--souls N]` | What are this hero's stats at a soul breakpoint | The offline card. |
| `deadlock ability "Name" [--souls N] [--spirit N] [--melee N] [--weapon N]` | What are this ability's numbers and tier upgrades | The offline card. |
| `deadlock meta [--hero H] [--by rating\|day\|week\|month]` | What are the public win and pick rates | From deadlock-api.com. |
| `deadlock schema [table] [--views]` | What columns and metric views exist | The data dictionary. Read it before you write polars. |
| `deadlock assets` | Refresh the bundled current-patch data after a patch | |
| `deadlock sync [--full] [--source api]` | Rebuild the parquet tables | |

## Command rules

- run `deadlock history` first when you need a match id
- `deadlock match` splits the game into 5-minute intervals by default, and `--ago` rejects a match id alongside it
- a match none of your accounts played never reaches your tables. `deadlock download --match ID` pulls it into the players tables, and `deadlock match` falls back to them by itself
- `deadlock item "Name" --hero H` drops the stat card, so run the bare form for the card. The meta stats default to Eternus lobbies and above
- the track flow is `leaderboard`, then a paste into `config.toml`, then `download`, and `leaderboard` downloads nothing on its own
- read a tracked player's games with `--account <name>` on an archive report, or one downloaded match with `deadlock match ID --hero H`
- both sides of `deadlock compare` read parquet offline. Your games come from your tables and theirs from `parquet-players/` filtered to the config pool
- never hand-roll a win rate in polars; relay `deadlock winrate` instead
- `deadlock winrate --by mode` lifts the mode filter on purpose, so do not combine it with a mode-selection flag
- `deadlock winrate --hero H` adds the public win rate on the default selection only, because public stats cannot match an explicit mode
- `deadlock winrate` keeps abandoned games in the table and reports the not-scored games under it
- `deadlock rank` reads net points over the window, while the record and the rating read the whole stored season
- an "archive gap before this" note on `deadlock rank` marks a game that the archive lacks. Run `deadlock sync --source api` to backfill what the API has
- `deadlock laning` counts scored games only
- `--hero` is required on `damage`, `healing`, `souls`, `combat`, and `movement`, and fuzzy names resolve, so "mo krill" works
- comeback souls, unspent balances, and the stray-counter Other section stay in `deadlock match --combat`
- archive aim percentiles are not in the CLI, so use `queries.aim_rates` for them
- the tracked-player movement comparison is `deadlock compare movement`, not `deadlock movement`
- `deadlock souls --milestones` interpolates the minute between the 5-minute snapshots
- `deadlock ability --spirit` and `--melee` reject `--souls` and `--level`, because a total already includes boons. `--weapon` takes the item percent plus the weapon shop investment percent, and it is boon free, so it does combine with them
- `deadlock meta --hero H` defaults `--by` to week. The API recomputes any historical window and carries no region dimension, so nothing accumulates locally
- `deadlock meta --min-rating` filters both teams while the buckets use the match average, so a floor shrinks the boundary bucket. Read distributions without a floor
- `deadlock sync --source api` may not find every game, and the rest need a click in the in-game match history
- `deadlock sync` self-heals the asset history after a client update, and it carries on when the asset update fails

## The `match` view flags

- `--souls` Total is gross souls earned. Net worth adds starting souls and subtracts death losses. See [Soul sources](../patterns/soul-sources.md)
- `--damage` groups the sources into gun, abilities, and item procs at read time. See [Damage tables](../patterns/damage.md)
- `--healing` adds a healing-prevented table per anti-heal item. The game does not show healing per source anywhere
- `--teams` decodes only matches on the 2026-06-30 rework build. See [Objectives and mid boss](../patterns/objectives-and-mid-boss.md)
- `--laning` defaults to 9 minutes, which sits on the 3-minute snapshot cadence. Kills, deaths, and guardian falls filter by event time. The flag ignores `--interval`. See [Stats snapshots](../patterns/stats.md)
- `--items` prices each buy at the era shop price and pairs an upgrade to the component buys it consumed. See [Item events](../patterns/item-events.md)
- `--accolades` is the only source for several stats, and the stars shown equal the threshold plus 1. See [Matches and players](../patterns/matches-and-players.md)
- `--buffs` splits the permanent buffs by where they came from. Matches from build 6712 on record each statue pickup, so Gained sums the recorded values and a pickup timeline follows `--interval`. Older matches price Gained from the statue history era and show no timeline. The footer says which. See [Custom stats](../patterns/custom-stats.md)
- `--stacks` prints final values only, with no timestamps. See [Queries](queries.md) for `stack_games`
- `--combat` prints whole-match totals and ignores `--interval`. Gun and headshot damage are the two disjoint bullet series that sum to the Bullet total. Enemy fire at you is the whole team combined. See [Custom stats](../patterns/custom-stats.md)
- `--melee` prints whole-match totals and ignores `--interval`. The melee columns count the bare light and heavy swing, because an ability melee lands under its own damage source. Parry counts include Counterspell and Rebuttal procs. See [Custom stats](../patterns/custom-stats.md)
- `--movement` divides the slide, air, zipline, and fighting percents by alive seconds, and stationary by moving seconds. See [Movement and deaths](../patterns/movement-and-deaths.md)
- `--deaths` and `--kills` read the `deaths` table directly, with no movement join. See [Movement and deaths](../patterns/movement-and-deaths.md)

The `compare` report subcommands are `souls`, `damage`, `healing`, `combat`, and `movement`. Do not suggest `--stat`, `soul_sources`, or individual soul groups as public compare modes. `--since` filters your games. `--pool-since` filters tracked games by local match date. `--against someplayer` narrows the tracked pool. `--account someplayer` instead makes that player the subject.
