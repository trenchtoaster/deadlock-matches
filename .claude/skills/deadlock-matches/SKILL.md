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
                                          # match screen numbers + lobby average, most recent day of games by default
uv run deadlock match [92345678] [--hero Wraith] [--interval 10] [--damage|--healing|--teams|--abilities]
                                          # one player's match split into 5-minute intervals:
                                          # souls (+/min), K/D/A, damage dealt/taken, obj damage,
                                          # healing + prevented healing, troopers, neutrals, denies;
                                          # no id = your most recent match, --hero picks any
                                          # player in the match instead of you (works on matches
                                          # you only viewed, every player's snapshots are archived);
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
                                          # or cumulative AP spend
uv run deadlock item "Mercurial Magnum"   # the shop card: innate stats, then each passive/active
                                          # section with the game's labels and units (offline)
uv run deadlock item "Escalating Exposure" --hero Mirage [--min-rating all] [--since 2026-06-30]
                                          # your games table + meta stats, whether it is worth
                                          # building (no card here, the bare form above is the
                                          # card); meta defaults to Eternus+ lobbies, --since caps
                                          # your games AND the meta to a patch window
uv run deadlock builds --hero Mirage      # item builds from top mains of a hero
uv run deadlock compare --hero Mirage     # your stats vs top players, where you fall behind
uv run deadlock compare --hero Mirage --stat soul_sources
                                          # the same gap split by income source
uv run deadlock download --hero Mirage       # materialize recent matches from top mains and
                                          # config-selected players into parquet-players/ (see below)
uv run deadlock winrate [--days N] [--since 2026-07-01] [--by week] [--hero Mirage] [--min-rating Oracle]
                                          # daily W/L, MVP/Key Player counts, net wins;
                                          # --by week/month rolls days into bigger buckets;
                                          # never hand-roll this in polars. --hero adds the
                                          # hero's public win rate (deadlock-api.com, Eternus+
                                          # default) under the table; skipped offline
uv run deadlock deaths [--hero Mirage] [--days N] [--radius 2000]
                                          # deaths by game time, top killers; with movement
                                          # exported also solo/outnumbered context
uv run deadlock movement --hero Mirage    # slide/dash/air movement profile vs top mains
                                          # (needs movement out of the config exclude list)
uv run deadlock hero Mirage --souls 25000 # boon stats at a soul breakpoint (health, spirit,
                                          # melee, gun damage, AP), --level N works too,
                                          # no breakpoint = base card + per boon gains
uv run deadlock ability "Dust Devil" [--hero Mirage] [--souls 25000]
                                          # ability/gun numbers: base, spirit scaling, and a
                                          # section per tier with the values it changes;
                                          # --souls/--level resolves boon scaling (spirit,
                                          # melee); --hero for names on several heroes
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
uv run deadlock assets                    # refresh heroes/items after a patch (+ dated snapshot for as-of pricing)
uv run deadlock export                    # rebuild parquet tables
```

`compare --stat`: `farm` (default, kill/assist gold excluded), `combat`, `objectives`, `catch_up`, `other` (item income), `souls` (net worth), `soul_sources` (the income gap table, all sources + a footnote that net worth runs ~1% over the sum, the game credits sell refunds etc. to no source), or any raw snapshot field (`creep_kills`, `denies`, `player_damage`, ...).

## Aggregate questions → parquet + polars

Prefer `deadlock export` + polars over looping protobufs for win rates, damage totals, souls curves, item timing. Tables rebuild automatically whenever a data command archives new matches, so run a quick `deadlock history` first and the tables are guaranteed fresh; `deadlock export` forces a full rebuild (needed after changing `export.py`). `--archive`/`--parquet` point any command at non-default dirs. Tables in `~/.local/share/deadlock-matches/parquet/`:

- `matches` (has `average_badge_team0/1` — each team's average skill rating as a badge level, tier * 10 + level, 95 = Phantom 5; null when the protobuf omits it. `queries.skill_rating("average_badge_team0")` maps to labels. NO per-player skill rating exists anywhere in the metadata — "only you can see your Skill Rating" per the in-game help. lobby averages in thin queues can sit well below a player's real badge — never present lobby average or deadlock-api mmr-history as the player's skill rating), `players` (has `hero`, `won`, `lane` — starting lane color, yellow = west / blue = center / green = east, geometry-verified against movement; `assigned_lane` keeps the raw 1/4/6 ids — and `mvp_rank` — the post-game awards: 1 = match MVP, always a winner; 2-3 = Key Player, 3 usually the best loser; 0 = no award. The protobuf also carries per-player `accolades` (the award stat cards, id/value/tier) — deliberately not exported; decode inline if ever needed)
- `stats` — cumulative snapshots, so `max()` per match ≈ final value, with verified caveats: snapshot `kills` drifts from the scoreboard in ~32% of player-games (±1 to ±4, BOTH directions, so it's not one mechanism; checked 2026-07-07 over 824 player-games) — counting `deaths` rows by `killer_account_id` matches the scoreboard in 822/824, so that's the kill source `match_intervals` uses; snapshot `deaths` also counts Rejuvenator self-revives, which the scoreboard doesn't (1-3 extra in ~26% of player-games; 93% of extra ticks follow an own-team Rejuv claim, carry no `gold_death_loss`, and have no `death_details` entry — the `deaths` table, exported from `player.death_details`, is the record that matches the scoreboard exactly), `net_worth` can trail the scoreboard by a few souls when the last snapshot lands before match end, and `creep_kills` is lane creeps only — the scoreboard's `last_hits` counts creeps + neutrals + more, so never compare snapshot creep_kills to a "last hits" figure (top-level `player.last_hits` is the real one). Snapshot timestamps also skew a few seconds early against event times (a death at t=182 lands in the t=180 snapshot) — use ~10s tolerance when bucketing events into snapshot windows. Protobuf `gold_*` renamed `souls_*`. Accuracy = `shots_hit / (shots_hit + shots_missed)`, headshot rate = `hero_bullets_hit_crit / (hero_bullets_hit + hero_bullets_hit_crit)`
- `soul_sources` — per income source per snapshot (`source_name` = troopers/jungle/breakables/...). The in-game number is `souls + souls_orbs`, ALWAYS sum both — `souls` alone undercounts troopers by the orb-confirm portion (~40%; verified against the in-game source breakdown of one of his matches, every line exact). `timeline.py` already sums both, this applies to ad-hoc polars
- `item_events` — buys with names/cost/tier; `attribution` marks how an item's value shows up: `proc` = has its own damage rows (Scourge, Escalating Exposure), `stat` = never appears as a source, value hides inside other rows (Boundless Spirit, Echo Shard). `cost`/`tier`/`slot` resolve as-of match time from dated asset snapshots (`assets_date` says which; null = no history covered that match yet), so a balance patch doesn't reprice history
- `damage` — per dealer/source/target; `stat` names the figure (damage/healing/mitigated/...), `category` splits screen-level `total` rows ("Bullet", "Ability", "Melee") from `gun`/`ability`/`item` detail rows — summing totals with details double-counts. `delivery` groups detail rows for gun-vs-spirit questions: `gun`, `gun_proc` (on-hit items like Mystic Shot/Headhunter/Toxic, even when spirit-typed), `ability`, `spirit_proc`. Gun headshots are the `_crit` source ("Promises Kept (crit)"). Rows with null `target_account_id` are NON-PLAYER targets (creeps/objectives, raw slot 0) — filter `target_account_id.is_not_null()` for hero damage, ALWAYS, or farm damage inflates every source (creep headshots once made gun-crit look 9× body); hero-only detail sums reconcile with snapshot `player_damage`. Healing rows (`stat == "healing"`): NO base hero regen or fountain regen exists anywhere (verified 2026-07-07, `player_healing` == source sum in 824/824 player-games), item regen IS included and credited to the item (Fortitude, Radiant/Mystic Regeneration), and a source in a player's block does NOT imply ownership — Spirit Shredder Bullets grants allies spirit lifesteal so its class lands in non-owner blocks, and Ivy's Kudzu tether splits credit between Ivy and each tethered player
- `damage_sources` — the damage table's sources over time, cumulative per (dealer, source, stat) sample like the in-game damage graph. Summed over targets with a `vs_heroes` split instead of per-target rows; same `category`/`delivery` columns, so keep the total-vs-detail filter. Samples are sparse (~3 minutes apart plus match end) and the protobuf arrays are RIGHT-aligned to `sample_time_s` — the export already handles the alignment. Final sample == the `damage` table value; `queries.damage_intervals` diffs it into the view behind `deadlock match --damage`, which reproduces the in-game graph tooltip exactly
- games from other players: `deadlock download --hero X` writes the SAME tables to the sibling `parquet-players/` dir (top mains + config-selected players; api json is field-identical to the local decode, so every query pattern here applies unchanged). Before running it, check whether coverage is already fresh — another session or agent may share these dirs and have just downloaded: `scan("downloads", players.PARQUET_DIR).group_by("player").agg(pl.col("downloaded_at").max(), pl.col("match_id").max())` (join matches for the latest game date); only download if the window you need is missing. Re-runs skip persisted match bodies but still hit leaderboard + match-history endpoints and rebuild every table. Query with `queries.scan(table, players.PARQUET_DIR)`. Its extra `downloads` table is the provenance: which tracked player brought each match in, rank/region at download time, `downloaded_at` = patch era (null rank = selected in config, not on the leaderboard). The tables are a chosen sample, not the full history of those players — check `downloaded_at` before comparing across patches. `players.tracked_player_games(["somename"], hero="Mirage")` does the downloads→players→matches join for you (the tracked player's own rows among all 12 per match, names case-insensitive, local `day` included)
- `objectives` — one row per team objective (Guardian/Walker/Base Guardians/Shrine/Patron/Weakened Patron) with `team`, `lane` (color, derived empirically: engine lane ids 1/3/4 = yellow/blue/green, verified three ways against attacker positions 2026-07-07), `destroyed_time_s` (null = survived), `first_damage_time_s`, and the player/creep damage split. Backs the `deadlock match --teams` log
- `mid_boss` — one row per midboss (Rejuvenator) kill: `destroyed_time_s`, `team_killed`, `team_claimed` (differs from team_killed when stolen). The in-game reward has been multi-part across patches (3 dropped crystals in mid-2025, later one crystal granting 3 shared revive credits) but the protobuf only ever records ONE claiming team per boss kill — a split pickup is not representable, so never present team_claimed as "got all the rejuvs". Claims per team is the only trustworthy "rejuv metric"; revives *consumed* (`max(snapshot deaths) - scoreboard deaths` per player) is deliberately NOT exported — 7% of those ticks provably can't be rejuv revives (players with more ticks than own-team claims), so don't present it as a rejuv count
- `movement` — OPT-OUT via the config exclude list (the starter config excludes it). ~330KB and ~26k rows per match, ~85% of export time before vectorization. If movement.parquet is missing, `queries.table_exists("movement")` is False and `deadlock deaths` drops its context columns instead of failing. Every player's per-second track from `match_info.match_paths`: `x`/`y` world units, `health_percent` (0-100, 0 while dead), `combat_type` (out/player/enemy_npc/neutral), `move_type` (normal/ability/ability_debuff/ground_dash/slide/rope_climbing/ziplining/in_air/air_dash). LEFT-aligned, unlike the damage matrix: sample index = game second (verified against death positions, median error ~209 units at offset 0 vs ~8000 one second off); trailing samples past `duration_s` are end-screen noise and already dropped at export. Positions are quantized to a per-player bounding box (14-bit), so expect ~200-unit jitter; there is no z. Velocity = distance between consecutive seconds; clamp respawn/zipline teleport spikes before averaging. Movement-tech profiles (slide%, dash/min, air-dash/min) vary strongly BY HERO — normalize per hero before comparing players
- `deaths` — one row per death from `player.death_details`: `game_time_s`, `time_to_kill_s`, `death_duration_s` (respawn timer), `killer_account_id` (null = non-player), death `x`/`y`/`z` and `killer_x`/`y`/`z`. This is the death record that matches the scoreboard (snapshot `deaths` overcounts, see `stats` above). Join to `movement` at `game_time_s` to count allies/enemies within radius at the moment of death (~2000 units = in the fight; enemies with `combat_type == "player"` in the preceding seconds were participants, not bystanders)

Start ad-hoc polars from `queries.py` instead of re-writing the boilerplate — `scan("damage")` lazy-reads a table by name, `my_games()` is the players table filtered to the config accounts and joined to matches, with `start_local`/`day` columns already in your timezone, `daily_record()` is the per-day W/L frame behind `deadlock winrate`, `item_buys("Echo Shard")` is your purchases with `buy_n` order within the match ("bought it as my 6th item"; `item_buys(tier=4)` keeps one shop tier with buy_n unchanged — tier is a real assets label (`item_tier`), 1:1 with cost 800/1600/3200/6400, no 4800 tier exists: 4800 is only the incremental outlay when a 1600 component upgrades into a 6400 item, and the buy row lands at upgrade time at full cost), `item_games("Echo Shard", "Mirage", since="2026-06-30")` is one row per game with the first buy time, buy order (`buy_n`), same-tier order (`tier_buy_n`), first same-tier purchase (`first_tier_item`/`first_tier_time_s`), `is_first_tier_item`, `owned_s` (ownership windows summed, a sold buy's window ends at the sell time), item damage, and `dealt_after_buy` (your hero damage while owning it, the denominator for `percent_of_hero_damage`) joined in (nulls = not built for the item's own buy/order columns, sold buys still count as built, `since` caps to a patch window, backs `deadlock item`), `hero_damage()` is the damage table pre-filtered to detail rows on hero targets (the safe base for any per-source sum; `stat=` picks healing/mitigated/...), `final_stats()` is the final snapshot per match-player with hero/won joined and `accuracy`/`headshot_rate` computed, `team_damage_ranks()` ranks every player's final hero damage within their team per match (`top_team_damage` flags the damage chart top — "am I top damage on my team"), `ability_upgrades()` is ability unlocks/upgrades in spend order with the level and soul requirement for each unlock or cumulative AP spend, `hero_scaling()` is the per-hero-per-level reference frame (base_health, spirit_power, required_souls) for joining against snapshot `level`, `skill_rating(column)` maps a badge level column to labels ("Emissary 4"), `my_deaths()` is deaths joined to your games (hero/won/day), `death_context(radius=2000)` adds allies/enemies/solo/outnumbered at the death second (raises unless movement is exported — check `table_exists("movement")` first), `snapshot_players(hero)` is your games as timeline-ready blocks read from parquet (feeds timeline.compare without looping protobufs — `deadlock compare` uses it for the your side since 2026-07-07), `match_intervals(match_id, account_id, interval_s=300)` is one player's match as per-interval gains (souls/kills/deaths/assists/damage/damage_taken/obj_damage/healing/heal_prevented/creeps/neutrals/denies + souls_min, diffed from the cumulative snapshots; kills and deaths counted from the deaths table instead, snapshot kills/deaths both drift from the scoreboard — backs `deadlock match`), `damage_intervals(match_id, account_id, interval_s=300, stat="damage")` is one player's damage to heroes as per-source interval gains from the damage_sources table (detail rows only, ordered by match total — backs `deadlock match --damage`), `source_intervals(games, interval_s=300, stat="damage")` tracks the same data across multiple matches at once (games = any frame with match_id/account_id columns, e.g. my_games or tracked_player_games rows; same per-source forward-fill semantics, plus a `full` flag for whole windows; use `stat="healing"` for healing — NEVER sum cumulative damage_sources across sources per timestamp yourself, each source samples at its own times so the sum sawtooths and undercounts, ~55% low when tried 2026-07-08), `team_intervals(match_id, interval_s=300)` is both teams' souls gained per interval with the running lead (team 0 minus team 1 — backs `deadlock match --teams`), and `movement_profile()` is per-(match, player) movement metrics (slide/dash/air percents, distance, stationary percent, farm pace — hero-normalize before comparing players):

```python
from deadlock_matches import queries

queries.my_games().group_by("hero").agg(pl.len().alias("games"), pl.col("won").mean()).collect()
```

Keep ad-hoc analysis cheap — one exploratory session cost ~5 scripts and 3 avoidable errors before these rules existed:

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
- `Item.properties` has the actual stat grants ({tech_power: 18, bonus_health: 75, ...}, negatives are real tradeoffs like Glass Cannon's -13% health); weapon records in abilities.json carry `weapon` gun stats (bullet_damage, clip_size, falloff/crit ranges, dps). Weapon distances are game units (inches): divide by 39.37 (`cli.cards.UNITS_PER_METER`) for the meters the game shows — Promises Kept falloff 787→2264 units = the in-game card's 20m→58m (verified against the card). Ability `properties` distances are already meters. Known gap: Vyper's in-game "Crit Bonus Scale: -30%" exists nowhere in the assets API (the gun record says the standard 1.65 crit bonus, and no -30/0.7 field exists in any Vyper record, checked 2026-07-07) — don't hunt for it, and don't confuse it with `crit_damage_received_scale` (incoming crits: Seven 0.45, Mo & Krill 0.8, Rem 0.9); `Hero.scaling_stats` is spirit scaling of base stats (12 heroes, e.g. Vindicta bullet damage +0.022/spirit)
- ability tuning numbers are on `Ability` too: `properties` (base values, unit strings like "20m" already parsed to numbers), `scaling` (which stat a property scales with and by how much), `upgrades` (per-tier bonus entries; `type: add_to_scale` changes scaling, not the base). `stat(name, tier)` and `spirit_scale(name, tier)` do the tier math — verified against deadlock.wiki for Dust Devil (65 base, +60 at T1, scale 0.3 → 1.3 at T3). Lookups: `ability_by_name(name, hero_id)` (raises ValueError on names owned by several heroes — every hero has a "Melee"), `for_hero(hero_id)`, `hero_gun(hero_id)`
- hero level scaling is on `Hero` too: `level_up` (per-boon stat increments), `levels` (soul thresholds per level), `purchase_bonuses` (shop tier bonuses), and helpers `base_health(level)`, `spirit_power(level)`, `level_for_souls(souls)` — snapshot stats tables carry each player's `level`, so these compute expected base health/spirit at any point in a match
- breakpoint questions ("what's my health at 25k souls") are built in: `Hero.stats_at(souls)` / `boon_stats(level)` return level, health, spirit, bullet damage bonus, light/heavy melee and ability points/unlocks; `deadlock hero <name> --souls N` (or `--level N`) prints it with gun dps, `deadlock ability <name> [--hero X]` prints ability numbers with a section per tier (the game's tier text plus before -> after values from `Ability.tier_descriptions` and the tier math). Melee boons: the per-boon melee increment applies to light, heavy keeps the hero's base heavy/light ratio (mostly 2.32; wiki-confirmed, Mirage +1.58 light / +3.67 heavy per boon)
- `Hero.cost_bonuses` / `investment_bonus(slot, spent)` is the shop's souls-invested bonus curve (the graph above each category). The steps are deliberately uneven: 4,800 invested is a designed power spike in every category (spirit +19 spirit power vs +4/+7 neighbors, weapon +28%, vitality +18), and spirit spikes again at 28,800 (+25)
- patch drift: asset-derived numbers describe the CURRENT patch. `deadlock assets` keeps a dated snapshot history (`~/.local/share/deadlock-matches/assets/<date>/`); the export prices `item_events` as-of match time from it, but `Hero` helpers and `hero_scaling()` are always current — rebuilds print a warning (via `queries.stale_hero_matches`) listing matches whose recorded max_health the current base stats can't explain. Treat the derived hero numbers for those matches with suspicion; observed snapshot columns stay trustworthy
- no cast events exist ANYWHERE in the metadata: `player.ability_stats` is only the self-counting items/abilities (Trophy Collector trophies, Glass Cannon stacks, Sticky Bomb bonus, Restorative Locket charges, Guided Owl/Assassinate counters — 11 distinct ids over 69 matches, checked 2026-07-07), and `custom_user_stats` is accuracy/bullet figures. Active item presses (Debuff Remover), stuns, and debuff windows live only in replay demos, which nothing here parses — don't promise cast counts
- `match_mode == 1` is ranked; hero_id maps to names via `heroes.py`
- api.deadlock-api.com is the same data: `v1/matches/{id}/metadata` returns the identical `match_info` we decode (cross-checked field-for-field, zero diffs), so it's ground truth for decode changes AND a backfill source for matches Steam evicted before we archived them. `v1/players/{id}/match-history` scoreboard fields equal the protobuf top-level player fields exactly (win = `match_result == player_team`); very recent matches lag there by hours, so the local cache is fresher

## Module map

Modules are organized by data source, not by layer: `queries.py` answers questions about YOUR games from the local parquet (works offline); `players.py`/`meta.py` answer questions about other players / the global item meta from the deadlock-api (network via `api.py`, or its warm cache). New analysis helpers go where their data comes from; code mixing both worlds (like `compare`) belongs in the `cli/` package.

Everything in `src/deadlock_matches/`:

- `extract.py` — cache walking, archive sync, protobuf decode (`iter_matches`, `archive`, `load`), local Steam accounts (`steam_accounts`)
- `cli/` — the `deadlock` entry point, one module per command group: `main.py` (parser, dispatch, `schema`), `data.py` (`history`, `download`, `export`, `assets` plus the archive sync), `performance.py` (`compare`, `winrate`, `deaths`, `movement`), `items.py` (`item`, `builds`), `cards.py` (`hero`, `ability`)
- `config.py` — config.toml reading and the starter file (`config_accounts`, `config_account_names`, `format_accounts`, `config_players`, `config_exclude`, `config_timezone`, `ensure_config`)
- `export.py` — parquet tables (`build_tables`) plus the `delivery`/`attribution` classifiers
- `schemas.py` — the table models: one class per parquet table, dtype + description per column
- `queries.py` — polars helper functions: `scan(table)`, `my_games()` (accounts + matches + local day), `daily_record()` (per-day W/L + net wins, `by="week"`/`"month"` rolls up), `item_buys(item, tier=)` (your purchases with buy order), `item_games(item, hero=)` (one row per game with buy timing/order, ownership, and item damage), `hero_damage()` (detail damage rows on hero targets, safe to sum), `final_stats()` (final snapshot per match-player + accuracy/headshot rates), `team_damage_ranks()` (final hero damage ranked within each team), `match_intervals(match_id, account_id)` (per-interval gains behind `deadlock match`), `damage_intervals(match_id, account_id)` (per-source damage gains behind `deadlock match --damage`), `source_intervals(games, stat=)` (source intervals across multiple matches), `team_intervals(match_id)` (souls per team + lead behind `deadlock match --teams`), `hero_scaling()` (per-level base stats), `skill_rating(column)` (badge level → skill rating label), `stale_hero_matches()` (patch-drift tripwire)
- `assets.py` — downloads heroes/items/abilities json from the assets API
- `damage.py` — per-source damage from the damage matrix
- `timeline.py` — per-minute cumulative curves, medians, interval rates
- `api.py` — deadlock-api HTTP client with disk cache (`get_json`), the only network code; its docstring lists every endpoint in use and which function wraps it — keep that list current when adding endpoints
- `players.py` — other players: leaderboard → top mains of a hero → their builds/timelines, plus the parquet-players materialization (`download_matches` → `write_player_tables`) and `tracked_player_games(names, hero=, since=)` (tracked players' own rows joined to players/matches with local day, names matched case-insensitively — the downloads→players→matches boilerplate for comparing against specific tracked players)
- `meta.py` — item win-rate/synergy analytics on api data
- `heroes.py` / `items.py` — id ↔ name mapping from the assets API
- `skill_rating.py` — badge level → skill rating label (`label(52)` = "Ritualist 2", tiers from `data/skill_rating.json`, refreshed by `deadlock assets`)
- `abilities.py` — damage-source class_name → current display name (`label()`; engine names like mirage_tornado never change, display names do), plus ability tuning numbers (`Ability.stat`/`spirit_scale` tier math, `ability_by_name`, `for_hero`, `hero_gun`)
- `gen/` — compiled protos, checked in and never regenerated by hand; `protos/` (repo root) — Valve sources
