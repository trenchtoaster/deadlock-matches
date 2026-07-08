# Parquet table schema caveats

Per-table columns and verified traps for **hand-writing raw polars**. Read this before querying a table directly when no `queries.py` helper covers what you need. If you are relaying CLI output or reusing a helper, you do not need this file — the command and the helper already apply every caveat below.

Tables live in `~/.local/share/deadlock-matches/parquet/`; `deadlock schema <table>` prints the columns for any of them.

## Tables

- `matches` / `players`:
  - `matches` has `average_badge_team0/1` — each team's average skill rating as a badge level (tier * 10 + level, 95 = Phantom 5; null when the protobuf omits it). `queries.skill_rating("average_badge_team0")` maps to labels. NO per-player skill rating exists anywhere in the metadata ("only you can see your Skill Rating" per the in-game help). Lobby averages in thin queues can sit well below a player's real badge — never present lobby average or deadlock-api mmr-history as the player's skill rating
  - `players` has `hero`, `won`, `lane` (starting lane color, yellow = west / blue = center / green = east, geometry-verified against movement; `assigned_lane` keeps the raw 1/4/6 ids) and `mvp_rank` (post-game awards: 1 = match MVP, always a winner; 2-3 = Key Player, 3 usually the best loser; 0 = no award). Per-player `accolades` (award stat cards, id/value/tier) exist in the protobuf but are deliberately not exported — decode inline if ever needed

- `stats` — cumulative snapshots, so `max()` per match ≈ final value. Verified caveats:
  - snapshot `kills` drifts from the scoreboard in ~32% of player-games (±1 to ±4, BOTH directions, so it's not one mechanism; checked 2026-07-07 over 824 player-games). Counting `deaths` rows by `killer_account_id` matches the scoreboard in 822/824, so that's the kill source `match_intervals` uses
  - snapshot `deaths` also counts Rejuvenator self-revives, which the scoreboard doesn't (1-3 extra in ~26% of player-games; 93% of extra ticks follow an own-team Rejuv claim, carry no `gold_death_loss`, and have no `death_details` entry). The `deaths` table, exported from `player.death_details`, matches the scoreboard exactly
  - `net_worth` can trail the scoreboard by a few souls when the last snapshot lands before match end
  - `creep_kills` is lane creeps only — the scoreboard's `last_hits` counts creeps + neutrals + more, so never compare snapshot creep_kills to a "last hits" figure (top-level `player.last_hits` is the real one)
  - snapshot timestamps skew a few seconds early against event times (a death at t=182 lands in the t=180 snapshot) — use ~10s tolerance when bucketing events into snapshot windows
  - protobuf `gold_*` renamed `souls_*`. Accuracy = `shots_hit / (shots_hit + shots_missed)`, headshot rate = `hero_bullets_hit_crit / (hero_bullets_hit + hero_bullets_hit_crit)`

- `soul_sources` — per income source per snapshot (`source_name` = troopers/jungle/breakables/...). The in-game number is `souls + souls_orbs`, ALWAYS sum both. `souls` is the guaranteed portion; `souls_orbs` is the deniable flying-orb portion you SECURED. Two different quantities, don't conflate them:
  - design ratio (share of trooper bounty placed in the orb): 40% before the 2026-06-30 patch, 50% after (from the patch notes)
  - secured share (`souls_orbs / (souls + souls_orbs)`, what you actually kept): lower, because orbs get denied/missed — his archive medians ~27% before, ~30% after, with individual matches swinging past 40%
  - never pin a fixed figure — the sum-both rule is invariant, the magnitude drifts by patch and by how well the player confirms orbs. `timeline.py` already sums both, this applies to ad-hoc polars

- `item_events` — buys with names/cost/tier. `attribution` marks how an item's value shows up: `proc` = has its own damage rows (Scourge, Escalating Exposure), `stat` = never appears as a source, value hides inside other rows (Boundless Spirit, Echo Shard). `cost`/`tier`/`slot` resolve as-of match time from dated asset snapshots (`assets_date` says which; null = no history covered that match yet), so a balance patch doesn't reprice history

- `damage` — per dealer/source/target. `stat` names the figure (damage/healing/mitigated/...):
  - `category` splits screen-level `total` rows ("Bullet", "Ability", "Melee") from `gun`/`ability`/`item` detail rows — summing totals with details double-counts
  - `delivery` groups detail rows for gun-vs-spirit questions: `gun`, `gun_proc` (on-hit items like Mystic Shot/Headhunter/Toxic, even when spirit-typed), `ability`, `spirit_proc`. Gun headshots are the `_crit` source ("Promises Kept (crit)")
  - ALWAYS filter `target_account_id.is_not_null()` for hero damage — null target = NON-PLAYER (creeps/objectives, raw slot 0). Without it farm damage inflates every source (creep headshots once made gun-crit look 9× body). Hero-only detail sums reconcile with snapshot `player_damage`
  - healing rows (`stat == "healing"`): NO base hero regen or fountain regen exists anywhere (verified 2026-07-07, `player_healing` == source sum in 824/824 player-games). Item regen IS included and credited to the item (Fortitude, Radiant/Mystic Regeneration). A source in a player's block does NOT imply ownership — Spirit Shredder Bullets grants allies spirit lifesteal so its class lands in non-owner blocks, and Ivy's Kudzu tether splits credit between Ivy and each tethered player

- `damage_sources` — the damage table's sources over time, cumulative per (dealer, source, stat) sample like the in-game damage graph. Summed over targets with a `vs_heroes` split instead of per-target rows; same `category`/`delivery` columns, so keep the total-vs-detail filter. Samples are sparse (~3 minutes apart plus match end) and the protobuf arrays are RIGHT-aligned to `sample_time_s` — the export already handles the alignment. Final sample == the `damage` table value; `queries.damage_intervals` diffs it into the view behind `deadlock match --damage`, which reproduces the in-game graph tooltip exactly

- `objectives` — one row per team objective (Guardian/Walker/Base Guardians/Shrine/Patron/Weakened Patron) with `team`, `lane` (color, derived empirically: engine lane ids 1/3/4 = yellow/blue/green, verified three ways against attacker positions 2026-07-07), `destroyed_time_s` (null = survived), `first_damage_time_s`, and the player/creep damage split. Backs the `deadlock match --teams` log

- `mid_boss` — one row per midboss (Rejuvenator) kill: `destroyed_time_s`, `team_killed`, `team_claimed` (differs from team_killed when stolen).
  - the in-game reward has been multi-part across patches (3 dropped crystals in mid-2025, later one crystal granting 3 shared revive credits) but the protobuf only ever records ONE claiming team per boss kill — a split pickup is not representable, so never present `team_claimed` as "got all the rejuvs". Claims per team is the only trustworthy rejuv metric
  - revives *consumed* (`max(snapshot deaths) - scoreboard deaths` per player) is deliberately NOT exported — 7% of those ticks provably can't be rejuv revives (players with more ticks than own-team claims), so don't present it as a rejuv count

- `movement` — OPT-OUT via the config exclude list (the starter config excludes it). ~330KB and ~26k rows per match, ~85% of export time before vectorization. If movement.parquet is missing, `queries.table_exists("movement")` is False and `deadlock deaths` drops its context columns instead of failing.
  - every player's per-second track from `match_info.match_paths`: `x`/`y` world units, `health_percent` (0-100, 0 while dead), `combat_type` (out/player/enemy_npc/neutral), `move_type` (normal/ability/ability_debuff/ground_dash/slide/rope_climbing/ziplining/in_air/air_dash)
  - LEFT-aligned, unlike the damage matrix: sample index = game second (verified against death positions, median error ~209 units at offset 0 vs ~8000 one second off). Trailing samples past `duration_s` are end-screen noise, already dropped at export
  - positions are quantized to a per-player 14-bit bounding box (~200-unit jitter); there is no z. Velocity = distance between consecutive seconds; clamp respawn/zipline teleport spikes before averaging
  - movement-tech profiles (slide%, dash/min, air-dash/min) vary strongly BY HERO — normalize per hero before comparing players

- `deaths` — one row per death from `player.death_details`: `game_time_s`, `time_to_kill_s`, `death_duration_s` (respawn timer), `killer_account_id` (null = non-player), death `x`/`y`/`z` and `killer_x`/`y`/`z`. This is the death record that matches the scoreboard (snapshot `deaths` overcounts, see `stats` above). Join to `movement` at `game_time_s` to count allies/enemies within radius at the moment of death (~2000 units = in the fight; enemies with `combat_type == "player"` in the preceding seconds were participants, not bystanders)

## Games from other players → `parquet-players/`

`deadlock download --hero X` writes the SAME tables to the sibling `parquet-players/` dir (top mains + config-selected players; api json is field-identical to the local decode, so every query pattern here applies unchanged).

- before running, check whether coverage is already fresh — another session or agent may share these dirs and have just downloaded: `scan("downloads", players.PARQUET_DIR).group_by("player").agg(pl.col("downloaded_at").max(), pl.col("match_id").max())` (join matches for the latest game date); only download if the window you need is missing
- re-runs skip persisted match bodies but still hit leaderboard + match-history endpoints and rebuild every table
- query with `queries.scan(table, players.PARQUET_DIR)`. The extra `downloads` table is the provenance: which tracked player brought each match in, rank/region at download time, `downloaded_at` = patch era (null rank = selected in config, not on the leaderboard). The tables are a chosen sample, not the full history of those players — check `downloaded_at` before comparing across patches
- `players.tracked_player_games(["somename"], hero="Mirage")` does the downloads→players→matches join for you (the tracked player's own rows among all 12 per match, names case-insensitive, local `day` included)
