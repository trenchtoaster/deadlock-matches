# Change log

One line per change to the skill or to a wiki page, newest last. The line says what changed and why. It carries no score. Git holds the diff.

- 2026-07-08: the skill and the table caveats arrive with the first commit. The caveats live in `references/schema-caveats.md`.
- 2026-07-29 to 2026-08-10: the skill grows with each feature, to 96KB after Ranked Season One.
- 2026-09-06: the skill moves to `.agents/skills/deadlock-matches/`. The caveats become this wiki, with one dated page per table and five contract pages. `.claude/skills/deadlock-matches` becomes a symlink.
- 2026-09-06: a cleanup pass splits `cli/performance.py` into four modules and adds `queries/objectives.py`. It renames `players.PARQUET_DIR` to `PLAYERS_PARQUET_DIR` and moves `UNITS_PER_METER` to `queries.movement`. The skill and the wiki follow the renames.
- 2026-09-06: the skill drops from 44KB to 18KB. The command block becomes a table plus command rules, and the `match` flag list keeps only what `--help` lacks. The metric views section of the queries catalog points at `deadlock schema --views`. Twelve facts move into the pattern pages.
- 2026-09-06: the index entries take the trap, cause, fix form. `PURPOSE.md` maps each skill rule to its source, and this log starts.
