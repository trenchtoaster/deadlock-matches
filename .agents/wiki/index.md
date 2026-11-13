# Deadlock matches knowledge

This directory is the version-controlled knowledge of the project. It is not specific to one agent. The skill in `.agents/skills/deadlock-matches/` holds the procedures, and its `references/` link points at this directory. An installed user gets a copy of both from `deadlock skill install`, so a page must stand on its own without the repository.

Use this index for routing and read only the pages you need. The CLI commands and the `queries` helpers already apply every pattern below. Read a pattern page before you hand-write polars against a table that no helper covers. Read a contract page before you change the code it describes.

Every entry carries a `First seen` date. A date of 2026-07-08 means the entry was present at the first commit of the repository and predates the git history. The page frontmatter carries `last_confirmed`, the date of the last commit that edited the page's source text.

Add a pattern only when the conclusion is reusable, the cause is established, and the entry names the evidence and the condition for a recheck. A one-off analysis with no reusable conclusion stays out.

## Patterns

Patterns are the verified traps in the data, one page per table or subsystem. Each entry names the view or helper that already applies it.

- [Matches and players](patterns/matches-and-players.md): a filter on `match_mode` alone mixes Street Brawl into Standard, because the two mode enums are separate wire fields. The team badge averages read `0/0` after build 6652. An abandon flag does not mean the player stayed gone, and the accolade-only stats exist in no other table. `my_games`, `record_games`, `abandon_record`, and `unscored_record` apply the rules.
- [Ranked](patterns/ranked.md): `match_mode 1` was the ranked queue before build 6652 and is the unranked queue after it, so `ranked_type` is the discriminator. Rank Points sit on one flat scale of 7,000 per tier, and a badge derived from points is wrong. `record_games` splits net points into results, win-streak bonuses above the 300 base grant, and shield savings. `matches.rank_interval` splits the seasons, the CLI reads the current season by default, and `--season` picks another. Season 2 pays a 350 base grant on a 6,500 point tier. `deadlock rank`, `record_games.net_points`, and `skill_rating_asof` apply the rules.
- [Stats snapshots](patterns/stats.md): `max()` over the snapshots is wrong, because net worth and the power columns fall on a death loss or a sale. Snapshot kills and deaths drift from the scoreboard through the Rejuvenator, and samples land every 3 minutes then every 5. Take the last sample through `stat_snapshots`, `final_stats`, and `match_intervals`.
- [Soul sources](patterns/soul-sources.md): the in-game figure is `souls + souls_orbs`, because the orb portion is a separate deniable quantity. Source 7 is team-shared deny income, not personal denies, and gross souls are not net worth. `soul_source_games` and the soul helpers apply the rules.
- [Item events](patterns/item-events.md): a `flags=1` row is a component consumed by an upgrade, not a sell, and prices resolve as of match time from the dated snapshots. No 4800 tier exists. A corrupted buy looks like a normal buy, because no wire field marks it. `item_buys`, `item_games`, and `item_events_effective` apply the rules.
- [Damage tables](patterns/damage.md): `damage_sources` and `damage_targets` are cumulative timelines, so a plain sum overcounts about 5 times. `damage` is the totals table, total rows and detail rows double count together, a null target is farm, and two stat types arrived on 2026-10-20. `damage_source_games`, `hero_damage_games`, `source_totals`, and the interval helpers apply the rules.
- [Objectives and mid boss](patterns/objectives-and-mid-boss.md): the mitigation fields are zero on every objective, and the protobuf records one claiming team per boss kill. No row records a Rift win or an Urn delivery. Both come from treasure gains and decode only on the 2026-06-30 build. `with_objective_labels` and `deadlock match --teams` apply the rules.
- [Movement and deaths](patterns/movement-and-deaths.md): the movement track is left-aligned and quantized to about 200 units, unlike the damage matrix, and profiles vary by hero. `movement` is opt-out while `movement_intervals` is always built, and `deaths` is the record that matches the scoreboard. `movement_games`, `movement_profile`, and `death_context` apply the rules.
- [Custom stats](patterns/custom-stats.md): counter ids are registered per match, so a name lands at different ids in different games. The `Bullet Stats` values are percents and cannot be diffed, parries include Counterspell blocks, and incoming fire has no per-enemy split. Statue pickup times exist only from build 6712, so an empty timeline is not zero pickups and `buffs.count` stays the total. `combat_games`, `queries.custom_stats`, `buff_intervals`, and `deadlock match --buffs` apply the rules.
- [Tracked players](patterns/tracked-players.md): the downloads ledger holds more than the comparison pool, because old `--account` and `--match` rows stay forever. Comparisons read only the accounts under `[players.<Hero>]`, and the pool is ranked play by default. `pool_games`, `pool_members`, and `tracked_player_games` apply the rules.
- [Steam cache and API](patterns/steam-cache.md): the cache evicts by LRU churn at 10,000 entries, not by age, and new entries are Zstandard despite the `.bz2` suffix. The archive is the only irreplaceable data, and analytics counts drift between fetches because each flag set is its own cached URL. `iter_matches`, `download_metadata`, and `api.get_json` apply the rules.
- [Assets](patterns/assets.md): item names mislead and descriptions do not, Vyper's crit scale exists nowhere in the API, and no cast events exist in the metadata. The weapon and melee formulas were measured in the sandbox, and the history versions every patch era. `purchase_bonuses` is empty from build 6712, which also adds four statue families and nine unselectable hero ids. `deadlock hero`, `deadlock ability`, and the `Hero`, `Item`, and `Ability` helpers apply the rules.

## Contracts

Contracts describe a stable interface. Read the matching page before you touch the code it describes.

- [Commands](contracts/commands.md): every CLI command and the question it answers, the rules that `--help` does not carry, and the `match` view flags.
- [Parquet tables](contracts/tables.md): the table list, the hive layout, read-time labels, the schema drift and rebuild rules, and the engine and ordering rules.
- [Storage](contracts/storage.md): where the config, the archive, the parquet stores, the API caches, and the Steam cache live.
- [Match metadata](contracts/match-metadata.md): the protobuf shape, which wire field feeds which table, alignment, and ids.
- [Queries](contracts/queries.md): the public surface of the `queries` package. The one catalog to keep current when a helper changes.
- [Module map](contracts/module-map.md): what each module under `src/deadlock_matches/` owns.

## Guides

Guides hold the procedures that the skill body routes to.

- [Config and accounts](guides/config.md): how `[accounts]`, `--account`, and the `[players.<Hero>]` pool decide whose games a command reads.
- [Analysis](guides/analysis.md): ad-hoc polars through `queries.summarize()`, the four caveats that bite most, the scratch-script rules, the results table, and the data paths.

## Maintenance

Add or revise an entry in the same commit as the code or the finding that motivated it. Give a new entry a `First seen` line with the commit date. Update the page's `last_confirmed` when you edit it. Keep an entry under 30 lines. When a fix removes a trap, delete the entry and record the removal in the log. Update the summary line in this index when the page changes. The summary names the trap, the cause, and the helper that applies the fix, so an agent can judge relevance without opening the page.

Append a line to [log.md](log.md) whenever a page or the skill changes. When a skill rule changes, update the matching row in the skill's `PURPOSE.md`. Copy the result to `src/deadlock_matches/agent/skills/deadlock-matches/references/`, because the sync test compares the two trees byte for byte.
