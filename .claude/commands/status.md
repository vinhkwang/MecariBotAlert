---
description: Show the task board state and what can be started in parallel right now
allowed-tools: Read, Glob, Bash(git branch:*), Bash(git log:*), Bash(git worktree:*)
model: haiku
---

Read `docs/TASKS.md` and every `.tasks/*/state.md`.

Print three short sections:

1. **In flight** — task id, branch, phase, review round.
2. **Ready now** — tasks whose dependencies are all `merged`, with a note on
   which of them can safely run in parallel because their file sets do not
   overlap.
3. **Blocked** — task id and what it is waiting on.

No prose beyond that. Do not start anything.
