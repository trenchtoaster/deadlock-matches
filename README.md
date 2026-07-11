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
- includes reusable polars queries and a [marimo](https://marimo.io) notebook for questions that do not fit an existing report

The CLI contains a set of reports built on top of the exported match data. Treat those commands as examples for common questions, not the limit of what the data can answer. The same match metadata uploaded to Statlocker and the match data available from `deadlock-api` can be queried directly, so custom analysis does not need to wait for a dedicated CLI command.

## Why not just use Statlocker?

You definitely can.

As someone who likes to play around with data, I wanted to be able to answer questions about my own games from my terminal without uploading files to a website, and to ask things that no tracker has a view for. This project gave me the chance to explore what the raw data and API endpoints contain.

The complex protobuf data is parsed to simple parquet tables on your computer. The CLI helps answer common questions, [writing your own queries](#writing-your-own-queries) is how you ask questions that do not fit an existing report, and `notebooks/getting_started.py` is a marimo notebook that explores some tables interactively. There is also a Claude Code skill ([LLM agents](#llm-agents)) that teaches an agent the same tables and helpers, if you would rather ask about the data in English instead of code.

## Setup

Works on Linux and Windows, the cache path is detected automatically. Two ways to install:

- `uv tool install deadlock-matches` installs the `deadlock` command on its own. [uv](https://docs.astral.sh/uv/) downloads a Python for it if you do not have one. `pip install deadlock-matches` works too on Python 3.12 or newer.
- clone this repository and use `uv run deadlock` instead. Pick this if you want the marimo notebook, the Claude Code skill, or the source next to your queries.

The examples in this README use the `uv run deadlock` form from a clone. With a tool or pip install the prefix goes away and the commands are just `deadlock history`, `deadlock sync`, and so on.

- run `uv run deadlock accounts` to get set up. It writes a starter `config.toml` and lists the Steam accounts on your PC with their account IDs (the "Steam32" ID), so paste the ones that are you into the config.
  - the name is just a label so you can use your Steam account name, profile name, or just a nickname like "main" or "alt"
  - the name can be used for any `--account` filter as well, like `--account main`
- open your game history in Deadlock to force matches into the cache:
  1. hit Escape
  2. click Account in the top right corner
  3. click on the games in your match history
- run `uv run deadlock sync` to pull them in, then `uv run deadlock history` to see them
- `uv run deadlock sync --source api` skips the clicking and downloads your matches from [deadlock-api.com](https://deadlock-api.com) instead, but the API may not have every game (see [Sync new matches](#sync-new-matches))
- optionally add players to compare yourself against per hero under `[players.<Hero>]` (top ladder accounts, pros, friends, etc)

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

- the `movement` exclude is purely about size: one row per player per second is about 330 KB per match, while every other table stays small
  - excluding it does not limit the movement commands. `deadlock match --movement` and `deadlock movement` read the per minute `movement_intervals` table, which always builds and stays around 5 KB per match
  - the per second rows only matter when a question needs exact positions or health at a specific second: the who-was-nearby context in `deadlock deaths`, and custom queries like gank detection, rift fight attendance, or route heatmaps
  - to export them, delete `"movement"` from the list and run `uv run deadlock sync`. The missing table triggers a full rebuild on its own
- commands that read your matches archive the cache into `~/.local/share/deadlock-matches/matches/` (`%LOCALAPPDATA%\deadlock-matches\matches` on Windows)
  - Steam's cache only keeps the last 10,000 files it used for all of Steam combined - archiving the matches ensures you do not lose historical data
  - opening game history and clicking a match puts it back in the cache (or keeps it there), so it works as recovery too
- newly archived matches update the parquet tables automatically. Only the new matches get read each run and running `deadlock sync` yourself stays quick. `deadlock sync --full` rebuilds every table from scratch after a backfill or a schema change

## CLI

*Note - hero, item, and ability examples can drift when Deadlock patches. Asset data from 2026-01-01 onward is included with the package. Current cards use the latest snapshot, and `--as-of` / `--changes` read that history.*

These commands answer common questions from the parquet tables. Adding a command for every possible question is not feasible, so please see the section below on writing your own queries or using LLM agents if something is missing.

The sections below group the commands by what they read. **Match analysis** reads your local match archive and parquet tables. **Heroes, abilities, and items** reads the included asset data. **Tracked players and public stats** covers the comparisons, which read games `deadlock download` fetched from [deadlock-api](https://api.deadlock-api.com), plus the public meta numbers.

A few flags repeat across commands:

- `--help` is by far the most important flag since it describes all the options
  - `uv run deadlock --help` prints the full help
  - `uv run deadlock <command> --help` prints the help for that command
- `--account` picks which of your accounts count, by ID or a name from `config.toml`, comma-separated for several (`--account main` or `--account "main, alt1"`). Every command that reads your games takes it and defaults to all accounts in the config
- `--days N` filters your last N days of games (`--days 7`)
- `--since YYYY-MM-DD` filters for data since a date (`--since 2026-07-01`)
- `--hero Mirage` filters a report to one hero (required for the tracked player commands since players are tracked per hero). Quote names with spaces: `--hero "Mo & Krill"`, though capitals and punctuation are optional (`--hero "mo krill"` works too)
- `--min-rating Oracle` limits public stats to lobbies at that average skill rating or higher. `winrate` and `item` default to Eternus, `meta` counts every rating, and `all` disables the filter

## Match analysis

### Your Steam accounts

```
uv run deadlock accounts
```

- the Steam accounts on this PC that have run Deadlock, with the account IDs you put in `config.toml`
- reads Steam's `userdata/` folders and remembered logins, so it works before any matches are processed
- ends with a ready-to-paste `[accounts]` block for the accounts `config.toml` does not name yet
- the suggested names are neutral on purpose: your account name (the private login) is best kept out of `config.toml`, since the names you pick there are printed in report headers

```
Steam accounts on this PC that have run Deadlock, newest login first:

  Account      Account name       Profile name       Archived games  config.toml
  111222333    mainlogin          someplayer                     36  main
  123456789    oldalt             someplayer                      3

Add the ones that are you to config.toml, the names are yours to change:

[accounts]
alt1 = 123456789
```

### Sync new matches

```
uv run deadlock sync
```

- pulls new matches from the Steam cache into the archive and updates the parquet tables
- run this after opening matches in the in-game history, then use `deadlock history` to get match IDs
- report commands also do a quiet sync first, so `deadlock history` after a session usually shows the new games without a separate command
- the row counts it prints are what the new matches added on that run, not table totals
- `--source api` pulls your match history from deadlock-api.com and downloads any missing matches into the archive without opening them in game
- `--full` rebuilds every table from scratch, needed after a schema change or a backfill
- `--dry-run` shows what would happen without writing anything

```
Archive: 814 matches (+1 new) at ~/.local/share/deadlock-matches/matches

  matches                 1 rows
  players                12 rows
  stats                 132 rows
  soul_sources        1,584 rows
  item_events           411 rows
  damage              2,576 rows
  damage_sources     12,658 rows
  mid_boss                2 rows
  objectives             21 rows
  deaths                 82 rows
Decoded 1 new matches and skipped 813 already exported
```

The API might not have every game an account played, so the sync grabs whatever it does have. The only way to guarantee every match is to click each one in the in-game match history, and the game lets you open roughly 50 before it makes you wait and try again.

### Match history

```
uv run deadlock history
```

- one line per game of yours with the match ID, newest last
- shows your last 10 games, `--days` and `--since` reach further back
- the ID feeds the other commands: `match 12345678`, `download --match 12345678`
- matches you only viewed in game stay hidden unless you name their players with `--account`

```
  Account    Hero           Result  K/D/A        Souls   Damage  Timestamp         Match ID
  main       Mirage         win     10/5/15     58,210   57,784  2026-07-03 20:28  12345678
  main       Mirage         loss    9/12/11     43,912   38,102  2026-07-03 21:22  12345731
  alt1       Vindicta       win     11/2/9      51,004   62,220  2026-07-03 22:37  12345802
```

### One match

```
uv run deadlock match
```

- the final scoreboard of a single match and the per-5-minute interval data for your character by default
- `deadlock match 12345678` reads that match from your tables, `deadlock match` your most recent one. `--hero Wraith` follows another player from the match instead (your games keep all 12 players), and `--interval 10` changes the bucket size
- the scoreboard shows the match screen numbers while the interval columns come from the minute snapshots, so the Last hits totals can differ slightly. Troopers and Neutrals split the interval Last hits column
- a game that is not yours works too: `deadlock download --match <id>` pulls it into the players tables once, and `deadlock match <id> --hero Wraith` reads it from there automatically

```
Match 12345678: Mirage, win, 2026-07-08 07:16, 36:03
Lobby average: The Hidden King Oracle 1, The Archmother Archon 6

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

Each flag below swaps the interval table for a different view of the same match.

#### `--souls`: souls by source

- the in-game souls graph as a table, souls by source per interval, then grouped into lane (troopers and denies), roaming (jungle and breakables), combat, objectives (bosses and the Rift & Urn), and catch-up

```
Souls by source, 5-minute intervals

  Source                  0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-37m    Total      %
  Troopers               1,124    2,831    2,863    2,683    2,500    4,606    3,075      272   19,954    42%
  Enemy Kills               14       31    2,579      462    1,145    2,053    2,280    1,541   10,105    21%
  Neutral Enemies            0      132    1,175      369    1,112      725    1,257        0    4,770    10%
  Kill Assists               0      316      184      274      684    1,093    1,111      349    4,011     9%
  Objectives                 0        0      625        0      350    1,500      400        0    2,875     6%
  Breakable Pickups          0      295      594      110      740      710      261        0    2,710     6%
  Rift & Urn                 0        0      247        0      469        0    1,024        0    1,740     4%
  Team Catch-Up              0      142      175        0      307      181       56        0      861     2%
  Denies                    26        0        0        0        0        0        0        0       26     0%
  Total                  1,164    3,747    8,442    3,898    7,307   10,868    9,464    2,162   47,052

  Lane                   1,150    2,831    2,863    2,683    2,500    4,606    3,075      272   19,980    42%
  Roaming                    0      427    1,769      479    1,852    1,435    1,518        0    7,480    16%
  Combat                    14      347    2,763      736    1,829    3,146    3,391    1,890   14,116    30%
  Objectives                 0        0      872        0      819    1,500    1,424        0    4,615    10%
  Catch-Up                   0      142      175        0      307      181       56        0      861     2%

  Total is gross souls earned by source, the in-game souls breakdown. Net worth (47,025) adds starting souls and subtracts souls lost to deaths.
```

#### `--damage`: damage by source and by enemy

- the in-game damage graph, damage to heroes by source, then grouped into your gun, your abilities (melee counts as one), and item procs split into gun and spirit items, then the same damage split per enemy. The source data samples about every 3 minutes, so an interval can differ from the Damage column in the main view while the totals still match

```
Damage to heroes by source, 5-minute intervals

  Source                     0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-37m    Total      %
  Dust Devil                    0      138      463      748    1,560    2,116    2,106    1,305    8,436    21%
  Fire Scarabs                210      644      796      458    1,244    1,629    1,616      882    7,479    19%
  Djinn's Mark                129      460      487      172    1,053    2,065      967      685    6,018    15%
  Promises Kept               214      522      662      219      606      592      163      858    3,836    10%
  Mystic Shot                   0        0      676        0      482    1,001      749      334    3,242     8%
  Scourge                       0        0        0        0        0        0      825    1,939    2,764     7%
  Escalating Exposure           0        0        0        0        0      660    1,059      804    2,523     6%
  Headhunter                    0      373      640      106      632      374      357        0    2,482     6%
  Promises Kept (crit)        149      263      698       39      382      177      240        0    1,948     5%
  Bloodletting                  0        0       60       62      394       60      516        0    1,092     3%
  Headshot Booster            175      150        0        0        0        0        0        0      325     1%
  Total                       877    2,550    4,482    1,804    6,353    8,674    8,598    6,807   40,145

  Abilities                   339    1,242    1,806    1,440    4,251    5,870    5,205    2,872   23,025    57%
  Items (gun)                 175      523    1,316      106    1,114    1,375    1,106      334    6,049    15%
  Gun                         363      785    1,360      258      988      769      403      858    5,784    14%
  Items (spirit)                0        0        0        0        0      660    1,884    2,743    5,287    13%

Damage dealt to enemy, 5-minute intervals

  Enemy                      0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-37m    Total      %
  Ivy                         863    1,494    1,027      208    3,096      931    1,617      297    9,533    24%
  Warden                        0        0        0      741      797    4,635    1,273    1,103    8,549    21%
  Bebop                         0        0    2,207        0    1,105    1,978        0    3,197    8,487    21%
  Shiv                          0        0      212      457    1,067      293    2,652       96    4,777    12%
  Pocket                       14    1,056      343      398        0      832    1,140      682    4,465    11%
  Vindicta                      0        0      693        0      288        5    1,916    1,432    4,334    11%
  Total                       877    2,550    4,482    1,804    6,353    8,674    8,598    6,807   40,145
```

#### `--healing`: healing and anti-heal

- the same view for your healing, plus a second table for the healing your anti-heal items prevented. The game shows neither per source

```
Healing by source, 5-minute intervals

  Source               0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-37m    Total      %
  Fire Scarabs          244      728    1,051      422      895    1,666    1,308      282    6,596    50%
  Healbane                0        0      329      622      298      275      728      550    2,802    21%
  Dispel Magic            0        0        0        0      250      936      500      250    1,936    15%
  Headhunter              0      241      255       67      258      444      253        0    1,518    12%
  Spirit Rend             0        0        0        0        0        0       39      241      280     2%
  Total                 244      969    1,635    1,111    1,701    3,321    2,828    1,323   13,132

  Abilities             244      728    1,051      422      895    1,666    1,308      282    6,596    50%
  Items (spirit)          0        0      329      622      548    1,211    1,228      800    4,738    36%
  Items (gun)             0      241      255       67      258      444      292      241    1,798    14%

Healing prevented, 5-minute intervals

  Source               0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-37m    Total      %
  Healbane                0        0      310       73      422      694      317      312    2,128   100%
  Total                   0        0      310       73      422      694      317      312    2,128
```

#### `--teams`: the soul lead and objectives

- both teams per interval with the running lead, then every objective and Rejuvenator as it fell, mixed in with each Unstable Rift win (both teams, the souls each player got, noted when the winning team was behind) and each Soul Urn delivery (with the runner). Matches from before the June 30 objective rework carry no rift or urn line, the old modes worked differently

```
Your team: The Hidden King

  Time       Your team  Enemy team      Lead
  0-5m          10,157      10,740      -583
  5-10m         28,675      26,117    +1,975
  10-15m        40,636      32,231   +10,380
  15-20m        30,963      29,937   +11,406
  20-25m        46,210      38,227   +19,389
  25-30m        70,538      34,951   +54,976
  30-35m        56,192      61,814   +49,354
  35-37m        11,379       1,052   +59,681

  Objectives:
    9:08  enemy team destroys your Guardian (green)
   11:51  enemy team destroys your Guardian (blue)
   12:06  your team destroys the enemy Guardian (yellow)
   ...
   27:11  your team kills the mid boss and claims the Rejuvenator
   30:39  your team destroys the enemy Patron
   35:00  enemy team kills the mid boss and claims the Rejuvenator
   36:02  your team destroys the enemy Weakened Patron
```

#### `--laning`: who won each lane

- one section per lane with your lane first, a Yours and Enemy summary row with the two laners under each side, a signed Net row, then the lane's kills and guardian falls in time order. Stat columns read the last snapshot inside the window (9 minutes by default, the samples land every 3 minutes), kills and guardians use exact event times. `--laning 12` widens the window

```
Laning phase through 9:00

Yellow (your lane)
  Lane               Souls  Kills  Deaths   Damage    Taken  Healing  Prevented  Last hits  Denies
  Yours             12,340      2       0    7,218    6,721    4,854          0         70       1
   * Mirage          5,511      0       0    3,427    2,542    1,213          0         25       0
     Mo & Krill      6,829      2       0    3,791    4,179    3,641          0         45       1
  Enemy             10,665      0       2    6,985    7,910    1,179          0         49       1
     Pocket          5,522      0       1    5,274    3,270       28          0         23       1
     Ivy             5,143      0       1    1,711    4,640    1,151          0         26       0
  Net               +1,675     +2      -2     +233   -1,189   +3,675         +0        +21      +0

  3:07    Mo & Krill kills Ivy
  4:20    Mo & Krill kills Pocket
  both guardians up

Blue
  Lane               Souls  Kills  Deaths   Damage    Taken  Healing  Prevented  Last hits  Denies
  Yours             14,669      6       2   10,641    7,972      561          0         55      11
     Wraith          8,344      5       1    4,878    3,438      466          0         30       9
     Drifter         6,325      1       1    5,763    4,534       95          0         25       2
  Enemy             11,274      2       6    7,708    9,949      622          0         55      17
     Shiv            5,853      1       3    3,748    5,396      622          0         21       0
     Warden          5,421      1       3    3,960    4,553        0          0         34      17
  Net               +3,395     +4      -4   +2,933   -1,977      -61         +0         +0      -6

  5:00    Warden kills Drifter
  5:02    Wraith kills Warden
  5:25    Wraith kills Shiv
  ...
  both guardians up

...
```

#### `--abilities`: skill order

- ability unlocks and upgrades in the order you spent them, with the level and soul threshold for that unlock or cumulative AP spend

```
  Ability upgrades
    Time   #  Level  Req souls  Reward  Ability            Rank
    0:27   1      1          0  unlock  Fire Scarabs          1
    0:51   2      2        200  point   Fire Scarabs          2
    1:52   3      3        500  unlock  Djinn's Mark          1
    3:26   4      5      1,400  unlock  Dust Devil            1
    4:27   5      6      2,000  point   Fire Scarabs          3
    ...
   27:07  14     29     26,900  point   Traveler              2
   28:57  15     31     32,100  point   Traveler              3

  Req souls is the threshold for that unlock or cumulative AP spend.
```

#### `--items`: buy order

- every item purchase in buy order, with the shop price on that patch, when an item was sold, the upgrade that consumed it, and the ability an item was imbued into

```
  Item purchases
    Time   #  Item                    Slot      Tier    Cost
    0:59   1  Headshot Booster        weapon       1     800  into Headhunter at 5:29
    5:29   2  Headhunter              weapon       3   3,200
    8:29   3  Mystic Shot             weapon       2   1,600
    9:58   4  Extra Spirit            spirit       1     800  into Improved Spirit at 9:59
    9:59   5  Improved Spirit         spirit       2   1,600  into Boundless Spirit at 34:30
   11:35   6  Healbane                vitality     2   1,600
   16:05   7  Echo Shard              spirit       4   6,400  imbues Dust Devil
   19:28   8  Dispel Magic            vitality     3   3,200
   22:00   9  Compress Cooldown       spirit       2   1,600  imbues Fire Scarabs, into Superior Cooldown at 22:36
   22:36  10  Superior Cooldown       spirit       3   3,200  into Transcendent Cooldown at 32:06
   24:29  11  Mystic Vulnerability    spirit       2   1,600  into Escalating Exposure at 27:03
   27:03  12  Escalating Exposure     spirit       4   6,400
   30:00  13  Scourge                 spirit       4   6,400
   32:06  14  Transcendent Cooldown   spirit       4   6,400
   32:08  15  Duration Extender       spirit       2   1,600  imbues Fire Scarabs, into Superior Duration at 35:06
   34:30  16  Boundless Spirit        spirit       4   6,400
   35:06  17  Superior Duration       spirit       3   3,200

  'into' means the item was consumed by that upgrade, not sold.
```

#### `--accolades`: the post-game stat awards

- the end-of-match stat awards with your number and the reward thresholds you cleared. Several of these stats exist nowhere else in the data: the gun/melee/ability kill split, close and long range kills and damage, killstreak kills, Sinner's Sacrifice jackpots, urn deliveries, and barrier absorption

```
  Accolades
  Stat                           Value  Stars  Award
  kills                             14  **     Killer Instinct
  ...
  secures                           18  *      Social Security
  breakables destroyed              97  *      Championship Box-er
  pickups collected powerup         15  **     Power Overwhelming
  sinners sacrifice jackpot          7  **     Ka-Ching
  killstreak kills                   5  **     We're Going Streaking
  closeup kills                      6  ***    Up Close and Personal
  long distance kills                2  *      From Downtown
  gun kills                          4  ***    Gunslinger
  ability kills                      6  *      The Deadly Spirit
  ...
  damage absorbed                1,033         Well Protected
  headshots                         93  *      Pow, Right in the Kisser
  headshot damage                4,793  **     Head First

  Stars counts the reward thresholds cleared, up to three.
```

#### `--buffs`: permanent buffs

- the permanent buffs you gained, counted per buff and level, with the stats they added up to. Statue pickups get stronger as the game goes on, and the values come from the patch the match was played on. Also lists the temporary bridge buffs you claimed, and breaks down where the permanent buffs came from: statues you collected, sinner jackpots (4 each), and mid boss kills (2 to the whole team). The scoreboard's Buffs column is the same permanent total per player

```
  Permanent buffs
  Buff                   lv1   lv2   lv3  Total     Gained
  max health               2    11     4     17       +370
  spirit power             2     6     0      8        +22
  weapon damage            1     5     2      8       +35%
  fire rate                2     6     1      9     +17.5%
  ammo                     2     6     1      9       +43%
  cooldown reduction       1     7     2     10     +7.75%

  Bridge buffs
  vitality                 2
  movement                 1

  Sources
  statues collected       13   35 broken
  sinner jackpots          8   +32
  mid boss kills           2   +4 to the whole team
  other sources                +12 (urn runs and light melee jackpots)

  Gained uses the per statue values from the patch the match was played on.
```

#### `--stacks`: stack counters (Sticky Bomb, Trophy Collector, etc)

- the stack counts for every player in the match, from the abilities and items that track stacks

```
  Stacks
  Hero       Side   Stack                Final
  Bebop      enemy  Sticky Bomb            131
  Bebop      enemy  Trophy Collector        16
  Sinclair   ally   Trophy Collector        14

  Counts only exist for abilities and items that track stacks.
```

#### `--combat`: parries, shooting accuracy against heroes, and other hidden metrics

- the fight stats the game tracks but never shows. Every player in the match ranked by aim against heroes with the gun damage their aim produced, the fire the enemy team put at you (their whole team combined, no per-enemy split exists) with the familiar all-target accuracy printed for contrast, damage split by the range it was dealt and taken at, parries with your melee pressure and parry item buys, comeback souls with the Unstable Rift called out, and how many souls sat unspent in your pocket. Heroes with their own counters (Celeste stack uptime, Apollo damage prevented) get a section when you play them

```
  Aim vs heroes
  Hero       Side     Shots  Hit rate  HS rate  Gun damage  Headshot damage
  Mirage *   ally       816     44.4%    31.8%       6,038            5,111
  Yamato     enemy    1,551     12.0%    27.4%       5,476              794
  Seven      enemy    2,636     30.8%    26.8%       7,325            5,235
  Victor     ally     3,022     30.7%    22.4%      26,861           12,454
  Ivy        ally     6,915     22.5%    21.1%      15,639            6,063

  Rates count heroes only, the postgame screen counts every target.
  Gun and headshot damage are the two bullet series from the damage graph.

  Enemy team at you: 3,285 shots, 620 (19%) hits, 113 (18%) headshots
  Lucky shots: 3
  Accuracy with troopers and everything else included: 70%

  Damage by range
                  Gun dealt   Ability dealt       Gun taken   Ability taken
  0-10m         4,824 (30%)    21,448 (50%)     3,069 (16%)     9,483 (30%)
  10-20m        5,317 (33%)     7,031 (16%)     3,888 (20%)     7,264 (23%)
  20-30m        3,082 (19%)      3,278 (8%)     3,645 (18%)     5,453 (17%)
  Falloff on your hits: 10% none, 81% partial, 9% max
  Falloff on hits taken: 12% none, 74% partial, 14% max

  Parries
  Successful 1, missed 4
  Melee damage taken (light/heavy melee): 1,982, most from Billy (1,617)

  Souls
  Comeback souls: 2,323
  Unstable Rift comeback: 436
  Souls held unspent on average: 2,648
  Ability points held unspent on average: 1.2
```

#### `--movement`: dashes, slides, and time in the air

- how everyone moved through the match, from the per minute `movement_intervals` table, which always builds even with `movement` in the config exclude list. The Movement table sums the whole match for every player (allies first, most meters first), then your own game splits per interval. Meters covered and the pace while moving, then how much of the alive time went to standing still, sliding, being in the air, riding ziplines, and fighting players, plus dash counts. An interval you spent fully dead prints `-` for the percents

```
  Movement
  Hero         Side   Meters   /min  Stationary   Slide  In air  Zipline  Fighting  Dashes  Air dash
  Mirage *     ally   13,933    397        8.9%    4.0%    9.8%     5.7%     26.0%      71         4
  Haze         ally   12,839    424        7.7%    6.7%    9.0%    10.4%     18.6%     110         9
  Abrams       ally   12,063    409        6.6%    1.5%   11.5%    11.3%     33.2%     110        10
  McGinnis     ally   11,855    386       11.2%    4.0%   13.2%    12.1%     22.9%      57        30
  Wraith       ally   10,993    379       10.6%    1.4%   10.5%    12.4%     19.6%      61         7
  Venator      ally   10,703    358        9.4%    1.3%   16.4%    12.6%     13.5%      81        21
  Ivy          enemy  12,867    454        6.3%    3.6%   11.8%     5.1%     35.6%      85        11
  Drifter      enemy  11,677    433       10.6%    3.7%    9.5%    12.0%     25.7%      51         5
  Infernus     enemy  10,969    394       12.0%    5.8%    9.9%    12.6%     23.4%      64         4
  Shiv         enemy  10,785    373        6.5%    4.0%   11.1%    11.8%     37.3%      74        13
  Lash         enemy  10,614    384       13.7%    3.2%   34.9%    12.8%     28.7%      45        45
  Grey Talon   enemy   9,991    386       11.3%    1.0%    9.1%    16.6%     21.4%     129         9

  Mirage per interval
  Time       Meters   /min  Stationary   Slide  In air  Zipline  Fighting  Dashes  Air dash
  0-5m        1,490    324       10.5%    4.7%    4.3%     7.7%     45.0%       7         0
  5-10m       1,812    384       10.6%    2.1%   12.2%     0.3%     33.4%       4         1
  10-15m      1,847    426        3.8%    2.9%   11.6%     4.0%     17.7%      13         1
  15-20m      2,034    418        8.2%    3.3%   11.3%     2.3%     10.0%      10         1
  20-25m      1,830    402       10.6%    4.3%    9.0%     8.0%     14.7%       6         0
  25-30m      1,685    413        8.6%    1.3%   10.3%    16.0%     28.0%      13         0
  30-35m      2,020    428        8.5%    8.0%   11.0%     5.0%     36.3%      12         1
  35-39m      1,214    376       10.3%    6.1%    8.6%     0.0%     20.3%       6         0
  Total      13,933    397        8.9%    4.0%    9.8%     5.7%     26.0%      71         4
```

#### `--deaths`: damage from enemies and each death event

- the damage each enemy dealt to you per interval, then each death with who killed you, how long the fight lasted, how far away the killer stood, and your respawn timer. A death to troopers or an objective shows `not a player`

```
Damage taken by enemy, 5-minute intervals

  Enemy                0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-37m    Total      %
  Vindicta                0        0    2,017      146      601    1,911      942    3,017    8,634    25%
  Pocket                390    1,725    1,381      903    1,656    1,155        0      819    8,029    24%
  Shiv                    0        0       13      692    1,038    1,075    3,332        0    6,150    18%
  Warden                  0        0        0        0      543    3,094    1,283        0    4,920    14%
  Ivy                   246      181       36      721      439    1,503      187      413    3,726    11%
  Bebop                   0        0      581       67      108      982        0      868    2,606     8%
  Total                 636    1,906    4,028    2,529    4,385    9,720    5,744    5,117   34,065


  Time    Killed by      Killed in  Distance  Respawn
  16:28   Bebop              15.8s        2m      29s
  21:54   Pocket             12.2s       17m      42s
  33:35   Vindicta           10.0s       32m      90s
```

#### `--kills`: damage to enemies and each kill event

- the damage you dealt to each enemy per interval, then the same log from the killer side, each kill with the victim, the distance, and the respawn it cost them

```
Damage dealt to enemy, 5-minute intervals

  Enemy                0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-37m    Total      %
  Ivy                   863    1,494    1,027      208    3,096      931    1,617      297    9,533    24%
  Warden                  0        0        0      741      797    4,635    1,273    1,103    8,549    21%
  Bebop                   0        0    2,207        0    1,105    1,978        0    3,197    8,487    21%
  Shiv                    0        0      212      457    1,067      293    2,652       96    4,777    12%
  Pocket                 14    1,056      343      398        0      832    1,140      682    4,465    11%
  Vindicta                0        0      693        0      288        5    1,916    1,432    4,334    11%
  Total                 877    2,550    4,482    1,804    6,353    8,674    8,598    6,807   40,145


  Time    Kill           Killed in  Distance  Respawn
  10:26   Vindicta            9.0s       80m      25s
  10:34   Bebop              15.7s       15m      18s
  12:42   Bebop                  -       14m      22s
  14:29   Ivy                 9.9s        7m      25s
  16:31   Pocket             14.7s       71m      29s
  ...
  35:32   Bebop              30.8s       13m      78s
  35:39   Ivy                23.6s        6m      78s
```

### Win rate by day

```
uv run deadlock winrate
```

- wins and losses per day, with your MVP and Key Player awards
- `--by week` or `--by month` rolls the table into weekly or monthly rows, weeks start on Monday
- `--hero Mirage` filters to one hero and also adds the public win rate from `deadlock-api.com` under the table, scoped by `--min-rating` (Eternus+ by default)
- Lobby is the average lobby skill rating of the day, averaged in subrank steps
- games where someone abandoned stay in the table (they are still wins and losses), a footer separates them: who left with each record, how many leavers reconnected and finished, and your record without them
- games Valve flagged as not scored are left out of the table and reported under it, match history still shows their result

```
  Day           Games    W    L   Win rate         Lobby   MVP   Key  Abandons   Net wins   Cumulative net
  2026-04-06        4    3    1      75.0%     Phantom 4     1     0                   +2               +2
  2026-04-07        5    2    3      40.0%     Phantom 5     0     1         1         -1               +1
  2026-04-08        3    2    1      66.7%   Ascendant 1     0     0                   +1               +2
  2026-04-09        6    4    2      66.7%     Phantom 5     0     2         1         +2               +4
  2026-04-10        4    1    3      25.0%     Phantom 6     0     0                   -2               +2

Overall: 22 games, 12-10, 54.5% win rate, +2 net wins, 1 MVP, 3 Key Player, Phantom 5 lobbies.

Abandons: 2 games — an ally left 1 (0-1), an enemy left 1 (1-0).
  Without them: 20 games, 11-9, 55.0% win rate.

Not scored: 1 game left out of the table (safe to leave), 0-1 in match history.
```

### Does winning the lane win the game

```
uv run deadlock laning
```

- every scored game bucketed by where your lane stood at 9:00: your lane's souls minus the enemy side's, both read from the stats snapshots
- your own deaths in that window get a table too, with finer buckets since one early death already moves the number
- a second table splits the same games by the worst teammate death count in that window, games with an ally abandon are left out of it since a leaver feeds by definition
- the last table crosses the two, so a lost lane can be read with and without a feeding teammate
- `--days`, `--since`, `--hero`, and `--account` filter like `winrate`
- `--minutes` moves the mark, default 9 like `match --laning`

```
Lane result at 9:00: your lane's souls minus the enemy side's, scored games only.

  Lane at 9:00              Games     W     L   Win rate
  behind 3k+                   32    10    22      31.2%
  behind 1k-3k                 55    23    32      41.8%
  even within 1k               88    52    36      59.1%
  ahead 1k-3k                  47    33    14      70.2%
  ahead 3k+                    13     9     4      69.2%

  Lane result               Games     W     L   Win rate
  lost lane                   137    62    75      45.3%
  won lane                     98    65    33      66.3%

Your deaths by 9:00:

  Deaths                    Games     W     L   Win rate
  0                            95    60    35      63.2%
  1                            82    43    39      52.4%
  2-3                          47    20    27      42.6%
  4+                           11     4     7      36.4%

Worst teammate deaths by 9:00, you excluded (8 games with an ally abandon left out):

  Deaths                    Games     W     L   Win rate
  0-1                          41    28    13      68.3%
  2-3                         146    79    67      54.1%
  4+                           40    17    23      42.5%

Lane result and a feeding teammate (4+ deaths by 9:00):

                            Games     W     L   Win rate
  lost lane, ally fed          28    10    18      35.7%
  lost lane, no feeder        103    50    53      48.5%
  won lane, ally fed           12     7     5      58.3%
  won lane, no feeder          84    57    27      67.9%

Overall: 235 games, 127-108, 54.0% win rate.
```

### Deaths

```
uv run deadlock deaths --hero Mirage
```

- buckets deaths into 10 minute brackets
- tracks which hero killed you and how fast (TTK / time to kill)
- with the `movement` table exported it also shows who was nearby: `Solo` = no teammate within 2000 units, `Outnum` = more enemies than allies plus one, `Enemies` = enemies in range. `--radius` changes the distance

```
262 deaths across 49 games (5.3 per game, 220s dead per game)

  Time        Deaths  /game  Killed in   Solo  Outnum  Enemies
  0-10 min        54    1.1       12.3    37%     37%      2.0
  10-20 min       85    1.7       13.8    39%     47%      2.2
  20-30 min       70    1.4       15.4    40%     43%      2.5
  30+ min         53    1.1       14.7    34%     43%      2.6

  wins: 139 deaths, 42% solo, 42% outnumbered
  losses: 123 deaths, 33% solo, 45% outnumbered

Killed most by: Infernus 21, Shiv 17, Mina 15, Graves 12, Haze 12
```

## Heroes, abilities, and items

These commands read the included hero, ability, item, and rank data instead of your matches, so they need no games and work offline. Asset data from 2026-01-01 onward is included with the package.

### Hero card

```
uv run deadlock hero Pocket
```

- base gun, melee, health, and movement stats plus what each boon adds
- heroes with a second firing mode get an alt fire block under the gun
- ends with the ability names to feed `deadlock ability`

```
Pocket
  bullet damage         4.3  (The Black Sheep)
  gun dps              57.1
  pellets per shot        7
  ammo                   11
  bullets per sec      1.90
  reload time           2.8
  bullet velocity       559

  light melee          60.0
  heavy melee         116.0

  max health            780
  health regen          1.0
  spirit resist        -15%

  move speed            7.2
  sprint speed          1.6
  dash speed           14.7

  stamina                 3
  stamina cooldown      4.5

abilities
  Flying Cloak
  Enchanter's Satchel
  Barrage
  Affliction

Each boon adds (35 boons to level 36 at 48,600 souls):
  bullet damage    +0.14
  health           +36
  melee damage     +1.58 light / +3.05 heavy
  spirit power     +1.1
```

### Hero scaling at a level

```
uv run deadlock hero Seven --level 30
```

- health, spirit power, melee, gun damage, and ability points at a specific point in the game
- `--souls 25000` does the same from a soul count instead of the boon level

```
Seven at level 30
  max health          1,919
  spirit power         31.9
  ability points         26
  ability unlocks         4
  light melee          95.8
  heavy melee         222.3
  bullet damage        17.8  (Cold Calculus, 10.8 base)
  gun dps             103.6
```

### Ability card

```
uv run deadlock ability "Fire Scarabs" --souls 50000
```

- base numbers, spirit scaling, and the values each upgrade tier changes
- `deadlock hero <name>` lists a hero's ability names to feed this command
- `--hero` picks whose when the name is on several heroes
- `--souls` (or `--level`) updates the values using the scaling the hero has at that point
  - in the example below, the ability is level 36 at 48,600 souls, so the scaling is based on 38.5 spirit power that Mirage has at that point (no items)
- `--spirit 100` computes the values at that total spirit power instead (useful to check how much an ability does at 50, 100, 250 spirit for example)
  - the total already includes boons, so it replaces `--souls` and `--level` rather than combining with them
- `--melee 80` does the same for melee scaling at that light melee damage, and heavy melee keeps the hero's heavy to light ratio
  - the two combine: `--spirit 100 --melee 80` resolves both kinds of scaling on one card
- `--weapon 58` resolves weapon scaling (Gutshot, Ira Domini, Consecrating Grenade) at that bonus weapon damage percent, the stat screen number that counts items and the weapon shop investment
  - boons never add weapon damage percent, so this one combines with `--souls` and `--level` too
  - Kinetic Carbine uses its own hidden weapon formula and stays unresolved

```
Fire Scarabs  (Mirage ability at level 36, 38.5 spirit)
  Infest an enemy with fire scarabs, stealing life from them and causing them to deal reduced damage.

  ability cast delay                       0.05
  ability charges                             2
  ability cooldown                           35
  ability cooldown between charge             1
  ability unit target limit                   1
  channel move speed                         -1
  dps                                     11.85  (0.1 x spirit)
  max stacks                                100
  outgoing damage penalty percent           -20
  steal duration                              7

  T1  dps 11.85 -> 18.85

  T2  ability charges 2 -> 4

  T3  outgoing damage penalty percent -20 -> -35, dps 18.85 -> 25.4
```

### Item card

```
uv run deadlock item "Mercurial Magnum"
```

- the shop card for an item, straight from the asset data
- innate stats first, then each passive or active section with the cooldown and description
- adding `--hero` turns it into a full report of the item on that hero, covered with the tracked player commands below

```
Mercurial Magnum  (spirit tier 4, 6,400 souls)
  upgrades from Quicksilver Reload

  max ammo                                 +20%
  spirit power                               +7

Passive  (cooldown 15s)
  Your imbued ability charges up over time with bonus spirit damage, bonus fire rate, and reloads bullets on use. Until your next reload, your bullets deal bonus spirit damage based on your Spirit Power.
  base bullet damage                        25%
  damage                                     60
  fire rate                                +22%
  bullets reloaded                         100%
  charge-up time                            14s
```

### Past patches: `--as-of` and `--changes`

The repo includes a versioned history of every hero, ability, item, and rank going back to 2026-01-01, one era per patch that changed a value. The cards read the current patch by default, but every hero, ability, and item card takes two flags that read that history instead.

`--as-of DATE` shows the card as the game was on a past date. Mirage's gun was stronger in February than it is now:

```
Mirage  (as of 2026-02-01)
  bullet damage        15.2  (Promises Kept)
  gun dps              41.5
  ammo                   16
  bullets per sec      2.72
  reload time           2.6
```

`--changes` lists every patch that touched this hero, ability, or item, with the fields that moved. It reads the same history the cards do, so nothing extra needs downloading:

```
Mirage  (hero change history, 25 eras tracked)

  2026-01-01  build 6076  first tracked

  2026-03-06  build 6359
    level_up.base_bullet_damage_from_level 0.5 -> 0.3

  2026-03-10  build 6384
    cost_bonuses.vitality.0.bonus      75 -> 84
```

The same history feeds the analysis queries, so the ability tuning that was live when the match was played is used instead of just the current values. This data is written into parquet tables (`item_history`, `hero_history`, `ability_history`, `rank_history`, and `statue_history`) and `deadlock schema item_history --sample` reads them.

## Tracked players and public stats

The comparison commands (`compare`, `movement`, `builds`, and the top player part of `item`) all read the same pool: the players you track for a hero. Tracking a player takes three steps, and after the download every comparison runs offline from the downloaded games:

1. **Find candidates.** `deadlock leaderboard --hero Mirage` lists the current top players of the hero with their account IDs and ends with paste-ready config lines:

   ```
   Mirage leaderboard:
     someplayer           111222333    rank 1    Europe
     anothermain          444555666    rank 24   SAmerica

   Track players by pasting lines into config.toml, then `deadlock download --hero "Mirage"`:

   [players."Mirage"]
   "someplayer" = 111222333
   "anothermain" = 444555666
   ```

   Rank is their rank on that hero across regions, from the per-hero leaderboards on [deadlock-api](https://api.deadlock-api.com). The overall ranked ladder is not used here since it says nothing about a specific hero. Anyone works, not just ladder players: for a friend, take the Steam64 number from their Steam profile URL and subtract 76561197960265728, the difference is the Steam32 account ID. A match of theirs you already downloaded also holds the exact ID in the `players` table ([writing your own queries](#writing-your-own-queries)). Searching by name is unreliable, since the only name search is over current Steam persona names, which change often.

2. **Track the ones you want.** Paste their lines under `[players.<Hero>]` in `config.toml`. The name is just a label for reports, keep theirs or write your own.

3. **Download their games.** `deadlock download --hero Mirage` pulls recent ranked games from everyone tracked for the hero. Nothing is ever downloaded from the leaderboard on its own. Re-running adds new games without downloading old ones again.

To stop comparing against someone, delete their line from `config.toml`. The downloaded matches stay on disk (they cost little space and a game can contain more than one tracked player), they just stop being read, and tracking the player again later needs no new downloads. `deadlock movement --hero Mirage --by player` shows who is in the pool with their games and account IDs.

### Hero meta by rating

```
uv run deadlock meta --hero Mirage --by rating
```

- public win rates, pick rates, and match counts from deadlock-api.com
- no flags prints every hero sorted by win rate
- `--by rating` splits by lobby skill rating
- `--by week` (or day/month) shows trends over time
- `--hero` to select one hero
- `--since` and `--until` to limit date ranges
- `--min-rating Oracle` to only count lobbies with an average skill rating of Oracle or higher (all ratings by default)

```
Mirage public data (Oracle+ lobbies, deadlock-api.com)

  Rating            Matches Win rate Pick rate
  Oracle 1            5,523    47.4%     21.2%
  Oracle 2            5,586    48.5%     21.3%
  Oracle 3            5,317    47.8%     21.2%
  Oracle 4            4,958    48.1%     21.0%
  Oracle 5            4,847    48.3%     21.1%
  Oracle 6            4,357    48.4%     21.1%
  Phantom 1           2,849    48.1%     20.9%
  Phantom 2           2,822    47.1%     21.5%
  Phantom 3           2,695    50.5%     22.1%
```

### Tracked player builds

```
uv run deadlock builds --hero Mirage
```

- items your tracked players buy (in wins vs losses), from their downloaded games
- `--min-percent 30` hides items bought in fewer than 30% of the builds
- an expensive late item with a big win/loss gap usually just means the winner got rich enough to buy it

```
Tracked Mirage players (30 downloaded games):

  Player             Games  Rank  Record
  someplayer            10     1  8W 2L
  anothermain           10    14  6W 4L
  thirdmain             10     -  7W 3L

Shared core across 21 winning builds:

  Item                      Win %  Loss %  Median buy   Slot
  Dispel Magic                91%     96%         14m   vitality T3
  Recharging Rush             83%     64%         10m   weapon T2
  Ricochet                    83%     56%         27m   weapon T4
  Toxic Bullets               80%     60%         19m   weapon T3
  Escalating Exposure         74%     44%         24m   spirit T4
  Healbane                    51%     36%          8m   vitality T2
```

### Compare against your tracked players

```
uv run deadlock compare --hero Mirage
```

- your stats vs your tracked players, from their downloaded games, on the same 5-minute intervals the `match` command uses (`--interval 10` for wider rows). Only your ranked games count, matching the pool
- `--stat souls` (default, net worth) takes the `match` column names — `kills`, `deaths`, `assists`, `damage`, `damage_taken`, `obj_damage`, `healing`, `heal_prevented`, `creeps`, `neutrals`, `denies` — and the soul source groups: `farm` (troopers + jungle + breakables + rift/urn souls + deny souls, kill and assist souls excluded), `troopers`, `jungle`, `breakables`, `combat`, `objectives`, `catch_up`, `other`, or `soul_sources` for every income source as one gap table (rift and urn souls show there as the `rift_urn` row)
- the summary table shows each player as one row with their whole-game rate (average and median per minute), you first for contrast. `kills` and `deaths` print as plain counts instead — per game in the summary, per interval in the table below it
- every interval cell is the median of the per-game rates inside that window, so a game only counts while it lasts. The cumulative gap column keeps the running total of the gap column — positive means you are ahead by that point in a typical game, negative means you trail
- late intervals are not shown once too few games reach them on either side, sparse records would skew the medians
- `--since 2026-06-30` keeps only your games from that date, useful when a patch changed the soul economy and old games would drag your median

```
You (111222333, 50 games) vs 3 tracked Mirage players (30 games): souls

  Player             Games  Rank  Last download   Avg/min  Med/min
  you                   50     -              -       978      961
  someplayer            10     1     2026-07-10     1,102    1,056
  anothermain           10    14     2026-07-10       989    1,004
  thirdmain             10     -     2026-07-08     1,041    1,022

  Min       You/min  Them/min   Gap/min Cumulative gap    Games
  0-5           544       561       -17            -85    50/30
  5-10          831       902       -71           -440    50/30
  10-15         873     1,041      -168         -1,280    50/29
  15-20         942     1,105      -163         -2,095    50/29
  20-25       1,110     1,296      -186         -3,025    48/25
  25-30       1,151     1,178       -27         -3,160    41/19
  30-35       1,178     1,041      +137         -2,475    30/8
  35-40       1,633     1,712       -79         -2,870    14/4
  Total         961     1,022       -61

  This table shows the median values for each interval
  Games past 40m left out, too few tracked games reach them
  Biggest souls gap: 20-25m, you 1,110/min vs tracked players 1,296/min
```

### Leaderboard

```
uv run deadlock leaderboard --hero Mirage
```

- the current top players of a hero from the per-hero leaderboard, with their account IDs and paste-ready config lines for the ones you are not tracking yet ([Tracked players](#tracked-players-and-public-stats))
- `--matches` (optionally `--matches 10`) lists each one's recent ranked match ids, win or loss, so you can pick a game to pull
- tracked `[players.<Hero>]` entries show up too, marked `tracked`

```
Mirage leaderboard:
  someplayer           111222333    rank 1    Europe
      12345678  2026-07-05  win   14/2/23
      12345670  2026-07-05  win   19/5/20
  anothermain          444555666    rank 24   SAmerica
      12340013  2026-07-03  win   13/7/17
```

### Download matches from other players

```
uv run deadlock download --hero Mirage
```

- downloads recent games from the players you track into their own parquet tables (see below). Nothing is ever downloaded from the leaderboard on its own
- without `--account` it downloads everyone under `[players.<Hero>]` in your config.toml
- `--account 111222333` downloads a specific player without tracking them (still needs `--hero`, comma-separated for several). Their games archive and `deadlock match` reads them, but only players in config.toml join the comparisons
- `--match 12345678` fetches one match by ID (comma-separated for several), no `--hero` needed: it stores every player in the match, so `match --hero <anyone>` then works on it
- re-running adds new matches without downloading old ones again
- `--games 10` raises how many recent ranked games per player (5 by default)
- any command reads a downloaded game directly by pointing `--parquet` at the tables, for example `deadlock --parquet ~/.local/share/deadlock-matches/parquet-players match <id> --hero Mirage`
- players still on the ladder get their current rank noted when downloaded, so the comparison reports can show it later

### Is an item worth buying

```
uv run deadlock item "Escalating Exposure" --hero Mirage
```

- stats for the item on one hero, your games vs your tracked players
- meta stats count Eternus+ lobbies by default and `--min-rating all` removes that filter
- `--since 2026-06-30` limits your games and the meta stats to matches on or after a date, useful when a patch changed the item
- `--top 15` shows more rows in the bought together table
- if you track players for the hero and ran `deadlock download`, it also shows their damage per minute owned
- damage per minute owned can be compared across games since it ignores how late the item was bought and how long the game went
- % of dmg is how much of your hero damage came from the item while you owned it

```
Escalating Exposure (spirit tier 4, 6,400 souls) on Mirage

Your games (accounts 111222333, 50 found):

  Match      Result  Damage  Owned  % of dmg
  90111222   loss     5,411    33m     10.1%
  90111333   WIN      1,778    17m      9.6%
  90111444   WIN        852     6m      6.5%

              Games    W    L  Win rate  Avg dmg  Dmg/min  % of dmg
  Built          34   20   14     58.8%    1,829      169     10.3%
  Not built      16   11    5     68.8%        -        -         -

Tracked Mirage players: 219 damage per minute owned across 78 builds, 8.5% of their hero damage (their downloaded games)

Results (Eternus+ lobbies):
  win rate 56.8% over 5,292 games, usually bought around 26m
  items at the same price average 58.2%, so it sits 1.5 points below them

Bought together (win rate of games with both, vs the item alone):

  Item                     Win rate Vs alone    Games
  Spiritual Overflow          63.5%     +6.7    1,167
  Superior Duration           62.4%     +5.6    1,350
  Transcendent Cooldown       62.3%     +5.5    1,638
```

### Movement comparison

```
uv run deadlock movement --hero Mirage
```

- movement profile on one hero: how much you slide, dash, and stay airborne, how far you move, and how often you stand still (small radius)
- reads the per minute `movement_intervals` table, which always builds, so no config change is needed
- the Tracked column comes from past `deadlock download` runs for the players you track on the hero, nothing is fetched by this command. Downloads add up over time, so the header says how many tracked players you are compared against and when the last download ran

```
Mirage movement: you (50 games) vs 3 tracked players (34 games, last download 2026-07-01)

  Metric                        You  Tracked      Gap
  meters /min                 388.3    430.0    +41.7
  stationary %                  9.9      7.1     -2.8
  slide %                       3.9      8.3     +4.4
  in air %                      8.1     21.2    +13.1
  zipline %                     6.7      8.5     +1.9
  fighting players %           24.3     26.7     +2.4
  ground dashes /min            1.7      2.4     +0.7
  air dashes /min               0.2      0.8     +0.7
```

- `--by player` shows one row per tracked player instead of the single Tracked column, so you can see exactly who you are compared against and whether they even play alike
- Rank is their hero ladder rank when they were downloaded, `-` for players who were never on the board
- long or wide names (Korean, Cyrillic) are cut to a fixed width so the table stays aligned
- the Tracked averages can blend playstyles: here every tracked player beats the you row on meters and stationary, while in air ranges from 13% to 31% because ground and air Mirages are both viable

```
  Player            Account  Games    Rank   m /min  Stationary   Slide  In air  Zipline  Fighting  Dash/min  Air dash
  you                     -     50       -    388.3        9.9%    3.9%    8.1%     6.7%     24.3%       1.7       0.2
  proplayer1      111222333     14       1    453.2        5.4%    7.0%   13.3%     8.8%     26.4%       2.8       0.3
  someplayer      444555666     10       -    451.7        7.2%    9.2%   31.0%     8.2%     28.2%       1.8       1.8
  otherplayer     555666777     10      23    420.1        7.2%    7.4%   23.1%     8.6%     30.3%       1.9       1.9
```

## Maintenance

### Refresh the game data

```
uv run deadlock assets
```

- redownloads the hero, item, and ability data after a patch

### Table schemas

```
uv run deadlock schema damage
```

- column descriptions for the parquet table ("damage" table in this example)
- add `--sample` after a table name to print the first 5 rows from that parquet table, or `--sample 10` for another count

### API cache

Leaderboards, match histories, and analytics responses are cached as json under `~/.cache/deadlock-matches/api/` (`%LOCALAPPDATA%\deadlock-matches\cache\api` on Windows).

- entries refresh after a day, and a stale copy still serves when the API is unreachable
- cache files untouched for 30 days are deleted on the next command that talks to the API. Only files this tool wrote (`v1*.json` in that directory) are ever removed, and every one can be redownloaded
- match bodies, parquet tables, and the per-build asset data live elsewhere and are never cleaned up

### Removing everything

All data lives in two directories. Deleting them and the repo folder removes every trace:

```
rm -rf ~/.local/share/deadlock-matches ~/.cache/deadlock-matches
```

On Windows both live under `%LOCALAPPDATA%\deadlock-matches`.

- `matches/` inside the data directory is the one thing that cannot be rebuilt: Steam evicts its copies and the replay servers only keep match bodies for a few months. Copy it somewhere first if you might come back
- the parquet tables, asset data, and cache all rebuild or redownload from the archive and the API
- `config.toml` sits in the repo folder and goes with it

## The parquet tables

The raw match data is deeply nested protobuf, so every match has to be processed one at a time. Sync flattens the reusable parts into parquet tables. Any question across your whole match history can be answered with polars, and the same files work with [DuckDB](https://duckdb.org), [pandas](https://pandas.pydata.org), or anything else that reads parquet.

The tables are stored in `~/.local/share/deadlock-matches/parquet/` (`%LOCALAPPDATA%\deadlock-matches\parquet` on Windows) and update automatically when new matches show up. Match tables are partitioned by month under directories like `players/` and `damage/`, and asset-history tables live under `assets/`. `deadlock schema [table]` prints the data dictionary with the data type and description per column. `deadlock schema players --sample` also prints a small local preview, which is useful for checking join keys and real values without opening a notebook.

- `matches`: one row per match
- `players`: one row per player per match, with `hero`, `won`, and `lane` (the starting lane color)
- `stats`: cumulative stat snapshots, every 3 minutes through 15:00 and every 5 minutes after, plus one at match end
- `soul_sources`: souls per income source per snapshot
- `item_events`: item purchases, with names, prices, and tiers merged in from the cached API data. Prices reflect the patch each match was played on
- `buffs`: the buffs each player ended the match with, one row per pickup type with the buff family and level, permanent statue buffs and temporary bridge buffs told apart by the `permanent` column. `statue_history` holds the per-pickup values by patch
- `stacks`: the final counters from stacking abilities and items, one row per counter per player, with the class and display name resolved from the id
- `custom_stats`: the named stat counters the game tracks but never shows, one row per stat per player per snapshot with the family and name split out (parries, accuracy against heroes, damage by range, comeback souls, per-hero counters)
- `damage`: damage, healing, and mitigation per source and target, with the names you see in game like Dust Devil or "Promises Kept (crit)" for headshots. The totals from the match screen and the individual source rows have different `category` values, so filter to one or the other
- `damage_sources`: the same sources over time, cumulative like the in-game damage graph. Summed over targets, split into hero targets and everything else
- `mid_boss`: one row per midboss kill, with when it died, which team killed it, and which team claimed the Rejuvenator
- `movement`: the position of every player, health percent, and movement state (sliding, dashing, ziplining, in combat or not) for every second of the match. The starter config excludes it because it is larger than every other table combined. Delete it from `exclude` if you want to answer questions like these:
  - was I alone when I died?
  - was I on the other side of the map while my team was fighting?
  - do top players slide and air dash more than I do on the same hero?
- `deaths`: one row per death with the time, position, killer, and respawn timer. Joined to `movement`, this answers things like "was I alone when I died" or "how many enemies killed me"

Sizes scale with the archive. Measured on a real archive, per 100 matches:

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

That is about 40 MB per 100 matches, 33 of them movement, which is why the starter config excludes it. The asset-history tables under `assets/` are a fixed ~0.4 MB and do not grow with the archive.

The tables do not cover everything Valve stores yet. The full structure is `CMsgMatchMetaDataContents` in [`protos/citadel_gcmessages_common.proto`](https://github.com/trenchtoaster/deadlock-matches/blob/main/protos/citadel_gcmessages_common.proto) and can be read as plain text. This is a work in progress, and new columns and tables get added as more of that data turns out to be interesting to query.

`deadlock download --hero` builds the same tables for matches from *other* players in the `parquet-players/` directory: the players tracked under `[players.<Hero>]` in config, plus any account or match id you pass to `--account` / `--match`. The layout is identical, so every query works on their games. An extra `downloads` table records which player each match came from, their rank at the time, and when it was retrieved. A match pulled by id has no player, so those columns are null. Re-running adds new matches without downloading old ones again. The comparison commands read only the games of players currently in config, so deleting a config line removes them from comparisons without touching the data.

## Writing your own queries

Questions like these are a few lines of polars each:

- what is my win rate per hero?
- what is my accuracy? headshot rate? is it improving over time?
- when do I usually buy an item, and do I win more when I get it early?
- has my farm at 10 minutes improved recently?

`deadlock_matches.queries` handles the joins and filters these questions share, so a query is mostly the aggregation:

- `scan("damage")` reads any table by name
- `my_games()` is one row per match you played, with the local day for grouping by session
- `final_stats()` is the final stats of every player in every match, with accuracy and headshot rate worked out
- `hero_damage()` is damage against heroes only, safe to sum by source
- `damage_by_source("Mirage")` is whole-game damage totals per source across your games of a hero, the share each gun, ability, and item did, like `deadlock match --damage` summed over every game instead of split into intervals
- `souls_by_source("Mirage")` is the same for souls, where your income came from across your games of a hero (troopers, jungle, bosses, ...), the aggregate of `deadlock match --souls`
- `source_intervals(games, stat="damage")` is similar to `deadlock match --damage`, but tracks data from multiple matches at once in 5-minute intervals
- `team_damage_ranks()` ranks every player by hero damage within their team, with `top_team_damage` for "did they top the chart?"
- `ability_upgrades()` is your ability unlock and upgrade order, with the level and required souls for each unlock or cumulative AP spend
- `item_buys("Echo Shard")` is your purchases of one item, with the buy order within each match
- `item_value("Echo Shard")` is damage per minute owned and the percent of hero damage for one item, works on the download tables too
- `daily_record()` is the frame behind `deadlock winrate`
- `abandon_record()` is one row per match in the same window where someone abandoned, flagging who left and whether they reconnected
- `unscored_record()` is the games Valve flagged as not scored, which the winrate table leaves out
- `my_deaths()` is one row per death in your games, with hero and result joined in
- `death_context()` adds how many allies and enemies were within 2000 units when you died (needs the movement table)
- `movement_profile()` is the per-match frame behind `deadlock movement`
- `hero_scaling()` is base health and spirit power per hero per level

Every query in the module is a lazy polars plan and all collections use the streaming engine. Nothing is read until `.collect()`, the plan prunes the scan down to the columns and rows it actually touches, and memory stays bounded at any archive size. Keep your own queries lazy from `scan()` to `.collect()` and they get the same treatment.

This section is also available as a [marimo](https://marimo.io) notebook if you would rather poke at the tables interactively. It runs the same queries live on your own exported data and needs nothing installed beyond uv:

```
uv run --with marimo --with altair marimo edit notebooks/getting_started.py
```

### Comparing against tracked players

Run `deadlock download --hero Mirage` first. It writes the top Mirage players and anyone from `[players.Mirage]` in `config.toml` to `parquet-players/`. The downloaded tables have the same layout as your own tables, and `players.tracked_player_games()` finds the tracked player's own row in each downloaded match.

This example gets the two groups you need for a comparison, your Mirage games and the tracked players' Mirage games. From there, `source_intervals()` gives the same source breakdown as `deadlock match --damage`, but across every game in the frame.

```python
import datetime as dt

import polars as pl

from deadlock_matches import players, queries

hero = "Mirage"
main = 111222333
since = dt.date(2026, 7, 1)

mine = (
    queries.my_games(accounts=[main])
    .filter(pl.col("hero") == hero, pl.col("day") >= since)
    .select("match_id", "account_id", "day")
    .with_columns(pl.lit("me").alias("player"))
)

others = (
    players.tracked_player_games(["somename", "othername"], hero=hero)
    .select("player", "match_id", "account_id", "day")
)

my_sources = queries.source_intervals(mine, stat="damage")
other_sources = queries.source_intervals(others, stat="damage", parquet_dir=players.PARQUET_DIR)
```

The damage sources include abilities, gun damage, and item procs like Toxic Bullets or Escalating Exposure. Use `stat="healing"` for the same kind of source breakdown as `deadlock match --healing`. For final match totals instead of intervals, `hero_damage()` is the simpler starting point.

The `games` dataframe is just a labeled list of match/player rows, so the same pattern works for any match type you want to compare:

- manually list match IDs for a review set
- filter to won or lost games with `won`
- filter to long or short games with `duration_s`
- filter to a build path by joining `my_games()` to `item_buys()`

Echo Shard is one build example. An early buy is just a filter on `game_time_s`:

```python
early_echo = queries.item_games("Echo Shard", hero, accounts=[main], since=since).filter(
    pl.col("game_time_s") <= 20 * 60
)
```

If you mean "Echo was my first tier-4 item", use `is_first_tier_item`:

```python
echo_first_t4 = queries.item_games("Echo Shard", hero, accounts=[main], since=since).filter(
    pl.col("is_first_tier_item")
)
```

To answer "how often do they top damage on their team?", join the same game rows to `team_damage_ranks()`:

```python
mine.join(
    queries.team_damage_ranks(),
    on=["match_id", "account_id"],
).group_by("player").agg(
    pl.len().alias("games"),
    (pl.col("top_team_damage").mean() * 100).alias("top_damage_percent"),
    pl.col("team_damage_rank").mean().alias("avg_team_damage_rank"),
)

others.join(
    queries.team_damage_ranks(players.PARQUET_DIR),
    on=["match_id", "account_id"],
).group_by("player").agg(
    pl.len().alias("games"),
    (pl.col("top_team_damage").mean() * 100).alias("top_damage_percent"),
    pl.col("team_damage_rank").mean().alias("avg_team_damage_rank"),
)
```

The tables are plain parquet files, so DuckDB, pandas, or a notebook work as well. Here is a manual example of the same analysis an LLM would do to answer the question "how much healing does Toxic Bullets prevent compared to Healbane in my matches?":

```python
import polars as pl

pl.Config.set_thousands_separator(",")

pq = "~/.local/share/deadlock-matches/parquet"
me = 111222333
antiheal = ["Healbane", "Toxic Bullets"]

owned = (
    pl.scan_parquet(f"{pq}/item_events/*.parquet")
    .filter(pl.col("account_id") == me, pl.col("item").is_in(antiheal))
    .join(pl.scan_parquet(f"{pq}/matches/*.parquet"), on="match_id")
    .with_columns(
        pl.when(pl.col("sold_time_s") > 0)
        .then(pl.col("sold_time_s"))
        .otherwise(pl.col("duration_s"))
        .sub(pl.col("game_time_s"))
        .alias("owned_s")
    )
    .group_by("item")
    .agg(pl.len().alias("games"), pl.col("owned_s").sum())
)

prevented = (
    pl.scan_parquet(f"{pq}/damage/*.parquet")
    .filter(
        pl.col("dealer_account_id") == me,
        pl.col("stat") == "heal_prevented",
        pl.col("source_name").is_in(antiheal),
        pl.col("target_account_id").is_not_null(),
    )
    .group_by(pl.col("source_name").alias("item"))
    .agg(pl.col("damage").sum().alias("heal_prevented"))
)

(
    owned.join(prevented, on="item")
    .with_columns((pl.col("heal_prevented") * 60 / pl.col("owned_s")).round(1).alias("per_min_owned"))
    .sort("per_min_owned", descending=True)
    .collect()
)
```
The results show that the healing reduction from Toxic Bullets is quite minor per minute owned:

```
┌───────────────┬───────┬─────────┬────────────────┬───────────────┐
│ item          ┆ games ┆ owned_s ┆ heal_prevented ┆ per_min_owned │
╞═══════════════╪═══════╪═════════╪════════════════╪═══════════════╡
│ Healbane      ┆ 31    ┆ 50,402  ┆ 60,587         ┆ 72.1          │
│ Toxic Bullets ┆ 16    ┆ 16,548  ┆ 2,297          ┆ 8.3           │
└───────────────┴───────┴─────────┴────────────────┴───────────────┘
```

Note, I almost always get Healbane first and the prevention from Toxic Bullets is multiplicative (57.75% combined reduction) so the full 35% is not used. Applying Toxic Bullets takes more time and does not last as long generally in my fights.

## Accuracy

The numbers are checked against sources that don't depend on this code:

- match metadata processed locally matches [deadlock-api](https://api.deadlock-api.com) field for field
- damage per source reproduces the damage graph the game shows after a match
- hero boon scaling and ability numbers match the [Deadlock Wiki](https://deadlock.wiki) (health, spirit, bullet and melee per boon, ability tier upgrades)

## LLM agents

The same things that make the tables easy to query manually also make them easy for an agent.

- `.claude/skills/deadlock-matches` is a Claude Code skill that teaches the agent the CLI, the schemas, and the query helpers, so it writes the same polars you would
- `AGENTS.md` points Codex and other agents at the same file
- the skill has notes about the parts of the data that are easy to get wrong (rows that double count, snapshot stats that are not aligned with the scoreboard) so an agent does not provide wrong answers

With an agent you ask in English instead of writing the query yourself. Real questions from my own sessions:

- Where do I fall behind top Mirage players in souls? Am I missing waves or are they getting more boxes?
- Is Healbane worth buying early? Keep in mind health pools are much lower early game, so preventing healing each wave can be impactful.
- Do I do better when I hit my 4.8k gun spike before my 4.8k spirit spike?
- For matches where I purchase Echo Shard, am I doing more damage overall? Does my Dust Devil damage increase significantly?

## Valve protos

The schema files in `protos/` and the generated code in `src/deadlock_matches/gen/` describe Valve's match metadata messages. They come from [SteamDatabase/Protobufs](https://github.com/SteamDatabase/Protobufs), are copyright Valve Corporation, and are included so the tool can read the match files already on your computer. Everything else in this repository is MIT licensed.
