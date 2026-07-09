# deadlock-matches

Deadlock match metadata is stored in the Steam HTTP cache (`appcache/httpcache` inside your Steam folder) after the client loads a match. This is the same data that you upload to Statlocker for analysis, so my original goal was to parse the data locally and be able to answer questions about it.

This project is built upon [polars](https://pola.rs) and protobuf. Personal match analysis runs locally against your own Deadlock data; the comparison commands can also pull public matches from [deadlock-api](https://api.deadlock-api.com).

- archives your match history
- caches API data for heroes, items, and abilities
- processes the complex protobuf data into parquet tables with defined schemas
- includes common polars queries that can be reused
- includes a [marimo](https://marimo.io) notebook for exploring the tables interactively
- includes a [deadlock-api](https://api.deadlock-api.com) client to pull matches from other players so you can compare your games against theirs

The CLI contains a set of reports built on top of the exported match data. Treat those commands as examples for common questions, not the limit of what the data can answer. The same match metadata uploaded to Statlocker and the match data available from `deadlock-api` can be queried directly, so custom analysis does not need to wait for a dedicated CLI command.

## Why not just use Statlocker?

You definitely can.

As someone who likes to play around with data, I wanted to be able to answer questions about my own games from my terminal without uploading files to a website, and to ask things that no tracker has a view for. This project gave me the chance to explore what the raw data and API endpoints contain.

The complex protobuf data is parsed to simple parquet tables on your computer. The CLI helps answer common questions, [writing your own queries](#writing-your-own-queries) is how you ask questions that do not fit an existing report, and `notebooks/getting_started.py` is a marimo notebook that explores some tables interactively. There is also a Claude Code skill ([LLM agents](#llm-agents)) that teaches an agent the same tables and helpers, if you would rather ask about the data in English instead of code.

## Setup

- works on Linux and Windows (the cache path is detected automatically)
- install [uv](https://docs.astral.sh/uv/)
- clone this repository
- run `uv run deadlock accounts` to get set up. It writes a starter `config.toml` and lists the Steam accounts on your PC with their account IDs (the "Steam32" ID), so paste the ones that are you into the config.
  - the name is just a label so you can use your Steam account name, profile name, or just a nickname like "main" or "alt"
  - the name can be used for any `--account` filter as well, like `--account main`
- open your game history in Deadlock to force matches into the cache:
  1. hit Escape
  2. click Account in the top right corner
  3. click on the games in your match history
- run `uv run deadlock history` to process recent matches
- optionally add players to compare yourself against per hero under `[players.<Hero>]` (top ladder accounts, pros, friends, etc)

```toml
# tables the export skips. movement is one row per player per second,
# delete it from this list to export it
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

- commands that read your matches archive the cache into `~/.local/share/deadlock-matches/matches/` (`%LOCALAPPDATA%\deadlock-matches\matches` on Windows)
  - Steam's cache only keeps the last 10,000 files it used for all of Steam combined - archiving the matches ensures you do not lose historical data
  - opening game history and clicking a match puts it back in the cache (or keeps it there), so it works as recovery too
- newly archived matches also trigger an automatic parquet rebuild, so `deadlock export` is only needed to force one

## CLI

*Note - the hero, item, and ability numbers come from the game data from the current patch so the examples below might become outdated over time.*

These commands answer common questions from the parquet tables. Adding a command for every possible question is not feasible, so please see the section below on writing your own queries or using LLM agents if something is missing.

The commands in this section read your own local match archive and parquet tables. After them come the hero, ability, and item lookups, and then the commands that pull top players and public stats from [deadlock-api](https://api.deadlock-api.com).

A few flags repeat across commands:

- `--help` is by far the most important flag since it describes all the options
  - `uv run deadlock --help` prints the full help
  - `uv run deadlock <command> --help` prints the help for that command
- `--account` picks which of your accounts count, by ID or a name from `config.toml`, comma-separated for several (`--account main` or `--account "main, alt1"`). Every command that reads your games takes it and defaults to all accounts in the config
- `--days N` filters your last N days of games (`--days 7`)
- `--since YYYY-MM-DD` filters for data since a date (`--since 2026-07-01`)
- `--hero Mirage` filters a report to one hero (required for the top player commands since they pull from the leaderboard). Quote names with spaces: `--hero "Mo & Krill"`, though capitals and punctuation are optional (`--hero "mo krill"` works too)
- `--min-rating Oracle` limits public stats to lobbies at that average skill rating or higher. `winrate` and `item` default to Eternus, `meta` counts every rating, and `all` disables the filter

### `uv run deadlock accounts`

- the Steam accounts on this PC that have run Deadlock, with the account IDs `config.toml` wants
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

### `uv run deadlock history`

- your recent matches, one row per player with the numbers from the match screen
- your accounts are listed once up top and your hero is marked with a `*`
- shows your last day of games, `--days` and `--since` reach further back
- matches you only viewed in game stay hidden unless you name their players with `--account`

```
You (marked * below): main

Match 12345678: 2731s, The Hidden King won, 2026-07-03 20:28
Lobby average: The Hidden King Ascendant 3, The Archmother Ascendant 3

  Team             Hero                    K/D/A    Net worth   Damage Obj damage  Healing Prevented Last hits Denies
  The Hidden King  Seven          1 (MVP)  7/4/24      59,402   62,667     20,579    8,058         0       247      1
  The Hidden King  Mirage *       2 (Key)  10/5/15     58,210   57,784      8,062   24,004     4,231       160      0
  The Hidden King  Infernus                9/8/13      57,501   31,022      7,470   14,849         0       292      2
  The Archmother   Venator        3 (Key)  13/3/6      62,965   61,977     10,163   29,043     1,268       327      4
  The Archmother   The Doorman             3/6/15      55,408   18,387      1,629    6,032         0       180      6
  The Archmother   Dynamo                  6/6/11      48,292   22,678      7,528   15,098       620       204      9
```

### `uv run deadlock match`

- one player's match split into intervals: souls, kills/deaths/assists, damage dealt and taken, objective damage, healing and prevented healing, troopers, neutrals, denies
- `deadlock match`: your own data from your most recent match
- `deadlock match 12345678`: that match from the archive, your player
- `deadlock match 12345678 --hero Wraith`: another player from the match (any archived match works, including ones you only viewed)
- `deadlock match --hero Abrams`: the Abrams in your most **recent** match
- `--interval 10`: 10-minute intervals instead of 5
- `--souls`: souls by source per interval, like the in-game souls graph, then a block grouping them into lane (troopers and denies), roaming (jungle and breakables), combat, objectives (bosses and urn), and catch-up. The Total row is gross souls earned, net worth adds starting souls and subtracts souls lost to deaths
- `--damage`: damage to heroes by source per interval, like the in-game source graph. Its data is sampled about every 3 minutes, so an interval can differ from the Damage column above while the totals still match
- the block under the total groups the sources: your gun, your abilities (melee counts as one), and item procs split into ones that ride on bullets and ones from spirit items
- `--healing`: the same by-source view for your healing, plus a second table for the healing your anti-heal items prevented. The game never shows either per source, and the totals match the Healing and Prevented columns
- `--teams`: both teams per interval, souls and the running lead, then every objective and Rejuvenator event timestamp
- `--abilities`: ability unlocks and upgrades in the order you spent them, with the level and required souls for that unlock or cumulative AP spend
- the last hits total comes from the match screen, the per-interval columns split it into troopers and neutrals
- to read a top player's game, download it first (`deadlock download --match <id>` or `--account <id>`) and point match at those tables: `deadlock --parquet ~/.local/share/deadlock-matches/parquet-players match <id> --hero Mirage`

```
Match 12345678: Mirage, win, 2026-07-07 11:49, 32:48
Final: 9/3/20, 53,558 souls, 49,231 damage, 34,356 taken, 18,894 healing, 4,807 prevented, 151 last hits, 2 denies

  Time        Souls   /min   K/D/A   Damage   Taken  Obj dmg  Healing  Prevented  Troopers Neutrals  Denies
  0-5m        1,905    381   0/0/1    1,356     886        0      474          0         1        3       0
  5-10m       3,353    671   0/1/0    2,270   2,728        0      844        417        16        0       2
  10-15m      6,753  1,351   1/0/2    4,658   2,269        0    1,135        554        18        1       0
  15-20m      5,033  1,007   1/0/2    7,636   4,383    1,458    2,729        732        11        0       0
  20-25m      5,961  1,192   0/1/2    4,702   5,134      995    1,873        434        21        0       0
  25-30m      7,063  1,413   2/1/5   12,083   7,584       29    3,499      1,345         7        1       0
  30-35m     11,119  2,224   4/0/3    8,941   6,524    9,233    4,173        808         2        0       0
  35-40m      9,037  1,807   0/0/2    2,825   1,340        0      886        197        16        6       0
  40-41m      3,334  4,168   1/0/3    4,760   3,508    2,144    3,281        320         3        0       0
```

With `--souls`, the same intervals split by income source, matching the game's souls breakdown, then grouped into lane, roaming, combat, and objectives:

```
Match 12345678: Mirage, win, 2026-07-07 11:49, 32:48
Souls by source, 5-minute intervals

  Source                  0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-40m   40-41m    Total      %
  Troopers                 942    3,043    4,145    2,562    4,361    1,431    1,699    4,522      606   23,311    44%
  Enemy Kills                0        7      815      843       18    1,219    2,986        9    1,740    7,637    14%
  Neutral Enemies          123        0      210      267      691      396    2,655    1,653        0    5,995    11%
  Kill Assists             164        0      382      360      299    1,860      480      472      888    4,905     9%
  Objectives                 0        0      333      641      350      816    2,046        0      100    4,286     8%
  Urn                        0        0      247        0        0      728      987    1,209        0    3,171     6%
  Breakable Pickups          0      102      320      360      276      613      266    1,172        0    3,109     6%
  Team Catch-Up              0       62      301        0       15        0        0        0        0      378     1%
  Denies                    76      139        0        0        0        0        0        0        0      215     0%
  Total                  1,305    3,353    6,753    5,033    6,010    7,063   11,119    9,037    3,334   53,007

  Lane                   1,018    3,182    4,145    2,562    4,361    1,431    1,699    4,522      606   23,526    44%
  Roaming                  123      102      530      627      967    1,009    2,921    2,825        0    9,104    17%
  Combat                   164        7    1,197    1,203      317    3,079    3,466      481    2,628   12,542    24%
  Objectives                 0        0      580      641      350    1,544    3,033    1,209      100    7,457    14%
  Catch-Up                   0       62      301        0       15        0        0        0        0      378     1%

  Total is gross souls earned by source, the in-game souls breakdown. Net worth (53,558) adds starting souls and subtracts souls lost to deaths.
```

With `--damage`, the same intervals split by source instead, matching the game's damage graph:

```
Match 12345678: Mirage, win, 2026-07-07 11:49, 32:48
Damage to heroes by source, 5-minute intervals

  Source                     0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-40m   40-41m    Total      %
  Djinn's Mark                102      370    1,086      559      852    4,238    1,279    1,548    1,426   11,460    23%
  Dust Devil                    0      131      372      472      709    3,426    2,596    1,155      903    9,764    20%
  Fire Scarabs                465      721      797      402    2,138    2,215    1,200      562    1,074    9,574    19%
  Promises Kept               281      330      646      385      670    1,337      897      536      704    5,786    12%
  Mystic Shot                   0      133      631      542    1,252    1,258      497      743      400    5,456    11%
  Headhunter                    0        0      405      674      878      894      426      110      215    3,602     7%
  Promises Kept (crit)        263      271      498      306      436      535      142       32       81    2,564     5%
  Headshot Booster            245      314      223        0        0        0        0        0        0      782     2%
  Melee                         0        0        0        0      243        0        0        0        0      243     0%
  Total                     1,356    2,270    4,658    3,340    7,178   13,903    7,037    4,686    4,803   49,231

  Abilities                   567    1,222    2,255    1,433    3,942    9,879    5,075    3,265    3,403   31,041    63%
  Items (gun)                 245      447    1,259    1,216    2,130    2,152      923      853      615    9,840    20%
  Gun                         544      601    1,144      691    1,106    1,872    1,039      568      785    8,350    17%
```

With `--healing`, shows the source of all healing and anti-healing you did per item and ability:

```
Match 12345678: Mirage, win, 2026-07-07 11:49, 32:48
Healing by source, 5-minute intervals

  Source                        0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-40m   40-41m    Total      %
  Fire Scarabs                   474      777      772      386    2,357    2,175      978    1,432    1,896   11,247    60%
  Healbane                         0        0      275      550      358    1,003      908      232      550    3,876    21%
  Headhunter                       0        0       88      481      335      360      425        0      236    1,925    10%
  Spiritual Overflow               0        0        0        0        0        0      206      456      737    1,399     7%
  Kudzu Connection                 0       67        0        0        2       94        0      102        0      265     1%
  Spirit Shredder Bullets          0        0        0        0        0        0      162       20        0      182     1%
  Total                          474      844    1,135    1,417    3,052    3,632    2,679    2,242    3,419   18,894

  Abilities                      474      844      772      386    2,359    2,269      978    1,534    1,896   11,512    61%
  Items (spirit)                   0        0      275      550      358    1,003      908      232      550    3,876    21%
  Items (gun)                      0        0       88      481      335      360      793      476      973    3,506    19%

Healing prevented, 5-minute intervals

  Source               0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-40m   40-41m    Total      %
  Healbane                0      417      554      446      550    1,515      796      209      320    4,807   100%
  Total                   0      417      554      446      550    1,515      796      209      320    4,807
```

With `--teams`, shows the souls advantage and objective timeline for the same match:

```
Match 12345678: Mirage, win, 2026-07-07 11:49, 32:48
Your team: The Archmother

  Time       Your team  Enemy team      Lead
  0-5m          12,164       9,977    +2,187
  5-10m         22,824      24,827      +184
  10-15m        35,311      42,552    -7,057
  15-20m        33,046      23,438    +2,551
  20-25m        36,297      35,925    +2,923
  25-30m        44,422      39,477    +7,868
  30-35m        57,289      28,432   +36,725
  35-40m        55,434      46,367   +45,792
  40-41m        13,611       4,925   +54,478

  Objectives:
    9:53  your team destroys the enemy Guardian (green)
   10:59  enemy team destroys your Guardian (yellow)
   11:01  enemy team destroys your Guardian (blue)
   13:59  your team destroys the enemy Guardian (blue)
   14:33  enemy team destroys your Guardian (green)
   16:57  your team destroys the enemy Guardian (yellow)
   18:23  your team destroys the enemy Walker (green)
   20:42  your team destroys the enemy Walker (yellow)
   21:11  enemy team destroys your Walker (blue)
   23:18  your team kills the mid boss, enemy team steals the Rejuvenator
   26:20  your team destroys the enemy Walker (blue)
   27:53  enemy team destroys your Walker (yellow)
   32:25  your team kills the mid boss and claims the Rejuvenator
   33:14  your team destroys the enemy Base Guardians (blue)
   33:42  your team destroys the enemy Shrine
   34:06  your team destroys the enemy Shrine
   34:19  your team destroys the enemy Base Guardians (green)
   34:23  your team destroys the enemy Patron
   39:01  your team kills the mid boss and claims the Rejuvenator
   40:25  your team destroys the enemy Base Guardians (yellow)
   40:47  your team destroys the enemy Weakened Patron
```

### `uv run deadlock winrate`

- wins and losses per day, with your MVP and Key Player awards
- `--by week` or `--by month` rolls the table into weekly or monthly rows, weeks start on Monday
- `--hero Mirage` filters to one hero and also adds the public win rate from `deadlock-api.com` under the table, scoped by `--min-rating` (Eternus+ by default)

```
  Day           Games    W    L   Win rate   MVP   Key   Net wins   Cumulative net
  2026-06-30        5    4    1      80.0%     0     2         +3               +2
  2026-07-01        5    4    1      80.0%     0     0         +3               +5
  2026-07-02        4    3    1      75.0%     0     1         +2               +7
  2026-07-03        4    4    0     100.0%     1     0         +4              +11
  2026-07-04        5    4    1      80.0%     0     1         +3              +14

Overall: 32 games, 24-8, 75.0% win rate, +16 net wins, 1 MVP, 4 Key Player.
```

### `uv run deadlock deaths --hero Mirage`

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

These commands read the cached hero, ability, and item data instead of your matches, so they need no games and work offline after the assets have been downloaded.

### `uv run deadlock hero Pocket`

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

### `uv run deadlock hero Seven --level 30`

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

### `uv run deadlock ability "Fire Scarabs" --souls 50000`

- base numbers, spirit scaling, and the values each upgrade tier changes
- `deadlock hero <name>` lists a hero's ability names to feed this command
- `--hero` picks whose when the name is on several heroes
- `--souls` (or `--level`) updates the values using the scaling the hero has at that point
  - in the example below, the ability is level 36 at 48,600 souls, so the scaling is based on 38.5 spirit power that Mirage has at that point (no items)

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

### `uv run deadlock item "Mercurial Magnum"`

- the shop card for an item, straight from the asset data
- innate stats first, then each passive or active section with the cooldown and description
- adding `--hero` turns it into a full report of the item on that hero, covered with the top player commands below

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

## Top players and public stats

Everything in this section uses [deadlock-api](https://api.deadlock-api.com). Top players come from the per-hero leaderboards, so Rank in these reports is their rank on that hero across regions. The overall ranked ladder is not used here since it says nothing about a specific hero.

`--players` and `--games` set how many top players and how many recent ranked games per player are pulled (6 players with 10 games each by default currently).

### Following specific players

The commands below default to the current leaderboard top players, but the leaderboard shifts and a player you care about can drop off it. To follow specific people, go from a name to an account ID to a watchlist:

1. **Find the top players for your hero.** `deadlock leaderboard --hero Mirage` lists the current top players with their account IDs. Add `--matches` to also print each one's recent match ids.

   ```
   Mirage leaderboard:
     someplayer           111222333    rank 1    Europe
         12345678  2026-07-05  win   14/2/23
     anothermain          444555666    rank 24   SAmerica
   ```

2. **Get an account ID.** For someone off the leaderboard, the ID is exact in any match they played (`deadlock match <id> --hero <theirs>` prints every player), or convert their Steam profile URL from steam64 to steam32. Searching by name is unreliable, since the only name search is over current Steam persona names, which change often.

3. **Optionally pin them to a watchlist.** Add the ID under `[players.<Hero>]` in `config.toml` so `deadlock download` always pulls them, even when they are off the ladder. The name is just a label for reports.

   ```toml
   [players.Mirage]
   someplayer = 111222333
   ```

4. **Download and analyze.** `deadlock download --hero Mirage` pulls the top players plus everyone on the watchlist. To skip the watchlist and grab someone one-off, use `--account <id>`, or fetch a single game with `--match <id>`. Then any command works on their games by pointing `--parquet` at the downloaded tables, for example `deadlock --parquet ~/.local/share/deadlock-matches/parquet-players match <id> --hero Mirage`.

### `uv run deadlock meta --hero Mirage --by rating`

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

### `uv run deadlock builds --hero Mirage`

- items top players buy (in wins vs losses)
- `--min-percent 30` hides items bought in fewer than 30% of the builds
- an expensive late item with a big win/loss gap usually just means the winner got rich enough to buy it

```
Top 6 Mirage players:

  Player              Rank  Region    Record
  someplayer             1  Europe    8W 2L
  anothermain           14  SAmerica  6W 4L
  thirdmain             45  Europe    7W 3L

Shared core across 35 winning builds:

  Item                      Win %  Loss %  Median buy   Slot
  Dispel Magic                91%     96%         14m   vitality T3
  Recharging Rush             83%     64%         10m   weapon T2
  Ricochet                    83%     56%         27m   weapon T4
  Toxic Bullets               80%     60%         19m   weapon T3
  Escalating Exposure         74%     44%         24m   spirit T4
  Healbane                    51%     36%          8m   vitality T2
```

### `uv run deadlock compare --hero Mirage`

- your stats vs top players minute by minute
- `--stat farm` (default): souls from troopers, neutrals, boxes, treasure, and denies. Kill and assist gold is excluded, and the report ends with your kill and assist souls at 20 minutes so that figure stays visible
- `--stat combat`, `objectives`, `catch_up`, `other` (Trophy Collector and similar item income), `souls` (net worth), `soul_sources` (every income source as one gap table), or any raw snapshot field: `creep_kills`, `denies`, `player_damage`

```
You (111222333, 50 games) vs top Mirage players: farm

  Min       You (n)        Top (n)       Gap   You/min  Top/min
    3     1,138 (50)     1,274 (60)      -137       379       425
    6     2,754 (50)     3,019 (60)      -265       539       582
    9     4,608 (50)     5,118 (59)      -510       618       700
   12     6,720 (50)     7,441 (59)      -721       704       774
   15     9,116 (50)     9,945 (59)      -830       798       835
   20    12,992 (50)    14,684 (59)    -1,692       775       948
   25    17,920 (50)    19,340 (55)    -1,420       986       931
```

### `uv run deadlock leaderboard --hero Mirage`

- the current top players of a hero from the per-hero leaderboard, with their account IDs
- `--matches` (optionally `--matches 10`) lists each one's recent ranked match ids, win or loss, so you can pick a game to pull
- config `[players.<Hero>]` entries show up too, marked `config`

```
Mirage leaderboard:
  someplayer           111222333    rank 1    Europe
      12345678  2026-07-05  win   14/2/23
      12345670  2026-07-05  win   19/5/20
  anothermain          444555666    rank 24   SAmerica
      12340013  2026-07-03  win   13/7/17
```

### `uv run deadlock download --hero Mirage`

- downloads recent matches from top players and your selected `[players]` in config into their own parquet tables (see below)
- `--account 111222333` pulls a specific player's recent games instead of the leaderboard top players (still needs `--hero`); comma-separate for several
- `--match 12345678` fetches one match by ID, no `--hero` needed: it stores every player in the match, so `match --hero <anyone>` then works on it; comma-separate for several
- re-running adds new matches without downloading old ones again
- `item` and `movement` use these downloaded games for their top player numbers

### `uv run deadlock item "Escalating Exposure" --hero Mirage`

- stats for the item on one hero, your games vs top players
- meta stats count Eternus+ lobbies by default and `--min-rating all` removes that filter
- `--since 2026-06-30` limits your games and the meta stats to matches on or after a date, useful when a patch changed the item
- `--top 15` shows more rows in the bought together table
- if you ran `deadlock download`, it also shows damage per minute owned for top players
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

Top Mirage players: 219 damage per minute owned across 78 builds, 8.5% of their hero damage (deadlock-api.com)

Results (Eternus+ lobbies):
  win rate 56.8% over 5,292 games, usually bought around 26m
  items at the same price average 58.2%, so it sits 1.5 points below them

Bought together (win rate of games with both, vs the item alone):

  Item                     Win rate Vs alone    Games
  Spiritual Overflow          63.5%     +6.7    1,167
  Superior Duration           62.4%     +5.6    1,350
  Transcendent Cooldown       62.3%     +5.5    1,638
```

### `uv run deadlock movement --hero Mirage`

- movement profile on one hero: how much you slide, dash, and stay airborne, how far you move, and how often you stand still (small radius)
- needs the `movement` table, so delete it from `exclude` in `config.toml` first
- the Top column appears when `deadlock download` ran with movement enabled and is from the top players on the leaderboard

```
Mirage movement: you (50 games) vs top players (114 games)

  Metric                        You      Top      Gap
  slide %                       3.9      8.3     +4.4
  ground dashes /min            1.7      2.4     +0.7
  air dashes /min               0.2      0.8     +0.7
  in air %                      8.1     21.2    +13.1
  zipline %                     6.7      8.5     +1.9
  fighting players %           24.3     26.7     +2.4
  distance /min            15,288.9 16,932.3 +1,643.4
  stationary %                  9.9      7.1     -2.8
```

## Maintenance

### `uv run deadlock assets`

- redownloads the hero, item, and ability data after a patch

### `uv run deadlock export`

- rebuilds the parquet tables (normally automatic)

### `uv run deadlock schema damage`

- column descriptions for the parquet table ("damage" table in this example)
- add `--sample` after a table name to print the first 5 rows from that parquet table, or `--sample 10` for another count

## The parquet tables

The raw match data is deeply nested protobuf, so every match has to be processed one at a time. The export flattens the reusable parts into several parquet files. Any question across your whole match history can be answered with polars, and the same files work with [DuckDB](https://duckdb.org), [pandas](https://pandas.pydata.org), or anything else that reads parquet.

The tables are stored in `~/.local/share/deadlock-matches/parquet/` (`%LOCALAPPDATA%\deadlock-matches\parquet` on Windows) and rebuild automatically when new matches show up. `deadlock schema [table]` prints the data dictionary with the data type and description per column. `deadlock schema players --sample` also prints a small local preview, which is useful for checking join keys and real values without opening a notebook.

- `matches`: one row per match
- `players`: one row per player per match, with `hero`, `won`, and `lane` (the starting lane color)
- `stats`: cumulative stat snapshots taken every minute
- `soul_sources`: souls per income source per snapshot
- `item_events`: item purchases, with names, prices, and tiers merged in from the cached API data. Prices reflect the patch each match was played on
- `damage`: damage, healing, and mitigation per source and target, with the names you see in game like Dust Devil or "Promises Kept (crit)" for headshots. The totals from the match screen and the individual source rows have different `category` values, so filter to one or the other
- `damage_sources`: the same sources over time, cumulative like the in-game damage graph. Summed over targets, split into hero targets and everything else
- `mid_boss`: one row per midboss kill, with when it died, which team killed it, and which team claimed the Rejuvenator
- `movement`: the position of every player, health percent, and movement state (sliding, dashing, ziplining, in combat or not) for every second of the match. The starter config excludes it because it is larger than every other table combined. Delete it from `exclude` if you want to answer questions like these:
  - was I alone when I died?
  - was I on the other side of the map while my team was fighting?
  - do top players slide and air dash more than I do on the same hero?
- `deaths`: one row per death with the time, position, killer, and respawn timer. Joined to `movement`, this answers things like "was I alone when I died" or "how many enemies killed me"

The tables do not cover everything Valve stores yet. The full structure is `CMsgMatchMetaDataContents` in [`protos/citadel_gcmessages_common.proto`](protos/citadel_gcmessages_common.proto) and can be read as plain text. This is a work in progress, and new columns and tables get added as more of that data turns out to be interesting to query.

`deadlock download --hero` builds the same tables for matches from *other* players in the `parquet-players/` directory. This includes top players from the leaderboard, anyone selected under `players` in config, and any account or match id you pass to `--account` / `--match`. The layout is identical, so every query works on their games. An extra `downloads` table records which player each match came from, their rank at the time, and when it was retrieved; a match pulled by id has no player, so those columns are null. Re-running adds new matches without downloading old ones again.

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
- `source_intervals(games, stat="damage")` is similar to `deadlock match --damage`, but tracks data from multiple matches at once in 5-minute intervals
- `team_damage_ranks()` ranks every player by hero damage within their team, with `top_team_damage` for "did they top the chart?"
- `ability_upgrades()` is your ability unlock and upgrade order, with the level and required souls for each unlock or cumulative AP spend
- `item_buys("Echo Shard")` is your purchases of one item, with the buy order within each match
- `item_value("Echo Shard")` is damage per minute owned and the percent of hero damage for one item, works on the download tables too
- `daily_record()` is the frame behind `deadlock winrate`
- `my_deaths()` is one row per death in your games, with hero and result joined in
- `death_context()` adds how many allies and enemies were within 2000 units when you died (needs the movement table)
- `movement_profile()` is the per-match frame behind `deadlock movement`
- `hero_scaling()` is base health and spirit power per hero per level

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
    pl.scan_parquet(f"{pq}/item_events.parquet")
    .filter(pl.col("account_id") == me, pl.col("item").is_in(antiheal))
    .join(pl.scan_parquet(f"{pq}/matches.parquet"), on="match_id")
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
    pl.scan_parquet(f"{pq}/damage.parquet")
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
