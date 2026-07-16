# Commands

Every deadlock-matches command with a real example of what it prints. The [README](../README.md) shows a few of these. This is the complete set, grouped by what each command reads.

For the table schemas behind these reports, see [data.md](data.md).

*Note - hero, item, and ability examples can drift when Deadlock patches. Asset data from 2026-01-01 onward is included with the package. Current cards use the latest snapshot, and `--as-of` / `--changes` read that history.*

These commands answer common data questions after setup: syncing matches, inspecting games, comparing tracked players, and reading game assets. Adding a command for every possible question is not feasible, so please see [writing your own queries](../README.md#writing-your-own-queries) if something is missing. LLM agent support is optional and documented separately.

The sections below group the commands by what they read. **Match analysis** reads your local match archive and parquet tables. **Heroes, abilities, and items** reads the included asset data. **Tracked players and public stats** covers the comparisons, which read games `deadlock download` fetched from [deadlock-api](https://api.deadlock-api.com), plus the public meta numbers. **Setup and maintenance** keeps the archive, config, and asset data current.

A few flags repeat across commands:

- `--help` is by far the most important flag since it describes all the options
  - `deadlock --help` prints the full help
  - `deadlock <command> --help` prints the help for that command
- `--account` filters your games to one or more of your accounts, by ID or a name from `config.toml`, comma-separated for several (`--account main` or `--account "main, alt1"`). Every command that reads your games takes it and defaults to all accounts in the config
  - a tracked player name (or any account ID you downloaded games from) reads their games instead: `deadlock damage --hero Mirage --account tracked2`. Works for `history`, `match`, and the damage/healing/souls/combat/movement commands
- `--days N` filters your last N days of games (`--days 7`)
- `--since YYYY-MM-DD` filters for data since a date (`--since 2026-07-01`)
- `--hero Mirage` filters a report to one hero (required for the tracked player commands since players are tracked per hero). Quote names with spaces: `--hero "Mo & Krill"`, though capitals and punctuation are optional (`--hero "mo krill"` works too)
- `--min-rating Oracle` limits public stats to lobbies at that average skill rating or higher. `winrate` and `item` default to Eternus, `meta` counts every rating, and `all` disables the filter

## Match analysis

### Match history

```
deadlock history
```

- one line per game of yours with the match ID, newest last
- shows your last 10 games, `--days` and `--since` reach further back
- the ID feeds the other commands: `match 12345678`, `download --match 12345678`
- matches you only viewed in game stay hidden unless you name their players with `--account`

```
  Day         Time   Account    Hero           Result  K/D/A        Souls   Damage  Match ID
  2026-07-03  20:28  main       Mirage         win     10/5/15     58,210   57,784  12345678
              21:22  main       Mirage         loss    9/12/11     43,912   38,102  12345731
              22:37  alt1       Vindicta       win     11/2/9      51,004   62,220  12345802
```

### One match

```
deadlock match
```

- the final scoreboard of a single match and the per-5-minute interval data for your character by default
- `deadlock match 12345678` reads THAT match from your tables, `deadlock match` your most recent one. `--ago 1` steps back to the game before that (`--ago 2` two back, and so on) without needing the ID. `--hero Wraith` follows another player from the match instead (your games keep all 12 players), and `--interval 10` changes the bucket size
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

- the in-game souls graph as a table, souls by source per interval, then grouped into waves (troopers and denies), roaming (jungle and breakables), combat, objectives (bosses and the Rift & Urn), and catch-up

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

  Waves                  1,150    2,831    2,863    2,683    2,500    4,606    3,075      272   19,980    42%
  Roaming                    0      427    1,769      479    1,852    1,435    1,518        0    7,480    16%
  Combat                    14      347    2,763      736    1,829    3,146    3,391    1,890   14,116    30%
  Objectives                 0        0      872        0      819    1,500    1,424        0    4,615    10%
  Catch-Up                   0      142      175        0      307      181       56        0      861     2%

  Total is gross souls earned by source, the in-game souls breakdown. Net worth (47,025) adds starting souls and subtracts souls lost to deaths.
```

#### `--damage`: damage by source and by enemy

- the in-game damage graph, damage to heroes by source, then grouped into your gun, your abilities (melee counts as one), and item procs split into gun and spirit items, then the damage dealt to and taken from each enemy. The source data samples about every 3 minutes, so an interval can differ from the Damage column in the main view while the totals still match

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
  Items (bullet procs)        175      523    1,316      106    1,114    1,375    1,106      334    6,049    15%
  Gun                         363      785    1,360      258      988      769      403      858    5,784    14%
  Items (standalone)            0        0        0        0        0      660    1,884    2,743    5,287    13%

Damage dealt to enemy, 5-minute intervals

  Enemy                      0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-37m    Total      %
  Ivy                         863    1,494    1,027      208    3,096      931    1,617      297    9,533    24%
  Warden                        0        0        0      741      797    4,635    1,273    1,103    8,549    21%
  Bebop                         0        0    2,207        0    1,105    1,978        0    3,197    8,487    21%
  Shiv                          0        0      212      457    1,067      293    2,652       96    4,777    12%
  Pocket                       14    1,056      343      398        0      832    1,140      682    4,465    11%
  Vindicta                      0        0      693        0      288        5    1,916    1,432    4,334    11%
  Total                       877    2,550    4,482    1,804    6,353    8,674    8,598    6,807   40,145

Damage taken by enemy, 5-minute intervals

  Enemy                      0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-37m    Total      %
  Vindicta                      0        0    2,017      146      601    1,911      942    3,017    8,634    25%
  Pocket                      390    1,725    1,381      903    1,656    1,155        0      819    8,029    24%
  Shiv                          0        0       13      692    1,038    1,075    3,332        0    6,150    18%
  Warden                        0        0        0        0      543    3,094    1,283        0    4,920    14%
  Ivy                         246      181       36      721      439    1,503      187      413    3,726    11%
  Bebop                         0        0      581       67      108      982        0      868    2,606     8%
  Total                       636    1,906    4,028    2,529    4,385    9,720    5,744    5,117   34,065
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
  Items (standalone)      0        0      329      622      548    1,211    1,228      800    4,738    36%
  Items (bullet procs)    0      241      255       67      258      444      292      241    1,798    14%

Healing prevented, 5-minute intervals

  Source               0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-37m    Total      %
  Healbane                0        0      310       73      422      694      317      312    2,128   100%
  Total                   0        0      310       73      422      694      317      312    2,128
```

#### `--teams`: the soul lead and objectives

- both teams per interval with the running lead, then every objective and Rejuvenator as it fell, mixed in with each Unstable Rift win (both teams, the souls each player got, noted when the winning team was behind) and each Soul Urn delivery (with the runner). A blank line splits the timeline at each 10 minute mark. Matches from before the June 30 objective rework carry no rift or urn line, the old modes worked differently

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

- one section per lane with your lane first, a Team and Enemy summary row with the two laners under each side, a signed Net row, then the lane's kills and guardian falls in time order, each event signed + or - from your side. Stat columns read the last snapshot inside the window (9 minutes by default, the samples land every 3 minutes), kills and guardians use exact event times. `--laning 12` widens the window

```
Laning phase through 9:00

Yellow (your lane)
  Lane               Souls  Kills  Deaths   Damage    Taken  Obj damage  Healing  Prevented  Last hits  Denies
  Team              12,340      2       0    7,218    6,721       1,270    4,854          0         70       1
   * Mirage          5,511      0       0    3,427    2,542         320    1,213          0         25       0
     Mo & Krill      6,829      2       0    3,791    4,179         950    3,641          0         45       1
  Enemy             10,665      0       2    6,985    7,910         480    1,179          0         49       1
     Pocket          5,522      0       1    5,274    3,270         480       28          0         23       1
     Ivy             5,143      0       1    1,711    4,640           0    1,151          0         26       0
  Net               +1,675     +2      -2     +233   -1,189        +790   +3,675         +0        +21      +0

  3:07    + Mo & Krill kills Ivy
  4:20    + Mo & Krill kills Pocket
  both guardians up

Blue
  Lane               Souls  Kills  Deaths   Damage    Taken  Obj damage  Healing  Prevented  Last hits  Denies
  Team              14,669      6       2   10,641    7,972       2,145      561          0         55      11
     Wraith          8,344      5       1    4,878    3,438       1,624      466          0         30       9
     Drifter         6,325      1       1    5,763    4,534         521       95          0         25       2
  Enemy             11,274      2       6    7,708    9,949         743      622          0         55      17
     Shiv            5,853      1       3    3,748    5,396         743      622          0         21       0
     Warden          5,421      1       3    3,960    4,553           0        0          0         34      17
  Net               +3,395     +4      -4   +2,933   -1,977      +1,402      -61         +0         +0      -6

  5:00    - Warden kills Drifter
  5:02    + Wraith kills Warden
  5:25    + Wraith kills Shiv
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

#### `--combat`: shooting accuracy against heroes, range, and other hidden metrics

- the fight stats the game tracks but never shows. Every player in the match ranked by aim against heroes with the gun damage their aim produced, the fire the enemy team put at you (their whole team combined, no per-enemy split exists) with the all-target accuracy printed for contrast, damage split by the range it was dealt and taken at, a one-line parry count (the full lobby melee and parry table lives in `--melee`), comeback souls with the Unstable Rift called out, and how many souls sat unspent in your pocket. Heroes with their own counters (Celeste stack uptime, Apollo damage prevented) get a section when you play them

```
  Aim vs heroes
  Hero          Side     Shots  Hit rate  HS rate  Gun damage  Headshot damage
  Celeste       enemy      387     26.4%    23.5%       3,339            1,416
  The Doorman   ally       474     28.9%    19.0%       4,663            1,699
  Viscous       enemy      321     20.9%    17.9%       1,696              100
  Drifter       enemy    1,688     17.8%    16.3%       4,624              924
  Infernus      ally     4,289     20.0%    15.1%       5,109            1,669
  Yamato        ally       841     20.8%    14.3%       6,974              293
  Pocket        enemy    2,097     27.7%    14.3%       3,178            1,039
  Mirage *      ally       951     38.5%    13.9%       9,523            2,759
  Venator       ally     2,336     23.3%    13.1%      11,422            7,362
  Victor        enemy    1,817     17.3%    11.1%       8,027            1,525
  Wraith        enemy    3,892     20.5%     7.5%       6,949              771
  Ivy           ally     2,371     20.8%     7.1%       3,257              474

  Rates count heroes only, troopers and other NPCs left out.
  Gun and headshot damage are the two bullet series from the damage graph.

  Enemy team at you: 2,599 shots, 527 (20%) hits, 69 (13%) headshots
  Lucky shots: 1
  Accuracy with troopers and everything else included: 69%

  Damage by range
                  Gun dealt   Ability dealt       Gun taken   Ability taken
  0-10m         3,790 (29%)     6,363 (27%)     2,794 (35%)     9,739 (40%)
  10-20m        4,925 (38%)     5,396 (23%)     1,767 (22%)     6,886 (28%)
  20-30m        3,048 (23%)     4,273 (18%)     2,303 (29%)     4,062 (17%)
  30-40m           960 (7%)     2,457 (10%)       941 (12%)      1,222 (5%)
  40-50m           258 (2%)      1,396 (6%)        156 (2%)        339 (1%)
  50-75m            31 (0%)     2,959 (13%)         30 (0%)        919 (4%)
  75-100m                 -        199 (1%)               -               -
  100m+                   -        595 (3%)               -      1,013 (4%)

  Falloff on your hits: 7% none, 90% partial, 3% max
  Falloff on hits taken: 17% none, 62% partial, 20% max

  Parries 0 landed, 3 missed  (--melee for the lobby table)

  Souls
  Comeback souls: 154
  Souls held unspent on average: 2,291
  Ability points held unspent on average: 1.3
```

#### `--melee`: melee damage between heroes and parries

- every player ranked by the melee they dealt and took between heroes, with parries landed and missed, then the melee you took per enemy and any melee item buys. Melee is the bare light and heavy swing the game shows, ability melees land under their own damage source. The parry counts here are the same ones `--combat` reports in a single line

```
  Melee
  Hero          Side    Melee dealt  Melee taken  Parried  Missed parry
  Venator       ally          6,420          141        -             5
  Yamato        ally          5,043        1,152        5             8
  The Doorman   ally          1,833          226        1             1
  Victor        enemy         1,477        2,859        2             4
  Celeste       enemy           683        2,693        -             -
  Viscous       enemy           459        1,903        1             2
  Drifter       enemy           296        1,743        1             2
  Ivy           ally            143            -        -             -
  Mirage *      ally             58          792        -             3
  Pocket        enemy             -        2,607        -             1
  Infernus      ally              -          604        -             2
  Wraith        enemy             -        1,692        -             1

  Melee taken by you
    Victor        636
    Celeste        85
    Drifter        71
```

#### `--movement`: dashes, slides, and time in the air

- how everyone moved through the match, from the per minute `movement_intervals` table, which always builds even with `movement` in the config exclude list. The Movement table sums the whole match for every player (allies first, most meters first), then your own game splits per interval. Meters covered and the pace while moving, then how much of the alive time went to sliding, being in the air, riding ziplines, and fighting players, plus how much of the moving time was spent standing still and the dash counts. An interval you spent fully dead prints `-` for the percents

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

#### `--deaths`: deaths per enemy and each death event

- how many times each enemy killed you per interval, then each death with who killed you, how long the fight lasted, how far away the killer stood, and your respawn timer. A death to troopers or an objective shows `not a player`. The damage each enemy dealt to you lives in `--damage`

```
Deaths per enemy, 5-minute intervals

  Enemy                0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-37m    Total
  Bebop                   -        -        -        1        -        -        -        -        1
  Pocket                  -        -        -        -        1        -        -        -        1
  Vindicta                -        -        -        -        -        -        1        -        1
  Total                   -        -        -        1        1        -        1        -        3

  Time    Killed by      Killed in  Distance  Respawn
  16:28   Bebop              15.8s        2m      29s
  21:54   Pocket             12.2s       17m      42s
  33:35   Vindicta           10.0s       32m      90s
```

#### `--kills`: kills per enemy and each kill event

- your kills counted per enemy per interval, then the log from the killer side, each kill with the victim, the distance, and the respawn it cost them

```
Kills per enemy, 5-minute intervals

  Enemy                0-5m    5-10m   10-15m   15-20m   20-25m   25-30m   30-35m   35-37m    Total
  Bebop                   -        -        2        -        -        -        -        1        3
  Ivy                     -        -        1        -        -        -        -        1        2
  Vindicta                -        -        1        -        -        -        1        -        2
  Warden                  -        -        -        1        -        1        -        -        2
  Pocket                  -        -        -        1        -        -        -        -        1
  Shiv                    -        -        -        -        1        -        -        -        1
  Total                   -        -        4        2        1        1        1        2       11

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
deadlock winrate
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
deadlock laning --account main --hero Mirage
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
  behind 3k+                    3     3     0     100.0%
  behind 1k-3k                 12     7     5      58.3%
  even within 1k               22    14     8      63.6%
  ahead 1k-3k                  12     9     3      75.0%
  ahead 3k+                     3     1     2      33.3%

  Lane result               Games     W     L   Win rate
  lost lane                    31    19    12      61.3%
  won lane                     21    15     6      71.4%

Your deaths by 9:00:

  Deaths                    Games     W     L   Win rate
  0                            19    11     8      57.9%
  1                            22    16     6      72.7%
  2-3                          11     7     4      63.6%

Worst teammate deaths by 9:00, you excluded (2 games with an ally abandon left out):

  Deaths                    Games     W     L   Win rate
  0-1                           3     2     1      66.7%
  2-3                          38    28    10      73.7%
  4+                            9     4     5      44.4%

Lane result and a feeding teammate (4+ deaths by 9:00):

                            Games     W     L   Win rate
  lost lane, ally fed           6     3     3      50.0%
  lost lane, no feeder         24    16     8      66.7%
  won lane, ally fed            3     1     2      33.3%
  won lane, no feeder          17    14     3      82.4%

Overall: 52 games, 34-18, 65.4% win rate.
```

### Deaths

```
deadlock deaths --hero Mirage
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

### Damage by source across your games

```
deadlock damage --hero Mirage
```

- every game of a hero rolled into one table: a row per gun, ability, or item source with the games it appeared in, its total, per minute, and share of your hero damage
- the delivery block on top splits the total into gun, abilities, and item procs (bullet procs fire when your shot lands, standalone items bring their own trigger). The grouping follows what carries the damage, not the shop color — Siphon Bullets is a vitality item but procs on hit, so it counts as a bullet proc
- Mercurial Magnum sits under standalone: its on-cast proc has its own trigger, and while the until-next-reload bonus rides on bullets, the game reports both under one line, so it groups by its primary mechanic
- `/game` divides a delivery row by every listed game and a source row by the games it appeared in, so an item bought in a handful of games is not averaged over the whole window
- `/min` divides a delivery row by the combined length of every listed game and a source row by the minutes of its own games. `/min owned` divides item rows by the minutes the item was owned instead, so a late buy is not diluted by the minutes before it existed
- `/1k souls` divides item rows by every 1,000 souls the item actually cost, using shop prices from the patch the game was on. Building through a component does not count those souls twice
- a per game table follows with the delivery shares per game, so a build shift shows up as drift. It always prints the last 10 games of the window, `--games N` prints more
- the archive counterpart of `match --damage`, which shows the same sources for one game in intervals
- `--days`, `--since`, and `--account` filter like `winrate`

```
Damage to heroes by source, 47 games of Mirage

  Delivery                    Total    /game     /min      %
  Abilities                 840,309   17,879    525.2    60%
  Gun                       350,102    7,449    218.8    25%
  Items (bullet procs)      150,240    3,197     93.9    11%
  Items (standalone)         60,177    1,280     37.6     4%
  Total                   1,400,828   29,805    875.5

  Games  Source               Delivery               Total    /game     /min  /min owned  /1k souls      %
     47  Fire Scarabs         Abilities            401,220    8,537    250.8           -          -  28.6%
     47  Promises Kept        Gun                  270,466    5,755    169.0           -          -  19.3%
     47  Djinn's Mark         Abilities            260,118    5,534    162.6           -          -  18.6%
     46  Dust Devil           Abilities            150,377    3,269     96.0           -          -  10.7%
     21  Toxic Bullets        Items (bullet procs)  60,242    2,869     84.3       148.3      956.2   4.3%
     33  Escalating Exposure  Items (standalone)    55,101    1,670     49.0       155.6      269.3   3.9%

  /game divides a delivery row by every game and a source row by the games it appeared in.
  /min divides the same way with the minutes of those games.
  /min owned divides an item row by the minutes the item was owned instead.
  /1k souls divides an item row by every 1,000 souls it actually cost, so an upgrade does not recount the components you already bought.

Per game, the last 10 of 47 (--games N lists more), newest last

  Account    Day        Result  K/D/A      Gun %  Abil %  Items %    Damage  Match ID
  main       2026-07-02 win     10/5/15     24.1    61.3     14.6    41,102  12345678
  main       2026-07-03 loss    9/12/11     19.5    69.8     10.7    28,410  12345731
  main       2026-07-03 win     7/3/16      22.8    55.1     22.1    35,006  12345802
```

### Healing by source across your games

```
deadlock healing --hero Mirage
```

- the same shape as `damage` for your healing: a row per ability or item source with the games it appeared in, its total, per minute, and share of your healing
- the totals match the scoreboard healing number exactly, item lifesteal and regen included
- a second table lists the healing your anti-heal denied the enemy, source by source, with its own share column; it only prints when at least one game has any
- the per game table swaps the gun share for `Self %`, the share of your healing that landed on you instead of a teammate, so a support game reads differently from a sustain build, and adds the prevented total per game
- `--days`, `--since`, `--account`, and `--games` filter like `damage`

```
Healing by source, 47 games of Mirage

  Delivery                    Total    /game     /min      %
  Abilities                 310,376    6,604    187.6    55%
  Items (standalone)        194,458    4,137    117.5    34%
  Items (bullet procs)       61,068    1,299     36.9    11%
  Total                     565,902   12,040    342.0

  Games  Source               Delivery               Total    /game     /min  /min owned  /1k souls      %
     47  Fire Scarabs         Abilities            308,255    6,559    186.3           -          -  54.5%
     43  Healbane             Items (standalone)    76,078    1,769     50.3        67.8    1,415.4  13.4%
     26  Mystic Regeneration  Items (standalone)    52,931    2,036     57.8        71.0    1,628.6   9.4%
     29  Dispel Magic         Items (standalone)    37,977    1,310     37.2        84.6      436.5   6.7%
     17  Headhunter           Items (bullet procs)  27,452    1,615     45.9        61.8      504.6   4.9%
     14  Siphon Bullets       Items (bullet procs)  20,421    1,459     41.4       374.4      235.3   3.6%

Healing prevented:

  Games  Source               Delivery               Total    /game     /min  /min owned  /1k souls      %
     43  Healbane             Items (standalone)    64,204    1,493     42.4        57.2    1,194.5  91.7%
     31  Toxic Bullets        Items (bullet procs)   4,761      154      4.4        11.2       62.7   6.8%
     12  Inhibitor            Items (standalone)     1,033       86      2.4        14.9       16.4   1.5%

  /game divides a delivery row by every game and a source row by the games it appeared in.
  /min divides the same way with the minutes of those games.
  /min owned divides an item row by the minutes the item was owned instead.
  /1k souls divides an item row by every 1,000 souls it actually cost, so an upgrade does not recount the components you already bought.

Per game, the last 10 of 47 (--games N lists more), newest last

  Account    Day        Result  K/D/A       Abil %  Items %  Self %   Healing  Prevented  Match ID
  main       2026-07-02 win     10/5/15       40.4     59.6   100.0     8,044      1,317  12345678
  main       2026-07-03 loss    9/12/11       59.7     40.3    91.2    15,206      3,082  12345731
  main       2026-07-03 win     7/3/16        50.0     50.0   100.0    16,558      2,074  12345802
```

### Souls by source across your games

```
deadlock souls --hero Mirage
```

- gross souls by income source across every game of a hero, grouped the same way as `match --souls`: waves (troopers and denies), roaming (jungle and breakables), combat, objectives, and catch-up
- the per game table shows the four group shares plus souls per minute, so a farm-heavy stretch or a fight-heavy stretch reads as drift
- `--days`, `--since`, `--account`, and `--games` filter like `damage`
- `--milestones` flips the view around: the median minute each net-worth mark is first reached, stepping by `--step` souls (default 1600), with the minute interpolated between the 5-minute snapshots

```
deadlock souls --hero Mirage --milestones

  Minutes to reach a net worth, median across games
  You: main, 64 Mirage games

    Souls      You  games
     1600      2.8     64
     3200      5.6     64
     4800      7.7     63
     6400      9.6     63
```

```
Souls by source, 47 games of Mirage

  Group                     Total    /game     /min      %
  Waves                   902,542   19,203    520.5    46%
  Combat                  366,689    7,802    212.1    19%
  Roaming                 352,913    7,509    200.0    18%
  Objectives              290,655    6,184    163.2    14%
  Catch-Up                 74,118    1,577     42.8     4%
  Total                 1,988,075   42,300  1,139.2

  Games  Source             Group              Souls    /game     /min      %
     47  Troopers           Waves            894,199   19,025    516.2  45.3%
     47  Enemy Kills        Combat           241,233    5,133    138.1  12.1%
     47  Neutral Enemies    Roaming          203,151    4,322    118.7  10.4%
     47  Objectives         Objectives       156,574    3,331     89.9   7.9%
     47  Breakable Pickups  Roaming          139,762    2,974     81.3   7.1%
     46  Kill Assists       Combat           125,456    2,727     73.5   6.5%
     43  Rift & Urn         Objectives       124,081    2,886     77.7   6.4%
     40  Team Catch-Up      Catch-Up          74,118    1,853     49.9   3.8%
     44  Denies             Waves              7,343      167      4.5   0.4%

  /game divides a group row by every game and a source row by the games it appeared in.
  /min divides the same way with the minutes of those games.

Per game, the last 10 of 47 (--games N lists more), newest last

  Account    Day        Result  K/D/A      Waves %  Roam %  Combat %  Obj %     Souls   /min  Match ID
  main       2026-07-02 win     10/5/15       36.2    23.8      16.1   18.0    27,770    984  12345678
  main       2026-07-03 loss    9/12/11       50.9    17.2      22.8    8.5    48,375  1,173  12345731
  main       2026-07-03 win     7/3/16        34.2    30.2      24.4   11.1    55,762  1,226  12345802
```

### Combat counters across your games

```
deadlock combat --hero Mirage
```

- the hidden fight counters summed across every game of a hero, the archive counterpart of `match --combat`
- aim totals in both directions: your fire at enemy heroes and the whole enemy team's fire at you, with hit and headshot rates. The familiar all-target accuracy prints under the tables so the vs-hero rate never reads as a bug
- damage by range band with the falloff splits and parries follow as whole-window sums. Comeback souls and unspent balances stay in `match --combat`, where a single game gives them meaning
- heroes with stack counters get their uptime tables at the end, time summed across every game
- the per game table shows the vs-hero hit and headshot rates with shot volume and parries, so an aim slump reads as drift
- `--days`, `--since`, `--account`, and `--games` filter like `damage`

```
Combat stats, 47 games of Mirage

  Aim vs heroes                    Total    /game    Rate
  Shots                           35,251    1,006        
  Hits                            15,266      436   43.3%
  Headshots                        3,118       89   20.4%
  Lucky shots                         51        1        

  Enemy fire at you                Total    /game    Rate
  Shots                          103,869    2,997        
  Hits                            20,242      585   19.5%
  Headshots                        2,776       80   13.7%

  Accuracy with troopers and everything else included: 69%
  Rates count heroes only, troopers and other NPCs left out.

  Damage by range
                  Gun dealt   Ability dealt       Gun taken   Ability taken
  0-10m       144,389 (29%)   429,911 (39%)   152,209 (33%)   414,436 (39%)
  10-20m      186,344 (38%)   283,331 (25%)   163,681 (37%)   314,968 (30%)
  20-30m      105,837 (21%)   158,581 (14%)    77,137 (17%)   148,121 (14%)
  30-40m       50,584 (10%)     90,250 (9%)     45,248 (9%)     83,973 (8%)
  40-50m        10,172 (2%)     53,025 (5%)     12,476 (3%)     49,244 (4%)
  50-75m         1,805 (0%)     57,622 (5%)      2,885 (1%)     31,083 (3%)
  75-100m           17 (0%)     15,859 (2%)         38 (0%)      5,426 (1%)
  100m+              2 (0%)     26,852 (2%)               -     11,472 (1%)

  Falloff on your hits: 8% none, 86% partial, 6% max
  Falloff on hits taken: 29% none, 61% partial, 10% max

  Parries 98 landed, 117 missed, 2.1 landed per game
  Counterspell auto-parries count as landed parries.

Per game, the last 10 of 47 (--games N lists more), newest last

  Account    Day        Result  K/D/A       Hit %   HS %    Shots  Parry  Match ID
  main       2026-07-02 win     10/5/15      36.2   21.9      629      1  12345678
  main       2026-07-03 loss    9/12/11      48.2   22.0      925      0  12345731
  main       2026-07-03 win     7/3/16       44.0   23.6    1,009      2  12345802
```

### Movement across your games

```
deadlock movement --hero Mirage
```

- meters per minute, dashes, and the share of alive time sliding, airborne, on ziplines, or fighting, averaged across every game of a hero. The archive counterpart of `match --movement`
- wins and losses get their own columns so a pace gap between them stands out
- reads the per minute `movement_intervals` table, which always builds, so no config change is needed
- a game without movement rows prints `-` in the per game table and stays out of the averages
- `--days`, `--since`, `--account`, and `--games` filter like `damage`

```
Movement, 47 games of Mirage

  Metric                        All (47)     Wins (26)   Losses (21)
  meters /min                      380.1         386.4         372.3
  stationary %                      10.5          10.1          11.0
  slide %                            3.6           3.7           3.4
  in air %                           8.1           8.4           7.7
  zipline %                          6.6           6.4           6.8
  fighting players %                24.7          25.2          24.1
  ground dashes /min                 1.8           1.9           1.7
  air dashes /min                    0.2           0.2           0.2

  Percents cover seconds alive. Stationary and the pace cover seconds moving.
  Meters skip ziplines, respawns, and other teleports.

Per game, the last 10 of 47 (--games N lists more), newest last

  Account    Day        Result  K/D/A      m /min Stationary %  In air % Fighting % Dash /min   Match ID
  main       2026-07-02 win     10/5/15     391.4          9.8       7.6       25.1       1.9   12345678
  main       2026-07-03 loss    9/12/11     356.2         12.4       6.9       23.0       1.6   12345731
  main       2026-07-03 win     7/3/16      402.7          8.9       8.8       26.3       2.1   12345802
```

## Heroes, abilities, and items

These commands read the included hero, ability, item, and rank data instead of your matches, so they need no games and work offline. Asset data from 2026-01-01 onward is included with the package.

### Hero card

```
deadlock hero Pocket
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
deadlock hero Seven --level 30
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
deadlock ability "Fire Scarabs" --souls 50000
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
deadlock item "Mercurial Magnum"
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

The comparison commands (`compare`, `builds`, and the top player part of `item`) all read the same pool: the players you track for a hero. Tracking a player takes three steps, and after the download every comparison runs offline from the downloaded games:

1. **Find candidates.** `deadlock leaderboard --hero Mirage` lists the current top players of the hero with their account IDs and ends with paste-ready config lines:

   ```
   Mirage leaderboard:
     tracked2           111222333    rank 1    Europe
     tracked3          444555666    rank 24   SAmerica

   Track players by pasting lines into config.toml, then `deadlock download --hero "Mirage"`:

   [players."Mirage"]
   "tracked2" = 111222333
   "tracked3" = 444555666
   ```

   Rank is their rank on that hero across regions, from the per-hero leaderboards on [deadlock-api](https://api.deadlock-api.com). The overall ranked ladder is not used here since it says nothing about a specific hero. Anyone works, not just ladder players: for a friend, take the Steam64 number from their Steam profile URL and subtract 76561197960265728, the difference is the Steam32 account ID. A match of theirs you already downloaded also holds the exact ID in the `players` table ([writing your own queries](../README.md#writing-your-own-queries)). Searching by name is unreliable, since the only name search is over current Steam persona names, which change often.

2. **Track the ones you want.** Paste their lines under `[players.<Hero>]` in `config.toml`. The name is just a label for reports, keep theirs or write your own.

3. **Download their games.** `deadlock download --hero Mirage` pulls recent ranked games from everyone tracked for the hero. Nothing is ever downloaded from the leaderboard on its own. Re-running adds new games without downloading old ones again.

To stop comparing against someone, delete their line from `config.toml`. The downloaded matches stay on disk (they cost little space and a game can contain more than one tracked player), they just stop being read, and tracking the player again later needs no new downloads. `deadlock compare movement --hero Mirage` shows who is in the pool with their games and account IDs.

### Hero meta by rating

```
deadlock meta --hero Mirage --by rating
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
deadlock builds --hero Mirage
```

- items your tracked players buy (in wins vs losses), from their downloaded games
- `--min-percent 30` hides items bought in fewer than 30% of the builds
- an expensive late item with a big win/loss gap usually just means the winner got rich enough to buy it

```
Tracked Mirage players (30 downloaded games):

  Player             Games  Rank  Record
  tracked2            10     1  8W 2L
  tracked3           10    14  6W 4L
  tracked4             10     -  7W 3L

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
deadlock compare souls --hero Mirage
```

- your games vs your tracked players, from their downloaded games. Reports are `souls`, `damage`, `healing`, `combat`, and `movement`
- `compare souls` starts with income-source gaps, then net worth over time. `--milestones` flips it to the median minute each side reaches each net-worth mark
- `compare damage` and `compare healing` start with the source breakdown, grouped like the standalone commands, then print the interval table underneath. Healing includes a healing-prevented section when anti-heal rows exist
- `compare combat` compares aim, incoming fire, and parries as whole-window counters. `compare movement` prints whole-game movement averages and has its own section below
- the interval reports use the same 5-minute windows the `match` command uses (`--interval 10` for wider rows). Only your ranked games count, matching the pool
- the summary table shows each player as one row with their whole-game rate, you first for contrast
- every interval cell is the median of the per-game rates inside that window, so a game only counts while it lasts. The cumulative gap column keeps the running total of the gap column — positive means you are ahead by that point in a typical game, negative means you trail
- late intervals are not shown once too few games reach them on either side, sparse records would skew the medians
- `--since 2026-06-30` keeps only your games from that date, useful when a patch changed the soul economy and old games would drag your median
- `--pool-since 2026-06-30` also filters the tracked comparison pool by match date. Use both flags when you want recent form vs recent form
- `--against tracked1` compares you against only that tracked player. It takes tracked player names or account IDs, comma-separated for several
- `compare souls --milestones` is the `souls --milestones` table against the pool: the median minute each side first reaches every net-worth mark, with a Behind column for how many minutes later you get there

```
You (111222333, 50 games) vs 3 tracked Mirage players (30 games): souls

  Player             Games  Rank  Last download   Avg/min  Med/min
  you                   50     -              -       978      961
  tracked2            10     1     2026-07-10     1,102    1,056
  tracked3           10    14     2026-07-10       989    1,004
  tracked4             10     -     2026-07-08     1,041    1,022

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

```
deadlock compare souls --hero Mirage --milestones

  Minutes to reach a net worth, median across games
  You: main, 64 Mirage games     Them: 49 Mirage games

    Souls      You     Them   Behind    Games
     1600      2.8      2.4     +0.3    64/49
     3200      5.6      4.6     +1.0    64/48
     4800      7.7      6.5     +1.2    63/48
     6400      9.6      8.0     +1.6    63/48
```

Narrow the tracked side to one player when you want a direct head-to-head:

```
deadlock compare souls --hero Mirage --milestones --against tracked1
```

```
deadlock compare damage --hero Mirage --against tracked1 --since 2026-07-14 --pool-since 2026-07-14

Damage to heroes by source

  Delivery                 You/game  Them/game  Gap/game  You/min  Them/min   Gap/min   You %  Them %
  Abilities                  18,271     24,006    -5,735      509       709      -200     55%     47%
  Gun                         8,092     14,679    -6,587      226       433      -208     24%     29%
  Total                      33,434     51,032   -17,598      932     1,506      -575

  Source                 Delivery                You/game  Them/game  Gap/game  You/min  Them/min   Gap/min   You/1k  Them/1k    Games
  Djinn's Mark           Abilities                  6,721     11,939    -5,218      185       352      -168        -        -     57/9
  Promises Kept          Gun                        5,627     11,189    -5,562      157       330      -174        -        -     58/9
  Toxic Bullets          Items (bullet procs)       2,604      4,593    -1,989       70       136       -65      786    1,435     28/9
  Total                                             33,434     51,032   -17,598      932     1,506      -575        -        -     58/9

Damage over time
```

### Movement vs your tracked players

```
deadlock compare movement --hero Mirage
```

- whole-game movement averages instead of intervals: the tracked player list, the pooled gap table, and one row per tracked player
- the Tracked column comes from past `deadlock download` runs for the players you track on the hero, nothing is fetched by this command
- Rank is their hero ladder rank when they were downloaded, `-` for players who were never on the board
- long or wide names (Korean, Cyrillic) are cut to a fixed width so the table stays aligned
- the Tracked averages can blend playstyles: here every tracked player beats the you row on meters and stationary, while in air ranges from 13% to 31% because ground and air Mirages are both viable

```
You (111222333, 50 games) vs 3 tracked Mirage players (34 games): movement

  Player             Games  Rank  Last download
  tracked1            14     1  2026-07-01
  tracked2            10     -  2026-07-01
  tracked3             10    23  2026-07-01

  Metric                        You  Tracked      Gap
  meters /min                 388.3    430.0    +41.7
  stationary %                  9.9      7.1     -2.8
  slide %                       3.9      8.3     +4.4
  in air %                      8.1     21.2    +13.1
  zipline %                     6.7      8.5     +1.8
  fighting players %           24.3     26.7     +2.4
  ground dashes /min            1.7      2.4     +0.7
  air dashes /min               0.2      0.8     +0.6

  Player            Account  Games    Rank   m /min  Stationary   Slide  In air  Zipline  Fighting  Dash/min  Air dash
  you                     -     50       -    388.3        9.9%    3.9%    8.1%     6.7%     24.3%       1.7       0.2
  tracked1      111222333     14       1    453.2        5.4%    7.0%   13.3%     8.8%     26.4%       2.8       0.3
  tracked2      444555666     10       -    451.7        7.2%    9.2%   31.0%     8.2%     28.2%       1.8       1.8
  tracked3       555666777     10      23    420.1        7.2%    7.4%   23.1%     8.6%     30.3%       1.9       1.9
```

### Download matches from other players

```
deadlock download --hero Mirage
```

- downloads recent games from the players you track into their own parquet tables (see below). Nothing is ever downloaded from the leaderboard on its own
- without `--account` it downloads everyone under `[players.<Hero>]` in your config.toml
- `--account 111222333` downloads a specific player without tracking them (still needs `--hero`, comma-separated for several). Their games archive and `deadlock match` reads them, but only players in config.toml join the comparisons
- `--match 12345678` fetches one match by ID (comma-separated for several), no `--hero` needed: it stores every player in the match, so `match --hero <anyone>` then works on it
- re-running adds new matches without downloading old ones again
- `--games 10` raises how many recent ranked games per player (5 by default)
- read downloaded player games by name or ID, for example `deadlock damage --hero Mirage --account tracked2` or `deadlock damage --hero Mirage --account 111222333`
- read a specific downloaded match directly by ID, for example `deadlock match 12345678 --hero Mirage`
- players still on the ladder get their current rank noted when downloaded, so the comparison reports can show it later

### Is an item worth buying

```
deadlock item "Escalating Exposure" --hero Mirage
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

### Leaderboard

```
deadlock leaderboard --hero Mirage
```

- the current top players of a hero from the per-hero leaderboard, with their account IDs and paste-ready config lines for the ones you are not tracking yet ([Tracked players](#tracked-players-and-public-stats))
- `--matches` (optionally `--matches 10`) lists each one's recent ranked match ids, win or loss, so you can pick a game to pull
- tracked `[players.<Hero>]` entries show up too, marked `tracked`

```
Mirage leaderboard:
  tracked2           111222333    rank 1    Europe
      12345678  2026-07-05  win   14/2/23
      12345670  2026-07-05  win   19/5/20
  tracked3          444555666    rank 24   SAmerica
      12340013  2026-07-03  win   13/7/17
```

## Setup and maintenance

### Sync new matches

```
deadlock sync
```

- pulls new matches from the Steam cache into the archive and updates the parquet tables
- run this after opening matches in the in-game history, then use `deadlock history` to get match IDs
- report commands also do a quiet sync first, so `deadlock history` after a session usually shows the new games without a separate command
- the row counts it prints are what the new matches added on that run, not table totals
- `--source api` pulls your match history from deadlock-api.com and downloads any missing matches into the archive without opening them in game
- after a game update, sync pulls the new item data once and re-exports the matches that came in with the old data. It reads the installed version from steam.inf, so between patches it never calls the assets API, and offline it just skips
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

Exported 1 new match and skipped 813 already exported
```

The API holds at least a subset of an account's matches, and it is possible to have it retrieve all of them, so the sync grabs whatever it has. To fill the gaps yourself you can click each game in the in-game match history, though the game only lets you open roughly 50 before making you wait and try again. Check out [deadlock-api.com](https://deadlock-api.com) for more details.

### Your Steam accounts

```
deadlock accounts
```

- the Steam accounts on this PC that have run Deadlock, with the account IDs you put in `config.toml`
- reads Steam's `userdata/` folders and remembered logins, so it works before any matches are processed
- ends with a ready-to-paste `[accounts]` block for the accounts `config.toml` does not name yet
- the suggested names are neutral on purpose: your account name (the private login) is best kept out of `config.toml`, since the names you pick there are printed in report headers

```
Steam accounts on this PC that have run Deadlock, newest login first:

  Account      Account name       Profile name       Archived games  config.toml
  111222333    mainlogin          tracked2                     36  main
  123456789    oldalt             tracked2                      3

Add the ones that are you to config.toml, the names are yours to change:

[accounts]
alt1 = 123456789
```

### Your config

```
deadlock config
```

- prints where `config.toml` lives (the full path, ready to paste) and what it holds: timezone, accounts, tracked players, and any excluded tables
- `deadlock config --edit` opens it in your editor (`$EDITOR`, or the default app on Windows and macOS), handy since the file sits in a hidden folder

### Refresh the game data

Hero, item, and ability values ship with the package, so everything works offline out of the box. After a Deadlock patch the values on `deadlock-api.com` move ahead of the bundled copy, which only catches up when a new release of `deadlock-matches` ships. To pull the current values yourself instead of waiting:

```
deadlock assets
```

This saves the current snapshot to `~/.local/share/deadlock-matches/assets/` on Linux or `%LOCALAPPDATA%\deadlock-matches\assets` on Windows. Every command reads from there before the bundled copy, so you stay current.

To bring the `--as-of` and `--changes` history up to the new patch too:

```
deadlock assets --backfill
```

It fetches only the patches newer than what shipped and appends them.

### The Claude Code skill

```
deadlock skill install
```

- writes the bundled Claude Code skill to your Claude skills directory, teaching an agent the CLI, schemas, query helpers, and data pitfalls
- existing local edits are left alone unless you pass `--force`
- `deadlock skill path` prints the destination, `--dir` uses a different one
- `deadlock skill print` writes the skill to stdout for a quick read or for other agents

### The data dictionary

```
deadlock schema
```

- column names, types, and descriptions for every parquet table, or one table with `deadlock schema players`
- `--sample` prints real rows from your local data
- see [data.md](data.md) for the table overview and query patterns
