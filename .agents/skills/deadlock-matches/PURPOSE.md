# Purpose

Each row maps a part of `SKILL.md` to the knowledge that motivates it. A rule with no wiki page rests on the CLI help, the code, or a session lesson, and the row says which. Update a row when its rule changes. Delete the rule when its source page drops the trap.

## Sections

| Skill section | Source |
| --- | --- |
| Invoking the CLI | `pyproject.toml` scripts entry and the `uv tool install` setup |
| User config | [Storage](references/contracts/storage.md) and `config.py` |
| Common questions, the table | `deadlock <command> --help` |
| The `match` view flags | The pattern pages each bullet links |
| Aggregate questions | [Queries](references/contracts/queries.md) and [Parquet tables](references/contracts/tables.md) |
| Caveats | [Soul sources](references/patterns/soul-sources.md), [Damage tables](references/patterns/damage.md), [Stats snapshots](references/patterns/stats.md) |
| Ad-hoc rules | Session lessons from 2026-07. The rule text records them |
| Presenting results | Session lessons, no page |
| Where the data is | [Storage](references/contracts/storage.md) and [Steam cache and API](references/patterns/steam-cache.md) |

## Command rules

| Rule | Source |
| --- | --- |
| run `history` first for a match id | `cli/main.py`, the match id argument |
| `match` intervals and `--ago` | `cli/match.py` |
| a match none of your accounts played | [Tracked players](references/patterns/tracked-players.md) and `cli.main.resolve_store` |
| `item --hero` drops the card | `cli/items.py` |
| the track flow and the leaderboard | [Tracked players](references/patterns/tracked-players.md), "The pool is ranked play by default" |
| read a tracked player's games | [Tracked players](references/patterns/tracked-players.md), "Same tables, sibling directory" |
| both sides of `compare` read parquet offline | [Tracked players](references/patterns/tracked-players.md), "The ledger" |
| never hand-roll a win rate | [Matches and players](references/patterns/matches-and-players.md), "Not scored" and "Abandons and reconnects" |
| `winrate --by mode` lifts the mode filter | [Ranked](references/patterns/ranked.md), "`match_mode 1` means two things" |
| `winrate --hero` public rate | `cli/winrate.py` and `cli/meta.py` |
| `winrate` keeps abandoned games | [Matches and players](references/patterns/matches-and-players.md), "Abandons and reconnects" and "Not scored" |
| `rank` window against season | `cli/rank.py` |
| archive gap on `rank` | [Ranked](references/patterns/ranked.md), "Rank Points sit on one flat scale" |
| `laning` counts scored games only | [Stats snapshots](references/patterns/stats.md), "Lane result at the mark" |
| `--hero` required on the archive reports | `cli/main.py`, the `required=True` arguments |
| comeback souls stay in `match --combat` | [Custom stats](references/patterns/custom-stats.md), "Comeback souls" and "Unspent balances" |
| aim percentiles through `queries.aim_rates` | [Queries](references/contracts/queries.md) |
| movement comparison is `compare movement` | `cli/compare.py` |
| `souls --milestones` interpolates | [Queries](references/contracts/queries.md), `cumulative_marks` and `milestone_games` |
| `ability --spirit`, `--melee`, `--weapon` | [Assets](references/patterns/assets.md), "Weapon scaling, sandbox verified" and "Melee scaling, sandbox verified" |
| `meta --hero` and the API windows | `cli/meta.py` and [Steam cache and API](references/patterns/steam-cache.md), "Two API cache tiers" |
| `meta --min-rating` shrinks the boundary bucket | `cli/meta.py` |
| `sync --source api` may not find every game | [Steam cache and API](references/patterns/steam-cache.md), "Eviction is LRU churn, not age" |
| `sync` self-heals the asset history | [Assets](references/patterns/assets.md), "Patch drift and the committed history" |
