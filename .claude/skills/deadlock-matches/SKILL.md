---
name: deadlock-matches
description: Decode and analyze Deadlock match metadata from the Steam httpcache (the .meta.bz2 protobufs uploaded to statlocker). Use to answer questions about the user's matches, item value, top-player builds, or farm/combat pacing, or to extend this repo's tooling.
---

# Deadlock match metadata

Reads match metadata from Steam's HTTP cache and compares the user's games against top players. Answer plain-English questions by running the CLI, or write ad-hoc Python against the modules for novel ones.

## User config

- gitignored `config.toml` in repo root sets the `--account` default: an `[accounts]` table of `name = <steam32 id>` pairs (the only accepted shape — a plain list exits with the expected form). Every CLI run writes a commented starter config when the file is missing (`config.ensure_config`); the starter excludes the movement table (`exclude = ["movement"]`)
- "your games" = union across all alt accounts; `--account` (comma-separated) overrides per-invocation and takes config names as well as ids (`--account main`), matched case-insensitively. Report headers print the names (`config.format_accounts`)
- accounts empty? run `deadlock accounts` — it lists the Steam accounts on this PC that have run Deadlock (userdata/ folder names = Steam32 ids, account/profile names from loginusers.vdf, archived game counts) and prints a paste-ready `[accounts]` block with neutral main/altN names; offer to fill config.toml in from it. `extract.steam_accounts()` is the underlying reader. Suggested names are deliberately NOT the Steam account names — those are half of the login credentials and config names print in report headers (output columns use Steam's terms: Account name = private login, Profile name = public persona)
- `--hero` is always explicit — take it from the question or the user's recent `history` output
- `config.toml` also holds selected comparison players per hero as `[players.<Hero>]` tables (top ladder accounts, friends, anyone) — read via `config.config_players("Mirage")` for ad-hoc analysis (`players.download_builds`, damage comparisons). Never hardcode or commit player names/ids; the config is gitignored for a reason
- `config.config_timezone()` gives the zone for grouping matches into local days ("wins per day", "this week") — reads `timezone` from config.toml (the starter pins the detected zone at creation). Always `convert_time_zone()` with it before `.dt.date()`; `start_time` is UTC and late-night sessions split across days otherwise

## Common questions

```bash
uv run deadlock accounts                  # Steam accounts on this PC that have run Deadlock:
                                          # ids, account/profile names, archived games, plus a
                                          # paste-ready [accounts] block for config.toml
uv run deadlock history [--days N] [--since 2026-07-01]
                                          # lists one line per game of yours with account, hero,
                                          # result, K/D/A, souls, damage, timestamp, and match id,
                                          # newest last, last 10 games by default. Run it to get
                                          # the match id that match/download take
uv run deadlock match [12345678] [--hero Wraith] [--interval 10] [--souls|--damage|--healing|--teams|--abilities|--items|--accolades|--statues|--stacks|--combat|--deaths|--kills]
                                          # prints the 12-player final scoreboard (lobby average,
                                          # K/D/A, souls, damage, obj damage, healing, prevented,
                                          # last hits, denies, resolved player starred), then that
                                          # player's match split into 5-minute intervals of
                                          # souls (+/min), K/D/A, damage dealt/taken, obj damage,
                                          # healing + prevented healing, last hits (troopers +
                                          # neutrals split out), and denies, with a Total row;
                                          # --deaths logs each death (killer, game time, fight
                                          # length, killer distance in meters, respawn timer) and
                                          # --kills the same from the killer side, straight from
                                          # the deaths table with no movement join;
                                          # no id = your most recent match, --hero picks any
                                          # player in the match instead of you (your games keep
                                          # all 12 players; a match none of your accounts played
                                          # never reaches your tables — download --match pulls it
                                          # into the players tables and match falls back to them
                                          # by itself when the id is not in your tables);
                                          # --souls swaps the columns for souls by source, like the
                                          # in-game souls graph (in-game screen labels, hidden
                                          # sources only when nonzero), plus a Lane/Roaming/Combat/
                                          # Objectives/Catch-Up/Other group block: Lane = troopers
                                          # + denies, Roaming = jungle + breakables, Objectives =
                                          # bosses + urn; Total is gross souls earned, net worth
                                          # adds starting souls and subtracts death losses;
                                          # --damage swaps the columns for damage to heroes by
                                          # source, reproducing the in-game damage graph tooltip,
                                          # plus a Gun/Abilities/Items(gun|spirit) group block
                                          # from the delivery column; --healing = the same for
                                          # healing plus a "Healing prevented" table per anti-heal
                                          # item (the game shows neither per source); --teams =
                                          # souls per team with the running lead, then every
                                          # objective and Rejuvenator as it fell (steals called
                                          # out), worded from the resolved player's side;
                                          # --abilities = ability unlocks/upgrades in spend order,
                                          # with the level and soul requirement for that unlock
                                          # or cumulative AP spend;
                                          # --items = every purchase in buy order with the era
                                          # shop price, "sold at", "into <upgrade> at" (flags=1
                                          # component consumption paired to the buy at
                                          # sold_time_s via components), and "imbues <ability>"
                                          # from imbued_ability;
                                          # --accolades = the post-game stat awards from the
                                          # accolades table (value + threshold, stars shown =
                                          # threshold+1, names from bundled accolades.json) —
                                          # the ONLY source for gun/melee/ability kill splits,
                                          # close/long-range kills and damage, killstreak kills,
                                          # first blood, urn deliveries, and barrier absorption;
                                          # --statues = permanent buff statues from the statues
                                          # table, counts per buff and level plus the stat they
                                          # added up to, per-pickup values resolved against
                                          # statue_history at match time (counts have no
                                          # timestamps, so no per-interval split exists);
                                          # --stacks = stack counts from the stacks table for
                                          # EVERY player in the match, from the abilities and
                                          # items that track stacks (Sticky Bomb, Trophy
                                          # Collector, Glass Cannon, Restorative Locket,
                                          # Guided Owl / Assassinate / Combo kill counters);
                                          # final values only, no timestamps;
                                          # --combat = the fight stats from the custom_stats
                                          # table: shots/hits/headshots vs heroes both
                                          # directions (the enemy column is the whole team
                                          # combined, no per-enemy data exists), damage by
                                          # range band with falloff splits, parries with
                                          # melee damage taken (light/heavy melee only,
                                          # ability melees land under their own source) and
                                          # Counterspell/Rebuttal buy times, comeback souls
                                          # (Unstable Rift called out), average unspent
                                          # souls/AP, and per-hero counters (stack uptime
                                          # tables); whole-match totals, ignores --interval
uv run deadlock item "Mercurial Magnum"   # the shop card: innate stats, then each passive/active
                                          # section with the game's labels and units (offline)
uv run deadlock item "Escalating Exposure" --hero Mirage [--min-rating all] [--since 2026-06-30]
                                          # your games table + meta stats, whether it is worth
                                          # building (no card here, the bare form above is the
                                          # card); meta defaults to Eternus+ lobbies, --since caps
                                          # your games AND the meta to a patch window
uv run deadlock builds --hero Mirage      # item builds from top players of a hero
uv run deadlock compare --hero Mirage     # your stats vs top players, where you fall behind
uv run deadlock compare --hero Mirage --stat soul_sources
                                          # the same gap split by income source
uv run deadlock leaderboard --hero Mirage [--players 8] [--matches 5]
                                          # current top players from the per-hero leaderboard with
                                          # account_ids (config players too, marked config); --matches lists
                                          # each one's recent ranked match ids + result, the
                                          # discovery step before download --account/--match
uv run deadlock download --hero Mirage [--account 111222333] [--match 12345678]
                                          # materialize recent matches from top players and
                                          # config-selected players into parquet-players/ (see below).
                                          # --account pulls specific players' recent games instead
                                          # of the leaderboard (needs --hero); --match fetches
                                          # matches by ID, no --hero (stores all 12 players, so
                                          # match --hero works on any of them). both comma-separate.
                                          # then read a top player's game with:
                                          # deadlock --parquet <parquet-players dir> match <id> --hero Mirage
uv run deadlock winrate [--days N] [--since 2026-07-01] [--by week] [--hero Mirage] [--min-rating Oracle]
                                          # daily W/L, MVP/Key Player counts, net wins, and a
                                          # Lobby column (average lobby rating, averaged in
                                          # subrank steps so means never land between levels);
                                          # --by week/month rolls days into bigger buckets;
                                          # never hand-roll this in polars. --hero adds the
                                          # hero's public win rate (deadlock-api.com, Eternus+
                                          # default) under the table; skipped offline.
                                          # a footer separates games with an abandon (who left:
                                          # you/ally/enemy with each record, reconnects) plus
                                          # the record without them — abandoned games stay in
                                          # the table, they are still real wins and losses.
                                          # not_scored games are left OUT of the table and
                                          # reported under it (match history still shows their
                                          # result)
uv run deadlock deaths [--hero Mirage] [--days N] [--radius 2000]
                                          # deaths by game time, top killers; with movement
                                          # exported also solo/outnumbered context
uv run deadlock movement --hero Mirage    # slide/dash/air movement profile vs top players
                                          # (needs movement out of the config exclude list)
uv run deadlock hero Mirage --souls 25000 # boon stats at a soul breakpoint (health, spirit,
                                          # melee, gun damage, AP), --level N works too,
                                          # no breakpoint = base card + per boon gains
uv run deadlock ability "Dust Devil" [--hero Mirage] [--souls 25000 | --spirit 100 --melee 80] [--weapon 58]
                                          # ability/gun numbers: base, spirit scaling, and a
                                          # section per tier with the values it changes;
                                          # --souls/--level resolves boon scaling (spirit,
                                          # melee); --spirit N resolves at a total spirit
                                          # power instead (the in-game stat, items included),
                                          # --melee N the same for light melee damage (heavy
                                          # keeps the hero ratio, the two combine), both
                                          # reject --souls/--level since a total already
                                          # includes boons; --weapon N resolves weapon scaling
                                          # (Gutshot etc) at a bonus weapon damage percent =
                                          # item % + weapon shop investment %, boon-free so it
                                          # DOES combine with --souls/--level (verified in
                                          # sandbox 2026-07-10: 58 = Weighted Shots 40 + 18
                                          # for 3,200 souls invested; Kinetic Carbine's custom
                                          # weapon formula stays unresolved on purpose);
                                          # --hero for names on several heroes
uv run deadlock meta [--hero Mirage] [--by rating|day|week|month] [--min-rating Eternus] [--since 2026-06-01] [--until 2026-07-01]
                                          # public hero win/pick rates from deadlock-api.com;
                                          # --by rating = per skill rating (Oracle 3), day/week/month = trends
                                          # over time; --hero narrows to one hero (defaults --by
                                          # to week); the API recomputes any historical window
                                          # (max_unix_timestamp), so no local accumulation needed;
                                          # no region dimension exists on the analytics endpoints.
                                          # min-rating filters BOTH teams while buckets use the
                                          # match average, so the boundary bucket shrinks under a
                                          # floor (mixed lobbies drop out) — read distributions
                                          # without a floor; counts also drift between fetches
                                          # (each flag combo is its own URL, cached up to a day)
uv run deadlock schema [table]            # the data dictionary — read before writing polars
uv run deadlock assets                    # refresh the bundled current-patch data after a patch
uv run deadlock sync                      # rebuild parquet tables; --full from scratch;
                                          # --source api pulls missing matches from the
                                          # match-history API into the archive (it may not
                                          # have every game — the rest need in-game clicks)
```

`compare --stat` accepts: `farm` (default, kill/assist gold excluded), `combat`, `objectives`, `catch_up`, `other` (item income), `souls` (net worth), `soul_sources` (the income gap table, all sources + a footnote that net worth runs ~1% over the sum, the game credits sell refunds etc. to no source), or any raw snapshot field (`creep_kills`, `denies`, `player_damage`, ...).

## Aggregate questions → parquet + polars

Prefer `deadlock sync` + polars over looping protobufs for win rates, damage totals, souls curves, item timing. Tables rebuild automatically whenever a data command archives new matches, so run a quick `deadlock history` first and the tables are guaranteed fresh; `deadlock sync --full` forces a full rebuild. A column or table added to `schemas.py` needs no manual step — `export.schema_drift` compares every month file against the schema on each incremental export (both stores, footer reads only) and a mismatch triggers the full rebuild automatically, printing one "Rebuilt all tables" line. Never hand-patch a drifted month file; the rebuild streams one month at a time from the archive (or the stored API bodies for parquet-players), so it stays memory-bounded at any archive size. Sync filters to the config accounts — it refuses to run without an `[accounts]` table and refuses `--account` ids not in it. `--archive`/`--parquet` point any command at non-default dirs. Tables live in `~/.local/share/deadlock-matches/parquet/`.

Importing the package pins the polars engine affinity to streaming (`engine.py`), so every collect stays memory-bounded on the big tables. The streaming engine does NOT keep row order through joins or group_by — sort explicitly before printing or asserting on order, never rely on file order surviving a join. Float sums can also differ in the last bits between runs.

### queries.py helper catalog

Start ad-hoc polars from these instead of rewriting boilerplate. This is the canonical list — the module map points here.

- `scan("damage")` — lazy-read a table by name
- `my_games()` — players table filtered to the config accounts, joined to matches, with `start_local`/`day` already in your timezone
- `daily_record()` — the per-day W/L frame behind `deadlock winrate`
- `abandon_record()` — one row per scored match in the same window where someone abandoned: `you`/`ally`/`enemy` flag who left, `returned` = the leaver reconnected. The ONLY reconnect evidence is damage growth between samples after the abandon — queued builds keep auto-buying with passive souls while a player is disconnected, deaths happen to an idle hero, and kills are deliberately not counted. Backs the winrate footer
- `unscored_record()` — the not_scored games the winrate table leaves out (same window filters, match history still shows their result)
- `item_buys("Echo Shard")` — your purchases with `buy_n` order within the match ("bought it as my 6th item")
  - `item_buys(tier=4)` keeps one shop tier, `buy_n` unchanged. tier is a real assets label (`item_tier`), 1:1 with cost 800/1600/3200/6400. NO 4800 tier exists — 4800 is only the incremental outlay when a 1600 component upgrades into a 6400 item, and the buy row lands at upgrade time at full cost
- `item_games("Echo Shard", "Mirage", since="2026-06-30")` — one row per game with first buy time, buy order (`buy_n`), same-tier order (`tier_buy_n`), first same-tier purchase (`first_tier_item`/`first_tier_time_s`), `is_first_tier_item`, `owned_s` (ownership windows summed, a sold buy's window ends at the sell time), item damage, and `dealt_after_buy` (your hero damage while owning it, the denominator for `percent_of_hero_damage`). Nulls = not built for the item's own buy/order columns; sold buys still count as built; `since` caps to a patch window. Backs `deadlock item`
- `hero_damage()` — the damage table pre-filtered to detail rows on hero targets (safe base for any per-source sum; `stat=` picks healing/mitigated/...)
- `damage_by_source("Mirage", accounts=, matches=)` — whole-game totals per damage source across your games of a hero (one row per gun/ability/item source with `games`, `total`, `per_min`, `percent` of hero damage), the aggregate counterpart to the per-interval `deadlock match --damage`. `matches=` scopes to specific match ids (one game, like `--match`). Eager frame, raises if you never played the hero; damage only (for healing-by-source sum `hero_damage("healing")`)
- `souls_by_source("Mirage", accounts=, matches=)` — the souls mirror over `soul_sources`: whole-game souls per income source across your games of a hero (`games`, `souls` = the in-game souls+orbs total, `secured_orbs`, `percent` of total, `orb_share`), the aggregate counterpart to `deadlock match --souls`. `matches=` scopes to specific match ids. Same eager/raise shape
- `custom_stats(stat=, group=, accounts=, matches=)` — the hidden counter table (parries, vs-hero accuracy, damage by range, comeback souls, per-hero counters) with hero/won and local day joined, every filter optional ("parry rate by hero" is one group_by away). Backs `deadlock match --combat`
- `final_stats()` — final snapshot per match-player with hero/won joined and `accuracy`/`headshot_rate` computed
- `team_damage_ranks()` — every player's final hero damage ranked within their team per match (`top_team_damage` flags the damage chart top — "am I top damage on my team")
- `ability_upgrades()` — ability unlocks/upgrades in spend order with the level and soul requirement for each unlock or cumulative AP spend
- `hero_scaling()` — per-hero-per-level reference frame (base_health, spirit_power, required_souls) with one row per patch era; `hero_scaling_asof(left)` as-of joins it by (hero_id, level) on start_time
- `skill_rating(column)` — maps a badge level column to labels ("Emissary 4")
- `my_deaths()` — deaths joined to your games (hero/won/day)
- `death_context(radius=2000)` — adds allies/enemies/solo/outnumbered at the death second (raises unless movement is exported — check `table_exists("movement")` first)
- `snapshot_players(hero)` — your games as timeline-ready blocks read from parquet (feeds `timeline.compare` without looping protobufs; `deadlock compare` uses it for your side since 2026-07-07)
- `match_intervals(match_id, account_id, interval_s=300)` — one player's match as per-interval gains: souls/kills/deaths/assists/damage/damage_taken/obj_damage/healing/heal_prevented/creeps/neutrals/denies + souls_min, diffed from the cumulative snapshots. kills and deaths come from the deaths table instead (snapshot kills/deaths both drift). Backs `deadlock match`
- `soul_intervals(match_id, account_id, interval_s=300)` — one player's souls as per-source interval gains from `soul_sources` (value = souls+souls_orbs, sources with any souls ordered by match total, same 3-min-sample forward-fill as `damage_intervals`). Backs `deadlock match --souls`; the cli maps `source_name` to in-game screen labels and the Lane/Roaming/Combat/Objectives/Catch-Up/Other groups
- `damage_intervals(match_id, account_id, interval_s=300, stat="damage")` — one player's damage to heroes as per-source interval gains from `damage_sources` (detail rows only, ordered by match total). Backs `deadlock match --damage`
- `source_intervals(games, interval_s=300, stat="damage")` — the same across multiple matches at once (games = any frame with match_id/account_id columns, e.g. my_games or tracked_player_games rows; same per-source forward-fill, plus a `full` flag for whole windows; `stat="healing"` for healing). NEVER sum cumulative `damage_sources` across sources per timestamp yourself — each source samples at its own times so the sum sawtooths and undercounts (~55% low when tried 2026-07-08)
- `team_intervals(match_id, interval_s=300)` — both teams' souls gained per interval with the running lead (team 0 minus team 1). Backs `deadlock match --teams`
- `movement_profile()` — per-(match, player) movement metrics (slide/dash/air percents, distance, stationary percent, farm pace — hero-normalize before comparing players)

```python
from deadlock_matches import queries

queries.my_games().group_by("hero").agg(pl.len().alias("games"), pl.col("won").mean()).collect()
```

### Tables and schema caveats

Tables: `matches`, `players`, `stats`, `soul_sources`, `item_events`, `accolades`, `statues`, `stacks`, `custom_stats`, `damage`, `damage_sources`, `objectives`, `mid_boss`, `movement`, `deaths` (`deadlock schema <table>` prints columns). Other players' games are the SAME tables under the sibling `parquet-players/` dir via `deadlock download` — read `queries.scan(table, players.PARQUET_DIR)` and `players.tracked_player_games(...)`.

The CLI commands and the `queries.py` helpers above already apply every per-table caveat — relaying their output or reusing a helper needs nothing more. **Read `references/schema-caveats.md` BEFORE hand-writing raw polars against a table no helper covers** — it has each table's columns and verified traps. The four that bite most, always in force:

- `soul_sources`: the in-game number is `souls + souls_orbs` — ALWAYS sum both (`souls` alone drops the orb-confirm share, a big chunk of trooper income that drifts by patch)
- `damage`/`damage_sources`: filter `target_account_id.is_not_null()` for hero damage (null = creeps/objectives; skipping it inflated gun-crit 9×), and never sum `category == "total"` rows together with detail rows (double-counts)
- `stats` are cumulative snapshots (`max()` ≈ final); snapshot `kills`/`deaths` drift from the scoreboard — use the `deaths` table for the real count
- `damage_sources`/`soul_sources` samples are sparse (~3 min) and `damage_sources` is RIGHT-aligned — never diff them by hand, use the `*_intervals` helpers

### Ad-hoc rules

Keep it cheap — one exploratory session cost ~5 scripts and 3 avoidable errors before these rules existed:

- write ONE scratch script and iterate on it; don't create a new file per step
- run `deadlock schema <table>` for exact column names BEFORE writing joins (damage keys are `dealer_account_id`/`target_player_slot` — there is no dealer_slot)
- print compact aggregates (`group_by().agg()`), never per-game dumps — a 30-row table repr burns context and usually gets truncated anyway; `pl.Config.set_tbl_width_chars(240)` up front avoids re-runs for hidden columns
- run scripts from the repo root with an absolute script path; `cd` into the scratchpad breaks `uv run`'s env

Protobuf modules stay the tool for per-match detail the tables don't carry:

```python
from deadlock_matches import extract

for path in extract.iter_matches():
    info = extract.load(path)
    print(info.match_id, info.duration_s, len(info.players))
```

## Presenting results

For per-day / per-interval summaries, render an aligned table: one row per period, columns like Day, Games, W, L, Win rate, Net, Cumulative net. Right-align numbers, sign the net columns (+3 / -1), say which timezone days are grouped by, and end with a one-line overall summary ("26 games, 20-6, 76.9% win rate, +14 net"). Don't dump raw dataframe reprs at the user. `deadlock winrate` prints the daily version of this ready-made — relay its output instead of rebuilding the table.

## Where the data is

- `extract.default_cache()` finds Steam's cache (Linux: native `~/.steam`, `~/.local/share/Steam`, or flatpak; Windows: registry SteamPath or the default install). Data/cache dirs come from `paths.py` (`~/.local/share` + `~/.cache`, or `%LOCALAPPDATA%`)
- match entries: `replay###.valve.net/1422450/<match_id>_<salt>.meta.bz2` — find `BZh` magic, bz2-decompress, parse as `CMsgMatchMetaData`
- cache only holds matches this client downloaded, and eviction is LRU churn, not age: httpcache caps at 10,000 entries shared with ALL Steam HTTP traffic, entries carry max-age=1y so nothing times out, and re-viewing a match refreshes its slot (measured 2026-07-08: a days-old never-reopened match was evicted while a months-old one survived). Valve's replay servers still serve evicted `.meta.bz2` months later (plain HTTP only, HTTPS fails). A match is cached by VIEWING it in game (Escape -> Account in the top right -> click the game in match history); playing alone does NOT cache it. If a recent match is missing from `dump`, tell the user to open it in match history and rerun
- `extract.iter_matches()` snapshots everything into `~/.local/share/deadlock-matches/matches/` first, then iterates the archive — prefer it over `iter_meta_files` (live cache only)
- the archive is the only irreplaceable data; cache-touching commands print an `archive:` line (mention it if asked about backups)
- API data goes through `api.get_json`, two storage tiers: immutable match metadata bodies persist under `~/.local/share/deadlock-matches/api` (the parquet-players tables rebuild from them; old copies migrate out of the cache lazily), everything else (analytics, leaderboards, match histories) is cached under `~/.cache/deadlock-matches/api` with a 1-day max_age — expired entries refetch, and are still served when the network is down. Assets always refetch (`deadlock assets`)

## Data structure

```
CMsgMatchMetaData
  match_details (bytes) -> CMsgMatchMetaDataContents.match_info (MatchInfo)
    match_id, start_time, duration_s, winning_team, game_mode, match_mode
    players[12]: account_id (Steam32), team, player_slot, hero_id,
                 kills, deaths, assists, net_worth, last_hits, denies,
                 items (buy order), per-minute stats_type_stat snapshots
```

Notes:

- polars keeps Boolean/unsigned dtypes through aggregation, so subtraction wraps around instead of going negative — cast to signed (`.cast(pl.Int32)`) first
- exact per-item/per-ability damage lives in `match_info.damage_matrix`; `damage.damage_from_source()` reproduces the in-game post-match number
- in `player.items`, `flags=1` = consumed as a **component** of an upgrade, NOT a sell; cross-check with `Item.components`. Ability upgrades also appear in the items list masquerading as items — filter by cost/known item ids when reading builds
- `Item.description` (cleaned tooltip) says what an item actually does; `Hero.stats` has base stats — use these instead of guessing from names
- `Item.properties` has the actual stat grants ({tech_power: 18, bonus_health: 75, ...}, negatives are real tradeoffs like Glass Cannon's -13% health). `Hero.scaling_stats` is spirit scaling of base stats (12 heroes, e.g. Vindicta bullet damage +0.022/spirit)
- weapon records in abilities.json carry `weapon` gun stats (bullet_damage, clip_size, falloff/crit ranges, dps). Weapon distances are game units (inches): divide by 39.37 (`cli.cards.UNITS_PER_METER`) for the meters the game shows — Promises Kept falloff 787→2264 units = the in-game card's 20m→58m (verified against the card). Ability `properties` distances are already meters
- known gap: Vyper's in-game "Crit Bonus Scale: -30%" exists nowhere in the assets API (the gun record says the standard 1.65 crit bonus, and no -30/0.7 field exists in any Vyper record, checked 2026-07-07) — don't hunt for it, and don't confuse it with `crit_damage_received_scale` (incoming crits: Seven 0.45, Mo & Krill 0.8, Rem 0.9)
- ability tuning numbers are on `Ability` too: `properties` (base values, unit strings like "20m" already parsed to numbers), `scaling` (which stat a property scales with and by how much), `upgrades` (per-tier bonus entries; `type: add_to_scale` changes scaling, not the base). `stat(name, tier)` and `spirit_scale(name, tier)` do the tier math — verified against deadlock.wiki for Dust Devil (65 base, +60 at T1, scale 0.3 → 1.3 at T3). Lookups: `ability_by_name(name, hero_id)` (raises ValueError on names owned by several heroes — every hero has a "Melee"), `for_hero(hero_id)`, `hero_gun(hero_id)`
- hero level scaling is on `Hero` too: `level_up` (per-boon stat increments), `levels` (soul thresholds per level), `purchase_bonuses` (shop tier bonuses), and helpers `base_health(level)`, `spirit_power(level)`, `level_for_souls(souls)` — snapshot stats tables carry each player's `level`, so these compute expected base health/spirit at any point in a match
- breakpoint questions ("what's my health at 25k souls") are built in: `Hero.stats_at(souls)` / `boon_stats(level)` return level, health, spirit, bullet damage bonus, light/heavy melee and ability points/unlocks; `deadlock hero <name> --souls N` (or `--level N`) prints it with gun dps, `deadlock ability <name> [--hero X]` prints ability numbers with a section per tier (the game's tier text plus before -> after values from `Ability.tier_descriptions` and the tier math). Melee boons: the per-boon melee increment applies to light, heavy keeps the hero's base heavy/light ratio (mostly 2.32; wiki-confirmed, Mirage +1.58 light / +3.67 heavy per boon)
- `Hero.cost_bonuses` / `investment_bonus(slot, spent)` is the shop's souls-invested bonus curve (the graph above each category). The steps are deliberately uneven: 4,800 invested is a designed power spike in every category (spirit +19 spirit power vs +4/+7 neighbors, weapon +28%, vitality +18), and spirit spikes again at 28,800 (+25)
- weapon scaling, sandbox-verified against live damage 2026-07-10: `base_weapon_damage_increase` abilities (Gutshot, Ira Domini, Consecrating Grenade, Witching Hour) consume bonus weapon damage in percent points = item % + weapon investment % from `cost_bonuses`, boons excluded — Gutshot measured 85/115 bare and 126/202 at 58 points (Weighted Shots 40 + 18 for its own 3,200 souls invested), exactly `value + scale × points`. This is what `ability --weapon` resolves. Kinetic Carbine is different: actual damage = 5 + 2.75 × full burst, full burst = 5 bullets (`burst_shot_count` in the raw API weapon_info; the bundled weapon record says `bullets: 1`) × bullet damage INCLUDING boons × (1 + weapon %) — measured 99/223/151/351 across boons × Weighted Shots, boons multiply with items, and the in-game tooltip model (2.80) overshoots actual by ~2%, so the ability card leaves Carbine symbolic on purpose. `bullet_damage` (Hellfire Salvo) and `weapon_damage_scale` (Sleight of Hand, Infernal Brand) are still unmeasured
- melee scaling, same sandbox session: Bashdown measurements (93/200/143/306) matched the bundled model within ±1.2 — spirit part `35 + 1.1 × spirit`, melee part `0.5 × heavy` with heavy keeping the hero ratio through boons (the `--melee` derivation rule, now in-game-proven). The melee STAT gains half the weapon investment % (Crushing Fists case fits 1 + 22% melee + 27% = 54%/2 exactly, the wiki's "melee scales with weapon damage by 50%"), so the stat-screen melee number `--melee` takes already includes it. On-hit riders are NOT in the stat: Crushing Fists' `bonus_heavy_melee_damage: 25` is a separate ×1.25 on heavy hits, applied after ability scaling — same category as crit, out of scope for the resolver
- patch drift: the committed history parquets (`deadlock assets --backfill`) version every patch era, so as-of consumers (`item_events` pricing, `hero_scaling`, `ability_upgrades`, the `--as-of` cards) read the tuning live at match time. The bare `Hero`/`Item`/`Ability` helpers without a `when` describe the CURRENT patch only. `deadlock assets --backfill --confirm` OVERWRITES the committed parquets by rescanning every build since `assets.HISTORY_START` (cached, near-free) — review the diff before committing. There is deliberately no date flag on the CLI: a narrowed scan would truncate the earlier eras, `start_date` exists only as a library param for tests
- no cast events exist ANYWHERE in the metadata: `player.ability_stats` is only the handful of stacking items/abilities (Trophy Collector trophies, Glass Cannon stacks, Sticky Bomb bonus, Restorative Locket charges, Guided Owl/Assassinate counters), exported as the `stacks` table and shown by `match --stacks`, and `custom_user_stats` is the named counter pool behind the `custom_stats` table (73 names as of 2026-07: parries, vs-hero accuracy both directions, damage by range, comeback souls, per-hero counters — see the schema caveats). Active item presses (Debuff Remover), stuns, and debuff windows live only in replay demos, which nothing here parses — don't promise cast counts. The wire `ability_id` is the murmur2 string token of the engine class name (`abilities.string_token`/`class_by_token` do the mapping; assets API ids are the same hash), so ids resolve with no lookup table
- `match_mode == 1` is ranked; hero_id maps to names via `heroes.py`
- api.deadlock-api.com is the same data: `v1/matches/{id}/metadata` returns the identical `match_info` we decode (cross-checked field-for-field, zero diffs), so it's ground truth for decode changes AND a backfill source for matches Steam evicted before we archived them. `v1/players/{id}/match-history` scoreboard fields equal the protobuf top-level player fields exactly (win = `match_result == player_team`); very recent matches lag there by hours, so the local cache is fresher

## Module map

Modules are organized by data source, not by layer: `queries.py` answers questions about YOUR games from the local parquet (works offline); `players.py`/`meta.py` answer questions about other players / the global item meta from the deadlock-api (network via `api.py`, or its warm cache). New analysis helpers go where their data comes from; code mixing both worlds (like `compare`) belongs in the `cli/` package.

Everything in `src/deadlock_matches/`:

- `extract.py` — cache walking, archive sync, protobuf decode (`iter_matches`, `archive`, `load`), local Steam accounts (`steam_accounts`), and `player_party` (recovers the removed party wire field from old matches, see the players caveats)
- `cli/` — the `deadlock` entry point, one module per command group: `main.py` (parser, dispatch, `schema`), `data.py` (`history`, `download`, `sync`, `assets` plus the archive snapshot), `performance.py` (`compare`, `winrate`, `deaths`, `movement`), `items.py` (`item`, `builds`), `cards.py` (`hero`, `ability`)
- `config.py` — config.toml reading and the starter file (`config_accounts`, `config_account_names`, `format_accounts`, `config_players`, `config_exclude`, `config_timezone`, `ensure_config`)
- `export.py` — parquet tables (`build_tables`) plus the `delivery`/`attribution` classifiers
- `schemas.py` — the table models: one class per parquet table, dtype + description per column
- `queries.py` — polars helpers over the local parquet, works offline. Full catalog under "Aggregate questions → queries.py helper catalog"; that is the one place to keep current when adding a helper
- `assets.py` — downloads heroes/items/abilities json from the assets API
- `damage.py` — per-source damage from the damage matrix
- `timeline.py` — per-minute cumulative curves, medians, interval rates
- `api.py` — deadlock-api HTTP client with disk cache (`get_json`), the only network code; its docstring lists every endpoint in use and which function wraps it — keep that list current when adding endpoints
- `players.py` — other players: per-hero leaderboard (`hero_leaderboard`) → top players of a hero → their builds/timelines, plus the parquet-players materialization (`download_matches` for tracked players or `matches_by_id` for specific match ids → `write_player_tables`) and `tracked_player_games(names, hero=, since=)` (tracked players' own rows joined to players/matches with local day, names matched case-insensitively — the downloads→players→matches boilerplate for comparing against specific tracked players). `matches_by_id` rows carry null account/hero (no tracked player brought them in)
- `meta.py` — item win-rate/synergy analytics on API data
- `heroes.py` / `items.py` — id ↔ name mapping from the assets API
- `skill_rating.py` — badge level → skill rating label (`label(52)` = "Ritualist 2", tiers from `data/skill_rating.json`, refreshed by `deadlock assets`)
- `abilities.py` — damage-source class_name → current display name (`label()`; engine names like mirage_tornado never change, display names do), plus ability tuning numbers (`Ability.stat`/`spirit_scale` tier math, `ability_by_name`, `for_hero`, `hero_gun`)
- `gen/` — compiled protos, checked in and never regenerated by hand; `protos/` (repo root) — Valve sources
```
