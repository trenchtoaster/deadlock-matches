# Change log

One line per change to the skill or to a wiki page, newest last. The line says what changed and why. It carries no score. Git holds the diff.

- 2026-07-08: the skill and the table caveats arrive with the first commit. The caveats live in `references/schema-caveats.md`.
- 2026-07-29 to 2026-08-10: the skill grows with each feature, to 96KB after Ranked Season One.
- 2026-09-06: the skill moves to `.agents/skills/deadlock-matches/`. The caveats become this wiki, with one dated page per table and five contract pages. `.claude/skills/deadlock-matches` becomes a symlink.
- 2026-09-06: a cleanup pass splits `cli/performance.py` into four modules and adds `queries/objectives.py`. It renames `players.PARQUET_DIR` to `PLAYERS_PARQUET_DIR` and moves `UNITS_PER_METER` to `queries.movement`. The skill and the wiki follow the renames.
- 2026-09-06: the skill drops from 44KB to 18KB. The command block becomes a table plus command rules, and the `match` flag list keeps only what `--help` lacks. The metric views section of the queries catalog points at `deadlock schema --views`. Twelve facts move into the pattern pages.
- 2026-09-06: the index entries take the trap, cause, fix form. `PURPOSE.md` maps each skill rule to its source, and this log starts.
- 2026-10-01: the protos refresh from SteamDatabase/Protobufs through the new `just protos` recipe. Match metadata records the enum renames and the build 6712 wire fields, and the module map names the recipe.
- 2026-10-01: statue pickup times arrive at build 6712. Custom stats, the queries catalog, and the skill `--buffs` line drop the claim that buffs carry no timestamps. They point at `buff_pickups` and `buff_intervals`.
- 2026-10-01: Item events records that no wire field marks a corrupted buy. Assets records the empty `purchase_bonuses`, the new statues and heroes, and the true `--backfill` targets. Ranked records the two Season One intervals as an open question.
