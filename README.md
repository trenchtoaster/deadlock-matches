# deadlock-matches

Deadlock match metadata is stored in the Steam HTTP cache (`appcache/httpcache` inside your Steam folder) after the client loads a match. This is the same data that you upload to Statlocker for analysis, so my original goal was to parse the data locally and be able to answer questions about it.

This project is built upon [polars](https://pola.rs) and protobuf. Personal match analysis runs locally against your own Deadlock data, and the comparison commands can also pull public matches from [deadlock-api](https://api.deadlock-api.com).

- archives your match history so Steam's cache eviction never loses a game
- processes the complex protobuf data into parquet tables with defined schemas, synced incrementally with lazy polars queries so reports stay quick as the archive grows
- includes in-depth analysis for all of your matches, and the same views work on matches you download from players you track or pull from the API:
  - souls, damage, healing, and healing prevented by source
  - item and ability timing, golden statue buffs, and stack counters like Sticky Bomb
  - stats the game tracks but never shows: aim against heroes, damage by range, parries, comeback souls, and the gun/melee/ability kill split
  - movement: distance covered, dashes, and time spent sliding, in the air, on ziplines, or standing still
- keeps hero, item, and ability data versioned per patch, so cards and queries use the values that were live when a match was played
- downloads games from top players of your hero and compares your farm, movement, and builds against theirs
- includes reusable polars queries, with [marimo](https://marimo.io) notebooks in the repository as examples for questions that do not fit an existing report

The CLI contains a set of reports built on top of the exported match data. Treat those commands as examples for common questions, not the limit of what the data can answer. The same match metadata uploaded to Statlocker and the match data available from `deadlock-api` can be queried directly, so custom analysis does not need to wait for a dedicated CLI command.

## Why not just use Statlocker?

You definitely can.

As someone who likes to play around with data, I wanted to be able to answer questions about my own games from my terminal without uploading files to a website, and to ask things that no tracker has a view for. This project gave me the chance to explore what the raw data and API endpoints contain.

The complex protobuf data is parsed to simple parquet tables on your computer. The CLI helps answer common questions, and [writing your own queries](#writing-your-own-queries) is how you ask questions that do not fit an existing report. If you already use Claude Code or another LLM agent, there is also an optional skill ([LLM agents](#llm-agents)) that teaches it the same tables and helpers.

## Getting started

### 1. Install the CLI

```
uv tool install deadlock-matches
```

This adds the `deadlock` command to your PATH and [uv](https://docs.astral.sh/uv/) downloads Python if needed. On Python 3.12 or newer, `pip install deadlock-matches` works too.

To update to a new release later, run `uv tool upgrade deadlock-matches`. Running the install command again does not upgrade a tool that is already installed.

The examples below use `deadlock <command>`. Running from a clone instead? Prepend `uv run`, so `deadlock history` becomes `uv run deadlock history`.

### 2. Create and check config.toml

`config.toml` lives in your user config directory (`~/.config/deadlock-matches/` on Linux, `%APPDATA%\deadlock-matches\` on Windows).

Start with `deadlock accounts`. It lists the Steam accounts on your PC with their account IDs (the "Steam32" ID) and prints a ready-to-paste `[accounts]` block along with the path to your `config.toml`.

```
deadlock accounts
```

Then open the file and paste that block in. `deadlock config --edit` creates the starter `config.toml` if it does not exist yet and opens it in your editor.

```
deadlock config --edit
```

- the name is just a label so you can use your Steam account name, profile name, or just a nickname like "main" or "alt"
- the name can be used for any `--account` filter as well, like `--account main`

Finally, `deadlock config` prints the exact path and current settings so you can confirm your accounts and timezone read back correctly.

```
deadlock config
```

Optionally add players to compare yourself against per hero under `[players.<Hero>]` (top ladder accounts, pros, friends, etc).

```toml
# tables sync skips. movement is one row per player per second,
# delete it from this list to export it
# the per minute movement_intervals table always builds
exclude = ["movement"]

# convert timestamps to this timezone (detected from your OS but you can edit)
timezone = "America/Chicago"

# your Steam32 account IDs, `deadlock accounts` lists the ones on this PC
[accounts]
main = 111222333
"old alt" = 123456789

# the player name is just a label for the reports, you can copy and paste their name
# quotes around hero and player names are required if they contain spaces
[players."Mirage"]
"someplayer" = 444555666

[players."Grey Talon"]
"Other Player" = 555666777
"proplayer1" = 666777888
```

- the `movement` exclude is purely about size since it contains one row per player per second (330 KB per match)
  - excluding it does not limit the movement commands. `deadlock match --movement`, `deadlock movement`, and `deadlock compare --stat movement` read the per minute `movement_intervals` table, which always builds and stays around 5 KB per match
  - the per second rows only matter when a question needs exact positions or health at a specific second. `deadlock deaths` uses them to check who was nearby when you died, and custom queries like gank detection or route heatmaps need them too
  - to export them, delete `"movement"` from the list and run `deadlock sync`. The missing table triggers a full rebuild on its own
- commands that read your matches archive the cache into `~/.local/share/deadlock-matches/matches/` (`%LOCALAPPDATA%\deadlock-matches\matches` on Windows)
  - Steam's cache only keeps the last 10,000 files it used for all of Steam combined - archiving the matches ensures you do not lose historical data
  - opening game history and clicking a match puts it back in the cache (or keeps it there), so it works as recovery too
- newly archived matches update the parquet tables automatically. Only the new matches get read each run and running `deadlock sync` yourself stays quick. `deadlock sync --full` rebuilds every table from scratch after a backfill or a schema change

### 3. Import matches

Open your game history in Deadlock to force matches into the Steam HTTP cache:

1. hit Escape
2. click Account in the top right corner
3. click on the games in your match history

Then run:

```
deadlock sync
```

Old games fall out of the Steam cache, and clicking back through months of history one match at a time gets tedious. For those, download your match history from [deadlock-api.com](https://deadlock-api.com) instead, though the API may not have every game either (see [Sync new matches](docs/commands.md#sync-new-matches)):

```
deadlock sync --source api
```

Either way, `deadlock sync` pulls your matches into the local archive and parquet tables. Then confirm the games are readable and get match IDs for the other commands:

```
deadlock history
```

### 4. Read a match

Once matches are synced, `deadlock match` reads your most recent game. It prints the final scoreboard and a per-5-minute breakdown of your own play. Pass a match ID from `deadlock history` to read a specific game instead, and `--hero` shows another player from the match instead of you, teammate or enemy.

```
deadlock match
```

This is the main analysis command. A stack of flags swap the interval table for other views of the same game, like `--souls`, `--damage`, `--laning`, and `--items`. See [the match views in docs/commands.md](docs/commands.md#one-match) for the full set and example output.

### 5. Optional: install the Claude Code skill

This step is only for people who want to use Claude Code or another LLM agent with their local match data. The normal workflow does not require AI.

The Python package includes a Claude Code skill that teaches an agent the CLI, schemas, query helpers, and data pitfalls.

```
deadlock skill install
```

This writes the skill to your Claude skills directory. If you edited your local copy it is left alone unless you pass `--force`. Run `deadlock skill path` to see where it goes on your OS.

Useful skill commands:

```
deadlock skill path
deadlock skill print
deadlock skill install --force
```

The marimo notebooks are example/reference files in the repository. If you want them, browse or download [`notebooks/`](notebooks/) from GitHub. The CLI does not install them.

## Commands

> **Every command has a full example with real output in [docs/commands.md](docs/commands.md).**
> The list below is a quick index, followed by a few examples. The reference page shows what each one actually prints, so it is the best way to see what the data can answer.

*Note - hero, item, and ability examples can drift when Deadlock patches. Asset data from 2026-01-01 onward is included with the package. Current cards use the latest snapshot, and `--as-of` / `--changes` read that history.*

A few flags repeat across commands:

- `--help` is by far the most important flag since it describes all the options
  - `deadlock --help` prints the full help
  - `deadlock <command> --help` prints the help for that command
- `--account` filters your games to one or more of your accounts, by ID or a name from `config.toml`, comma-separated for several (`--account main` or `--account "main, alt1"`). Every command that reads your games takes it and defaults to all accounts in the config
- `--days N` filters your last N days of games (`--days 7`)
- `--since YYYY-MM-DD` filters for data since a date (`--since 2026-07-01`)
- `--hero Mirage` filters a report to one hero (required for the tracked player commands since players are tracked per hero). Quote names with spaces: `--hero "Mo & Krill"`, though capitals and punctuation are optional (`--hero "mo krill"` works too)
- `--min-rating Oracle` limits public stats to lobbies at that average skill rating or higher. `winrate` and `item` default to Eternus, `meta` counts every rating, and `all` disables the filter

### Command index

**Match analysis** reads your local archive. Full output in [docs/commands.md](docs/commands.md#match-analysis).

- `history` - one line per game with the match ID
- `match` - the final scoreboard plus a per-5-minute breakdown of your play. Flags swap the interval table for another view of the same game: `--souls`, `--damage`, `--healing`, `--teams`, `--laning`, `--abilities`, `--items`, `--accolades`, `--buffs`, `--stacks`, `--combat`, `--melee`, `--movement`, `--deaths`, `--kills`
- `winrate` - wins and losses per day, with MVP and Key Player awards and a hero's public win rate
- `laning` - every game bucketed by where your lane stood at 9:00, so you can read whether winning lane wins the game
- `deaths` - deaths bucketed by game time, who kills you, and with movement exported whether you were alone
- `damage` - your damage sources summed across every game of a hero, then the gun/ability/item split game by game
- `healing` - the same for your healing plus the healing your anti-heal denied, with the share that landed on you instead of a teammate
- `souls` - the same for your souls, grouped into waves, roaming, combat, and objectives
- `combat` - the hidden fight counters summed across every game of a hero: aim both directions, damage by range, parries
- `movement` - meters per minute, dashes, and the time sliding, airborne, on ziplines, or standing still across every game of a hero

**Heroes, abilities, and items** reads the bundled asset data and works offline. Full output in [docs/commands.md](docs/commands.md#heroes-abilities-and-items).

- `hero` - base stats and per-boon scaling, `--level` or `--souls` for a point in the game
- `ability` - base numbers with spirit, melee, and weapon scaling, and the per-tier upgrades
- `item` - the shop card, or `--hero` for a full report of the item on that hero
- all three take `--as-of DATE` and `--changes` to read past patches

**Tracked players and public stats** reads games `deadlock download` fetched and the public meta. Full output in [docs/commands.md](docs/commands.md#tracked-players-and-public-stats).

- `leaderboard` - top players of a hero with paste-ready config lines
- `download` - pull recent games from the players you track
- `compare` - your farm, stats, and movement vs your tracked players
- `builds` - what your tracked players buy in wins vs losses
- `meta` - public win and pick rates by rating or over time
- `item --hero` - is an item worth buying, your games plus tracked players plus public meta

**Setup and maintenance** keeps the archive, config, and asset data current. Full output in [docs/commands.md](docs/commands.md#setup-and-maintenance).

- `sync` - pull new matches from the Steam cache into the archive and update the parquet tables
- `accounts` - Steam accounts on this PC with a paste-ready `[accounts]` block for `config.toml`
- `config` - where `config.toml` lives and the settings it holds, `--edit` opens it
- `assets` - refresh the hero, item, and ability values after a patch, `--backfill` extends the `--as-of` history
- `skill` - install the bundled Claude Code skill
- `schema` - column docs for the parquet tables, the data dictionary

### A few of the reports

Here are some examples of the reports which will print out to your terminal. Please take a look at [docs/commands.md](docs/commands.md) for more detailed views for anything which looks interesting to you.

The full scoreboard for a match, then your own play in 5-minute intervals. As you can see, this also includes metrics like healing prevented and golden statue buffs per player which are not shown in game:


```
Match 12345678: Mirage, win, 2026-07-08 07:16, 36:03
Lobby average: The Hidden King Ascendant 1, The Archmother Phantom 6

  Team             Hero                    K/D/A        Souls   Damage Obj damage  Healing Prevented Last hits Denies  Statues
  The Hidden King  Mo & Krill     2 (Key)  10/3/24     57,278   42,261      6,775   33,086       662       248      3       34
  The Hidden King  Wraith                  13/4/14     54,467   34,005     31,478   10,378         0       218      9       28
  The Hidden King  Drifter        1 (MVP)  12/2/26     48,584   44,218     11,763   17,145         0       162      2       41
  The Hidden King  Mirage *                14/3/17     47,025   40,145      2,154   13,132     2,128       162      0       22
  The Hidden King  Lash                    10/6/26     44,284   35,414      6,863    6,953         0       178      3       31
  The Hidden King  Seven                   5/10/8      43,115   21,329      6,736    7,082         0       169      1       12
  The Archmother   Vindicta       3 (Key)  15/8/7      43,969   59,793      2,674    2,312       252       144      2       19
  The Archmother   Ivy                     2/9/7       41,936   22,826        433    7,687         0       213      0       25
  The Archmother   Pocket                  1/9/6       41,040   37,468      4,432       28         0       186      2       15
  The Archmother   Shiv                    4/12/8      36,762   28,261         30    8,004     1,451       123      0        9
  The Archmother   Warden                  3/10/6      36,420   27,756      3,005    1,985         0       192     25       24
  The Archmother   Bebop                   3/16/12     34,944   29,645      2,273   10,218         0       112      2        7

  Time        Souls   /min   K/D/A   Damage   Taken Obj damage  Healing  Prevented Last hits  Troopers Neutrals  Denies
  0-5m        1,764    353   0/0/0      877     636          0      244          0         8         8        0       0
  5-10m       3,747    749   0/0/2    2,550   1,906        173      969          0        17        14        3       0
  10-15m      8,442  1,688   4/0/1    4,482   4,028      1,334    1,635        310        15        13        2       0
  15-20m      3,898    780   1/1/2    2,832   3,072          0    1,430        172        16        15        1       0
  20-25m      6,880  1,376   2/1/3    5,975   4,097          0    1,618        396        14        11        3       0
  25-30m     10,868  2,174   1/0/4    8,024   9,465          0    3,085        621        26        26        0       0
  30-35m      9,264  1,853   2/1/3   11,835   9,629        647    3,724        539         7         3        4       0
  35-37m      2,162  2,059   4/0/2    3,570   1,232          0      427         90         0         0        0       0
  Total      47,025  1,304 14/3/17   40,145  34,065      2,154   13,132      2,128       103        90       13       0
```

`match --combat` gives every player in the match a hero-only accuracy line: shots, hit rate, and headshot rate against enemy heroes with troopers and other NPCs left out, plus the gun and headshot damage that aim produced. Your row is marked `*`:

```
  Aim vs heroes
  Hero          Side     Shots  Hit rate  HS rate  Gun damage  Headshot damage
  Celeste       enemy      387     26.4%    23.5%       3,339            1,416
  Drifter       enemy    1,688     17.8%    16.3%       4,624              924
  Pocket        enemy    2,097     27.7%    14.3%       3,178            1,039
  Mirage *      ally       951     38.5%    13.9%       9,523            2,759
  Wraith        enemy    3,892     20.5%     7.5%       6,949              771
```

`match --melee` ranks the lobby by melee dealt and taken between heroes, with parries landed and missed:

```
  Melee
  Hero          Side    Melee dealt  Melee taken  Parried  Missed parry
  Venator       ally          6,420          141        -             5
  Yamato        ally          5,043        1,152        5             8
  Victor        enemy         1,477        2,859        2             4
  Mirage *      ally             58          792        1             3
```

`match --healing` breaks the healing your anti-heal denied out by source:

```
  Source               0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-40m   40-42m    Total      %
  Healbane                0        0      245      208      498      412       14      494       18    1,889    91%
  Toxic Bullets           0        0        0        0       10       15        4       94        7      130     6%
  Inhibitor               0        0        0        0        0        0        0       41       14       55     3%
  Total                   0        0      245      208      508      427       18      629       39    2,074
```

`match --stacks` pulls the stack counters for the whole lobby, like an enemy Bebop's Sticky Bomb:

```
  Stacks
  Hero       Side   Stack                Final
  Bebop      enemy  Sticky Bomb            154
  Bebop      enemy  Trophy Collector        16
  Sinclair   enemy  Trophy Collector        16
```

`match --movement` shows meters moved, pace, and the share of time spent sliding, airborne, and dashing. None of this data appears anywhere in game:

```
  Hero          Side   Meters   /min  Stationary   Slide  In air  Zipline  Fighting  Dashes  Air dash
  Mirage *      ally   14,446    393        9.2%    5.6%    7.8%     7.3%     25.7%      70        34
  Infernus      ally   15,521    424        4.5%    8.9%    9.9%     5.4%     15.8%      58        83
  Victor        enemy  15,558    446        9.9%   10.2%   15.1%     6.6%     23.4%      65       127
```

`match --teams` prints out a timeline of every objective in order, each Unstable Rift win, and each Soul Urn run with the runner. A late-game slice:

```
   28:02  your team destroys the enemy Walker (yellow)

   30:00  enemy team delivers the Soul Urn (Victor, +2,000 souls)
   30:00  your team wins an Unstable Rift (+728 souls each)
   31:32  your team destroys the enemy Walker (green)
   33:31  your team kills the mid boss and claims the Rejuvenator
   34:11  enemy team destroys your Walker (blue)
   35:00  enemy team wins an Unstable Rift (+987 souls each)
   35:00  your team delivers the Soul Urn (Venator, +2,128 souls)
```

`deadlock winrate` prints your wins and losses per day, with MVP and Key Player awards and the average lobby skill rating. `--by week` or `--by month` rolls the days up:

```
  Week          Games    W    L   Win rate         Lobby   MVP   Key  Abandons   Net wins   Cumulative net
  2026-06-15       24   17    7      70.8%     Phantom 4     1     2         1        +10              +10
  2026-06-22       26   14   12      53.8%     Phantom 2     1     3         2         +2              +12
  2026-06-29        3    2    1      66.7%     Phantom 3     0     1                   +1              +13

Overall: 53 games, 33-20, 62.3% win rate, +13 net wins, 2 MVP, 6 Key Player, Phantom 3 lobbies.

Abandons: 3 games — an ally left 1 (0-1), an enemy left 2 (2-0).
  Without them: 50 games, 31-19, 62.0% win rate.
```

`deadlock laning` buckets every game by where your lane stood at 9:00, so you can read whether winning the lane wins the game. A second table buckets the same games by the worst teammate death count before the mark.

```
  Lane result               Games     W     L   Win rate
  lost lane                    31    19    12      61.3%
  won lane                     21    15     6      71.4%

Worst teammate deaths by 9:00, you excluded (2 games with an ally abandon left out):

  Deaths                    Games     W     L   Win rate
  0-1                           3     2     1      66.7%
  2-3                          38    28    10      73.7%
  4+                            9     4     5      44.4%
```

`hero`, `ability`, and `item` cards can read past patches. `--as-of` shows the card as it was on a date. For example, we can see back in March when Fire Scarabs was a health steal spell with bullet shred:

```
Fire Scarabs  (Mirage ability)  (as of 2026-03-01)
  ability charges                             4
  ability cooldown                           40
  bullet armor reduction                     -8
  health steal                               45  +1.023 x spirit
```

`--changes` lists every patch that touched a hero, ability, or item. The same history feeds the reports above, so each match reads with the values that were live on its patch.

For every other command and view, see **[docs/commands.md](docs/commands.md)**.

## Maintenance

Each of these has a full example with real output in [docs/commands.md](docs/commands.md#setup-and-maintenance).

- `deadlock sync` pulls new matches from the Steam cache into the archive and updates the parquet tables. Report commands do a quiet sync first, so `deadlock history` after a session usually shows the new games on its own. `--source api` downloads your match history from deadlock-api.com instead
- `deadlock accounts` lists the Steam accounts on this PC that have run Deadlock, with a paste-ready `[accounts]` block for the ones `config.toml` does not name yet
- `deadlock config` prints where `config.toml` lives and the settings it holds. `--edit` opens it in your editor
- `deadlock assets` pulls the current hero, item, and ability values after a Deadlock patch, and `deadlock assets --backfill` brings the `--as-of` and `--changes` history up to the new patch

### API cache

Leaderboards, match histories, and analytics responses are cached as json under `~/.cache/deadlock-matches/api/` (`%LOCALAPPDATA%\deadlock-matches\cache\api` on Windows).

- entries refresh after a day, and a stale copy still serves when the API is unreachable
- cache files untouched for 30 days are deleted on the next command that talks to the API. Only files this tool wrote (`v1*.json` in that directory) are ever removed, and every one can be redownloaded
- match bodies, parquet tables, and the per-build asset data live elsewhere and are never cleaned up

### Removing everything

All data lives in two directories. On Linux and macOS, this removes the local data and cache:

```
rm -rf ~/.local/share/deadlock-matches ~/.cache/deadlock-matches
```

On Windows both live under `%LOCALAPPDATA%\deadlock-matches`, so delete that directory for the same reset.

- `matches/` inside the data directory is the one thing that cannot be rebuilt: Steam evicts its copies and the replay servers only keep match bodies for a few months. Copy it somewhere first if you might come back
- the parquet tables, asset data, and cache all rebuild or redownload from the archive and the API
- `config.toml` lives in your user config directory (`~/.config/deadlock-matches/`, `%APPDATA%\deadlock-matches\` on Windows), separate from the data directory, so resetting the data leaves it alone. `deadlock config` prints its path

## The parquet tables

The raw match data is deeply nested protobuf, so every match has to be processed one at a time. Sync flattens the reusable parts into parquet tables. Any question across your whole match history can be answered with polars, and the same files work with [DuckDB](https://duckdb.org), [pandas](https://pandas.pydata.org), or anything else that reads parquet.

The tables are stored in `~/.local/share/deadlock-matches/parquet/` (`%LOCALAPPDATA%\deadlock-matches\parquet` on Windows) and update automatically when new matches show up. Match tables are partitioned by month under directories like `players/` and `damage/`, and asset-history tables live under `assets/`.

Use the CLI when you want to see the data shape on your machine:

```
deadlock schema
deadlock schema players
deadlock schema players --sample
deadlock schema players --sample 10
```

`deadlock schema [table]` prints the data dictionary with the data type and description per column. `--sample` prints local rows, which is useful for checking join keys and real values before writing a query.

The main match tables are `matches`, `players`, `stats`, `soul_sources`, `item_events`, `buffs`, `stacks`, `custom_stats`, `damage`, `damage_sources`, `mid_boss`, `movement`, and `deaths`. For table descriptions and query patterns, see [docs/data.md](docs/data.md).

Sizes scale with the archive. Here is the data per 100 matches based on a real archive:

| Table | Rows | Size |
| --- | --: | --: |
| `movement` | 2,600,000 | 33 MB |
| `damage_sources` | 920,000 | 2.5 MB |
| `custom_stats` | 640,000 | 1.1 MB |
| `damage` | 230,000 | 1.3 MB |
| `soul_sources` | 150,000 | 0.3 MB |
| `movement_intervals` | 43,000 | 0.5 MB |
| `item_events` | 38,000 | 0.2 MB |
| `accolades` | 30,000 | 0.1 MB |
| `buffs` | 13,000 | <0.1 MB |
| `stats` | 12,000 | 0.7 MB |
| `deaths` | 7,200 | 0.2 MB |
| `objectives` | 2,100 | <0.1 MB |
| `players` | 1,200 | <0.1 MB |
| `stacks` | 430 | <0.1 MB |
| `mid_boss` | 160 | <0.1 MB |
| `matches` | 100 | <0.1 MB |

That is about 40 MB per 100 matches, but the vast majority is from the per-second movement data which is why the default config excludes it. The asset-history tables under `assets/` are a fixed ~0.4 MB and do not grow with the archive.

## Writing your own queries

Questions like these are a few lines of polars each:

- what is my win rate per hero?
- what is my accuracy? headshot rate? is it improving over time?
- when do I usually buy an item, and do I win more when I get it early?
- has my farm at 10 minutes improved recently?

The `deadlock_matches.queries` module handles common joins and filters, so a query is mostly the aggregation. Use `deadlock schema [table] --sample` to see the real rows, then see [docs/data.md](docs/data.md) for table descriptions and query patterns.

This repository also has optional marimo notebooks under [`notebooks/`](notebooks/) if you are browsing a source checkout. They are examples only and are not installed with the CLI.

## Accuracy

The numbers are checked against sources that don't depend on this code:

- match metadata processed locally matches [deadlock-api](https://api.deadlock-api.com) field for field
- damage per source reproduces the damage graph the game shows after a match
- hero boon scaling and ability numbers match the [Deadlock Wiki](https://deadlock.wiki) (health, spirit, bullet and melee per boon, ability tier upgrades)

## LLM agents

LLM agent support is completely optional. The CLI, parquet tables, notebooks, and Python helpers work on their own.

If you do use an agent, the same things that make the tables easy to query manually also make them easy for it.

- `.claude/skills/deadlock-matches` is a Claude Code skill that teaches the agent the CLI, the schemas, and the query helpers, so it writes the same polars you would
- installed users can run `deadlock skill install` to copy that skill into their Claude skills directory, and `deadlock skill path` prints where it goes on the current OS
- `AGENTS.md` points Codex and other agents at the same file
- the skill has notes about the parts of the data that are easy to get wrong (rows that double count, snapshot stats that are not aligned with the scoreboard) so an agent does not provide wrong answers

With an agent you ask in English instead of writing the query yourself. Real questions from my own sessions:

- Where do I fall behind top Mirage players in souls? Am I missing waves or are they getting more boxes?
- Is Healbane worth buying early? Keep in mind health pools are much lower early game, so preventing healing each wave can be impactful.
- Do I do better when I hit my 4.8k gun spike before my 4.8k spirit spike?
- For matches where I purchase Echo Shard, am I doing more damage overall? Does my Dust Devil damage increase significantly?

## Valve protos

The schema files in `protos/` and the generated code in `src/deadlock_matches/gen/` describe Valve's match metadata messages. They come from [SteamDatabase/Protobufs](https://github.com/SteamDatabase/Protobufs), are copyright Valve Corporation, and are included so the tool can read the match files already on your computer. Everything else in this repository is MIT licensed.
