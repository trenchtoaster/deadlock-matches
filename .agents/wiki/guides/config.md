---
status: active
scope: how `config.toml` picks your accounts, tracked players, the comparison pool, and the time zone
first_seen: 2026-07-08
last_confirmed: 2026-10-02
---

# Config and accounts

`config.toml` sets the defaults. `deadlock config` prints its path, and [Storage](../contracts/storage.md) describes the file.

- "your games" is the union across all accounts in `[accounts]`. `--account` (comma separated) overrides per invocation and takes config names as well as ids (`--account main`), matched case insensitively. Report headers print the names (`config.format_accounts`)
- `--account` also takes a tracked player name from `[players.<Hero>]` or any downloaded account id. `history`, `match` (latest-game form), and the damage, healing, souls, combat, and movement twins then read that player's downloaded games from the players store. `cli.main.resolve_store` flips when every account named is not in config and is in the downloads ledger. A mix of yours and tracked stays on your tables, where the tracked games do not exist. `[accounts]` names win a name collision
- when `[accounts]` is empty, use `deadlock accounts`, which lists the Steam accounts on this PC that ran Deadlock and prints a paste-ready `[accounts]` block, and offer to fill `config.toml` in from it
- `--hero` is always explicit. Take it from the question or the user's recent `history` output
- the `[players.<Hero>]` tables are the comparison pool. `compare`, `builds`, and the tracked part of `item` read only downloaded games whose account id sits in the table, resolved at query time (`players.pool_members`, `pool_games`, `pool_builds`). The pool readers enforce ranked play of the current season at read time by default, and `--season`, `--standard`, `--all`, `--placement`, `--street-brawl`, or `--private-lobby` selects one mode instead. Deleting a line removes the player from every comparison without touching data. A bare `deadlock download --hero X` downloads exactly these players' Ranked games. The leaderboard is never auto-downloaded. Read the table through `config.config_players("Mirage")` for ad-hoc analysis. Never hardcode or commit player names or ids
- group matches into local days with `config.config_timezone()`. `start_time` is UTC, so call `convert_time_zone()` before `.dt.date()`
