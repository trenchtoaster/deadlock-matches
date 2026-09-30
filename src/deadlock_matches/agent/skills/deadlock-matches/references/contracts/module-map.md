---
status: active
scope: what each module under `src/deadlock_matches/` owns
first_seen: 2026-07-08
last_confirmed: 2026-10-01
---

# Module map

Modules are organized by data source, not by layer. The `queries/` package answers questions about your games from the local parquet and works offline. `players.py` and `meta.py` answer questions about other players and the global item meta from the deadlock-api, through `api.py` or its warm cache. A new analysis helper goes where its data comes from. Code that mixes both worlds, like `compare`, belongs in the `cli/` package.

## Modules

- `extract.py` walks the cache, syncs the archive, and decodes the protobuf (`iter_matches`, `archive`, `load`, `archived_match_bodies`). It also lists the local Steam accounts (`steam_accounts`) and recovers the removed party wire field from old matches (`player_party`).
- `cli/` is the `deadlock` entry point, one module per command group. `main.py` holds the parser, the dispatch, and `schema`. `data.py` holds `history`, `download`, `sync`, `assets`, `skill`, and the archive snapshot. `compare.py` holds `compare`. `match.py` holds `match` and its sections. `winrate.py` holds `winrate`. `games.py` holds `laning`, `deaths`, `damage`, `healing`, `souls`, `combat`, and `movement`. `rank.py` holds `rank` and `season_rules` over the ranked-seasons asset. `items.py` holds `item` and `builds`. `cards.py` holds `hero` and `ability`. `render.py` prints tables through the measure formats.
- `config.py` reads `config.toml` and writes the starter file (`config_accounts`, `config_account_names`, `format_accounts`, `config_players`, `config_exclude`, `config_timezone`, `ensure_config`).
- `export.py` builds the parquet tables (`build_tables`). It is a faithful decode only. Judgment lives in the queries package.
- `schemas.py` holds the table models, one class per parquet table with a dtype and a description per column.
- `queries/` holds the polars helpers over the local parquet and works offline. There is one module per report area (`core`, `delivery`, `labels`, `items`, `records`, `stats`, `games`, `intervals`, `laning`, `movement`, `scaling`, `objectives`) plus `semantic`, the Dimension, Measure, Join, and MetricView machinery behind `summarize`. Every public name is re-exported through `__init__.py`, so callers keep writing `queries.foo`. [Queries](queries.md) is the one catalog to keep current when you add a helper.
- `engine.py` pins the polars engine affinity to streaming at import.
- `assets/` is the assets API package. `snapshots.py` redownloads the bundled data and holds `HISTORY_START`. `store.py` resolves asset files and prefers the writable user store over the bundled seed. `history.py` is the as-of lookup over the committed asset history, and `unnest.py` flattens that history into parquet tables. `heroes.py` and `items.py` map ids to names. `abilities.py` maps a damage-source class name to the current display name (`label`) and holds the ability tuning numbers (`Ability.stat`, `spirit_scale`, `ability_by_name`, `for_hero`, `hero_gun`, `string_token`, `class_by_token`). `skill_rating.py` maps a badge level to a skill rating label (`label`, `label_asof`, `era_labels`). `accolades.py` and `statues.py` read the bundled accolade names and statue magnitudes.
- `damage.py` computes per-source damage from the damage matrix (`damage_from_source`).
- `api.py` is the deadlock-api HTTP client with a disk cache (`get_json`), and the only network code. Its docstring lists every endpoint in use and which function wraps it. Keep that list current when you add an endpoint.
- `players.py` covers other players. It reads the per-hero leaderboard (`hero_leaderboard`, `top_players`) and materializes the tracked-player store (`download_matches` for tracked players or `matches_by_id` for specific match ids, then `write_player_tables`, with `match_info` as the one body loader). It also defines the comparison pool: `pool_members(hero)`, `pool_games(hero)`, `pool_builds(hero)`, and the ad-hoc `tracked_player_games(names, hero=, since=)`. See [Tracked players](../patterns/tracked-players.md).
- `meta.py` computes item win-rate and synergy analytics on API data. `cli/meta.py` is the `meta` command over the public hero trends.
- `paths.py` resolves the data and cache directories per platform.
- `gen/` holds the compiled protos. `protos/` at the repository root holds the Valve sources, and `just protos` regenerates `gen/` from them. See [Match metadata](match-metadata.md).
- `agent/skills/deadlock-matches/` is the bundled copy of the agent skill and this wiki that `deadlock skill install` writes for an installed user. The source of truth is `.agents/` at the repository root, and a test keeps the two in sync.
