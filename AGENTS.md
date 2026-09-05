# Agent notes

The agent skill lives in `.agents/skills/deadlock-matches/SKILL.md`. It holds the CLI workflow, the config handling, and the query rules. Read it before you answer a match question or extend the tooling. `.claude/skills/deadlock-matches` is a symlink to the same directory, so Claude Code lists the skill by itself.

Project knowledge lives in `.agents/wiki/`. Start at `.agents/wiki/index.md`. The `patterns/` pages hold the dated data traps, one page per table. The `contracts/` pages hold the table layout, the storage paths, the protobuf shape, the `queries` catalog, and the module map. The skill's `references/` link points at the wiki, so a page path in the skill resolves in a source checkout and in an installed copy alike.

The package ships a copy of the skill and the wiki under `src/deadlock_matches/agent/skills/deadlock-matches/`, and `deadlock skill install` writes that copy for an installed user. After you edit anything under `.agents/`, copy the result there. `tests/test_skill_sync.py` compares the two trees byte for byte.

Record a new verified trap as a dated entry on the matching pattern page in the same commit as the fix. Update the summary line in `index.md` when a page changes, and append a line to `.agents/wiki/log.md`. `PURPOSE.md` next to the skill maps each rule to its source page. Update the row when the rule changes.
