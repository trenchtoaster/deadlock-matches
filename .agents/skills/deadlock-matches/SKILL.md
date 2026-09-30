---
name: deadlock-matches
description: Decode and analyze Deadlock match metadata from the Steam httpcache (the .meta.bz2 protobufs uploaded to statlocker). Use to answer questions about the user's matches, item value, top-player builds, or farm/combat pacing, or to extend this repo's tooling.
---

# Deadlock match metadata

Reads match metadata from Steam's HTTP cache and compares the user's games against the players they track. Answer plain-English questions by running the CLI, or write ad-hoc Python against the modules for novel ones.

## Invoking the CLI

The examples call `deadlock <command>`, the name that an installed tool puts on PATH (`uv tool install deadlock-matches` is the recommended setup). A source clone has no `deadlock` on PATH. Prepend `uv run` from the repo root, so `deadlock history` becomes `uv run deadlock history`. Check which case applies before you run a command. `command -v deadlock` finds an installed tool. Otherwise look for a `pyproject.toml` that names `deadlock-matches` in the working directory and use `uv run`. The ad-hoc Python section at the end assumes a clone and runs scripts with `uv run` from the repo root.

## User config

`config.toml` sets the defaults. `deadlock config` prints its path, and [Storage](references/contracts/storage.md) describes the file.

- "your games" is the union across all accounts in `[accounts]`. `--account` (comma separated) overrides per invocation and takes config names as well as ids (`--account main`), matched case insensitively. Report headers print the names (`config.format_accounts`)
- `--account` also takes a tracked player name from `[players.<Hero>]` or any downloaded account id. `history`, `match` (latest-game form), and the damage, healing, souls, combat, and movement twins then read that player's downloaded games from the players store. `cli.main.resolve_store` flips when every account named is not in config and is in the downloads ledger. A mix of yours and tracked stays on your tables, where the tracked games do not exist. `[accounts]` names win a name collision
- when `[accounts]` is empty, use `deadlock accounts`. It lists the Steam accounts on this PC that ran Deadlock and prints a paste-ready `[accounts]` block. Offer to fill `config.toml` in from it
- `--hero` is always explicit. Take it from the question or the user's recent `history` output
- the `[players.<Hero>]` tables are the comparison pool. `compare`, `builds`, and the tracked part of `item` read only downloaded games whose account id sits in the table, resolved at query time (`players.pool_members`, `pool_games`, `pool_builds`). The pool readers enforce ranked play at read time by default, and `--standard`, `--ranked`, `--placement`, `--street-brawl`, or `--private-lobby` selects one mode instead. Deleting a line removes the player from every comparison without touching data. A bare `deadlock download --hero X` downloads exactly these players' Ranked games. The leaderboard is never auto-downloaded. Read the table through `config.config_players("Mirage")` for ad-hoc analysis. Never hardcode or commit player names or ids
- group matches into local days with `config.config_timezone()`. `start_time` is UTC, so `convert_time_zone()` before `.dt.date()`

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

### Command rules

- run `deadlock history` first when you need a match id
- `deadlock match` splits the game into 5-minute intervals by default, and `--ago` rejects a match id alongside it
- a match none of your accounts played never reaches your tables. `deadlock download --match ID` pulls it into the players tables, and `deadlock match` falls back to them by itself
- `deadlock item "Name" --hero H` drops the stat card, so run the bare form for the card. The meta stats default to Eternus lobbies and above
- the track flow is `leaderboard`, then a paste into `config.toml`, then `download`. Nothing is downloaded from the leaderboard on its own
- read a tracked player's games with `--account <name>` on an archive report, or one downloaded match with `deadlock match ID --hero H`
- both sides of `deadlock compare` read parquet offline. Your games come from your tables and theirs from `parquet-players/` filtered to the config pool
- never hand-roll a win rate in polars. Relay `deadlock winrate` instead
- `deadlock winrate --by mode` lifts the mode filter on purpose. Do not combine it with a mode-selection flag
- `deadlock winrate --hero H` adds the public win rate on the default selection only, because public stats cannot match an explicit mode
- `deadlock winrate` keeps abandoned games in the table and reports the not-scored games under it
- `deadlock rank` reads net points over the window, while the record and the rating read the whole stored season
- an "archive gap before this" note on `deadlock rank` marks a game that the archive lacks. Run `deadlock sync --source api` to backfill what the API has
- `deadlock laning` counts scored games only
- `--hero` is required on `damage`, `healing`, `souls`, `combat`, and `movement`, and fuzzy names resolve, so "mo krill" works
- comeback souls, unspent balances, and the stray-counter Other section stay in `deadlock match --combat`
- archive aim percentiles are not in the CLI. Use `queries.aim_rates` for them
- the tracked-player movement comparison is `deadlock compare movement`, not `deadlock movement`
- `deadlock souls --milestones` interpolates the minute between the 5-minute snapshots
- `deadlock ability --spirit` and `--melee` reject `--souls` and `--level`, because a total already includes boons. `--weapon` takes the item percent plus the weapon shop investment percent, and it is boon free, so it does combine with them
- `deadlock meta --hero H` defaults `--by` to week. The API recomputes any historical window and carries no region dimension, so nothing accumulates locally
- `deadlock meta --min-rating` filters both teams while the buckets use the match average, so a floor shrinks the boundary bucket. Read distributions without a floor
- `deadlock sync --source api` may not find every game. The rest need a click in the in-game match history
- `deadlock sync` self-heals the asset history after a client update, and it carries on when the asset update fails

### The `match` view flags

- `--souls` Total is gross souls earned. Net worth adds starting souls and subtracts death losses. See [Soul sources](references/patterns/soul-sources.md)
- `--damage` groups the sources into gun, abilities, and item procs at read time. See [Damage tables](references/patterns/damage.md)
- `--healing` adds a healing-prevented table per anti-heal item. The game shows healing per source nowhere
- `--teams` decodes only matches on the 2026-06-30 rework build. See [Objectives and mid boss](references/patterns/objectives-and-mid-boss.md)
- `--laning` defaults to 9 minutes, which sits on the 3-minute snapshot cadence. Kills, deaths, and guardian falls filter by event time. The flag ignores `--interval`. See [Stats snapshots](references/patterns/stats.md)
- `--items` prices each buy at the era shop price and pairs an upgrade to the component buys it consumed. See [Item events](references/patterns/item-events.md)
- `--accolades` is the only source for several stats, and the stars shown equal the threshold plus 1. See [Matches and players](references/patterns/matches-and-players.md)
- `--buffs` splits the permanent buffs by where they came from. Matches from build 6712 on record each statue pickup, so Gained sums the recorded values and a pickup timeline follows `--interval`. Older matches price Gained from the statue history era and show no timeline. The footer says which. See [Custom stats](references/patterns/custom-stats.md)
- `--stacks` prints final values only, with no timestamps. See [Queries](references/contracts/queries.md) for `stack_games`
- `--combat` prints whole-match totals and ignores `--interval`. Gun and headshot damage are the two disjoint bullet series that sum to the Bullet total. Enemy fire at you is the whole team combined. See [Custom stats](references/patterns/custom-stats.md)
- `--melee` prints whole-match totals and ignores `--interval`. The melee columns count the bare light and heavy swing, because an ability melee lands under its own damage source. Parry counts include Counterspell and Rebuttal procs. See [Custom stats](references/patterns/custom-stats.md)
- `--movement` divides the slide, air, zipline, and fighting percents by alive seconds, and stationary by moving seconds. See [Movement and deaths](references/patterns/movement-and-deaths.md)
- `--deaths` and `--kills` read the `deaths` table directly, with no movement join. See [Movement and deaths](references/patterns/movement-and-deaths.md)

`compare` has report subcommands. They are `souls`, `damage`, `healing`, `combat`, and `movement`. Do not suggest `--stat`, `soul_sources`, or individual soul groups as public compare modes. `--since` filters your games. `--pool-since` filters tracked games by local match date. `--against someplayer` narrows the tracked pool. `--account someplayer` instead makes that player the subject.

## Aggregate questions

Prefer `deadlock sync` plus polars over looping protobufs for win rates, damage totals, souls curves, and item timing. Run a quick `deadlock history` first. A data report checks the parquet schema before it reads and rebuilds a drifted store, so the tables are then fresh. `deadlock sync --full` forces a full rebuild.

For any count, rate, or total over your own matches, call `queries.summarize()` on a metric view. Do not join `players` to `matches` by hand, and do not write your own win rate. Drop to `scan()` only when the column you need is on none of the views.

```python
from deadlock_matches import queries

queries.summarize(
    queries.my_games, by="hero", measures=["games", "wins", "win_rate"]
).collect()
```

[Queries](references/contracts/queries.md) is the full helper catalog. [Parquet tables](references/contracts/tables.md) lists the tables, the layout on disk, and the read-time labels. `deadlock schema <table>` prints the columns and `deadlock schema --views` prints what `summarize` accepts.

### Caveats

The CLI commands and the `queries` helpers already apply every per-table caveat. Relaying their output or reusing a helper needs nothing more. Read the pattern page for a table in [the knowledge index](references/index.md) before you hand-write raw polars against it. The four that bite most:

- `soul_sources`: the in-game number is `souls + souls_orbs`. Always sum both. See [Soul sources](references/patterns/soul-sources.md)
- `damage` holds final totals and is safe to sum by source. `damage_sources` and `damage_targets` are cumulative snapshots, so a sum across `time_stamp_s` overcounts about 5 times. Filter `target_account_id.is_not_null()` for hero damage and never sum `category == "total"` rows with detail rows. See [Damage tables](references/patterns/damage.md)
- `stats` holds per-sample snapshots. Take the last sample per `match_id` and `account_id`, not `max()`. Snapshot kills and deaths drift from the scoreboard, so use the `deaths` table for the real count. See [Stats snapshots](references/patterns/stats.md)
- `damage_sources` and `soul_sources` samples are sparse and `damage_sources` is right-aligned. Never diff them by hand. Use the `*_intervals` helpers

### Ad-hoc rules

Keep it cheap. One exploratory session cost about 5 scripts and 3 avoidable errors before these rules existed.

- write one scratch script and iterate on it. Do not create a new file per step
- run `deadlock schema <table>` for exact column names before writing a join. The damage keys are `account_id` (the dealer) and `target_player_slot`, and there is no `dealer_slot`
- print compact aggregates (`group_by().agg()`), never per-game dumps. A 30-row table repr burns context and gets truncated. `pl.Config.set_tbl_width_chars(240)` up front avoids re-runs for hidden columns
- run scripts from the repo root with an absolute script path. A `cd` into the scratchpad breaks the `uv run` environment
- cast unsigned columns to signed (`.cast(pl.Int32)`) before a subtraction, because polars wraps around instead of going negative
- sort explicitly before printing or asserting on order. Row order after a join or a group_by is not stable

The protobuf modules stay the tool for per-match detail that the tables do not carry. See [Match metadata](references/contracts/match-metadata.md).

## Presenting results

For per-day or per-interval summaries, render an aligned table with one row per period. Use columns like Day, Games, W, L, Win rate, Net, and Cumulative net. Right-align the numbers and sign the net columns (+3 / -1). Say which time zone groups the periods. End with a one-line overall summary ("26 games, 20-6, 76.9% win rate, +14 net"). Do not dump raw dataframe reprs at the user. `deadlock winrate` prints the weekly version of the table ready-made, and `--by day` prints daily rows. Relay its output instead of rebuilding the table.

## Where the data is

- the archive under `~/.local/share/deadlock-matches/matches/` is the only irreplaceable data. Cache-touching commands print an `archive:` line. Mention it when asked about backups
- a match is cached by viewing it in game (Escape, then Account in the top right, then click the game in match history). Playing alone does not cache it. If a recent match is missing, tell the user to open it in match history and rerun
- `extract.iter_matches()` snapshots the cache into the archive first and then iterates the archive. Prefer it over `iter_meta_files`
- other players' bodies land in the same archive through `players.match_info(match_id)`, and their tables live under the sibling `parquet-players/` directory

[Storage](references/contracts/storage.md) lists every path. [Steam cache and API](references/patterns/steam-cache.md) explains eviction, the Zstandard switch, and the API cache tiers.

## Knowledge

`references/index.md` routes to the pattern and contract pages. Read [Module map](references/contracts/module-map.md) before you extend the code, and keep [Queries](references/contracts/queries.md) current when you add a helper. Record a new verified trap as a dated entry on the matching pattern page in the same commit as the fix.
