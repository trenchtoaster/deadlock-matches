---
status: active
scope: the shape of the protobuf that Steam caches for every match
first_seen: 2026-07-08
last_confirmed: 2026-10-01
---

# Match metadata

## The message

```
CMsgMatchMetaData
  match_details (bytes) -> CMsgMatchMetaDataContents.match_info (MatchInfo)
    match_id, start_time, duration_s, winning_team, game_mode, match_mode
    players[12]: account_id (Steam32), team, player_slot, hero_id,
                 kills, deaths, assists, net_worth, last_hits, denies,
                 items (buy order), stats_type_stat snapshots (3 min
                 through 15:00, 5 min after, plus match end)
```

`extract.load(path)` decodes one archived body. The compiled protos live in `gen/` and are checked in, so a user never runs protoc. The Valve sources live in `protos/` at the repository root.

## Refreshing the protos

First seen 2026-10-01.

The protos were refreshed from SteamDatabase/Protobufs on 2026-10-01. `just protos` compiles the 7-file closure with grpcio-tools and prints the gencode version stamp. That stamp must not exceed the `protobuf` floor in `pyproject.toml`, 6.33.5 on 2026-10-01, because the gencode checks the runtime on import. `protos/README.md` has the steps.

Valve renames enum values without changing their numbers. `k_ECitadelRankedType_*` became `k_eCitadelRankedType_*`, and `k_EHeroXPGrantReason_*` became `k_eGrant_*`. Stored parquet values keep their meaning. The label maps strip an enum prefix as a string, so a stale prefix raises nothing and only leaves a label unstripped. `tests/test_enum_labels.py` guards the match mode, game mode, stat, combat, and move label maps.

Recheck the prefixes after every refresh.

## Closed enums drop new values

First seen 2026-10-23.

The protos are proto2, so every enum is closed. The parser moves a number the enum does not list into the unknown fields, and a packed repeated enum comes back shorter. `source_details.stat_type` lost the new values 6 and 7 that way, fell out of line with `source_name`, and crashed `sync` with an `IndexError`. `build_tables` now raises a `ValueError` that names the match when the two lengths differ. The fix is a proto refresh.

On 2026-10-23 only the two `EStatType` values were added to the vendored file. The upstream copy also adds `boxed_type` options, new imports, and lobby fields. Those were left out because no match table reads them.

## Build 6712 fields

First seen 2026-10-01.

Client build 6712 added three wire fields. Match 108628471 on 2026-09-29 22:25 UTC is the first archived body that carries them, and none of the 1855 older bodies do.

- `MatchInfo.corrupted_penalty_seed` exports as `matches.corrupted_penalty_seed`. It is null before build 6712. It is an opaque seed and joins to nothing.
- `PowerUpBuff.pickup_times_s` and `pickup_stat_values` export as `buff_pickups`. See [Custom stats](../patterns/custom-stats.md).

`MatchInfo.extra_messages` can carry `hero_release_votes`, message type 2 (`CMsgMatchHeroReleaseVotes`). Its categories are match_completed, match_won, and daily_bonus, each with hero votes of slot, hero id, and count. It was empty in every archived body on 2026-10-01, including the five after build 6712, so nothing exports it.

Recheck when a body carries a nonempty `extra_messages` block.

## Where each table comes from

| Wire field | Table |
| --- | --- |
| `match_info` top level | `matches` |
| `players[]` top level | `players` |
| `players[].stats_type_stat` | `stats`, `soul_sources`, `custom_stats` |
| `players[].items` | `item_events` |
| `players[].death_details` | `deaths` |
| `players[].ability_stats` | `stacks` |
| `players[].power_up_buffs` | `buffs`, `buff_pickups` |
| `players[].custom_user_stats` | `custom_stats` |
| `match_info.damage_matrix` | `damage`, `damage_sources`, `damage_targets` |
| `match_info.match_paths` | `movement`, `movement_intervals` |
| `match_info.objectives` | `objectives` |
| `match_info.mid_boss` | `mid_boss` |

## Alignment

The damage matrix arrays are right-aligned to `sample_time_s`. The movement track is left-aligned, with the sample index equal to the game second. The export handles both alignments. See [Damage tables](../patterns/damage.md) and [Movement and deaths](../patterns/movement-and-deaths.md).

## Ids

`account_id` is a Steam32 id. A Steam64 id from a profile URL minus `extract.STEAM64_BASE` (76561197960265728) gives it. The wire `ability_id` is the murmur2 string token of the engine class name, and the assets API uses the same hash. Custom stat ids are registered per match and mean nothing across matches. See [Custom stats](../patterns/custom-stats.md).

## Ground truth

`v1/matches/{id}/metadata` on api.deadlock-api.com returns the identical `match_info`, so it is ground truth for a decode change. See [Steam cache and API](../patterns/steam-cache.md).

## Ad-hoc protobuf reads

The protobuf modules stay the tool for per-match detail that the tables do not carry:

```python
from deadlock_matches import extract

for path in extract.iter_matches():
    info = extract.load(path)
    print(info.match_id, info.duration_s, len(info.players))
```
