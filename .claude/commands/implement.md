---
description: Implement the approved plan for the current task, committing each atomic unit
argument-hint: "<task id>"
allowed-tools: Read, Glob, Grep, Write, Edit, Bash
model: sonnet
---

Read `CLAUDE.md` and `.tasks/$ARGUMENTS/plan.md`.

The plan is approved and authoritative. Implement exactly what it specifies and
nothing more. If you believe the plan is wrong or incomplete, stop and say so
rather than improvising.

Rules you will be reviewed against:
- No comments anywhere. Names carry the meaning.
- `mypy --strict` and `ruff check` must pass.
- Tests from the plan are written in this branch, not deferred.
- Layer boundaries in CLAUDE.md section 6 are not crossed.
- Nothing constructs its own collaborators outside `composition_root.py`.

Work through the commit sequence in the plan in order. After each unit run
`make fmt lint type test`, then commit with the exact message from the plan and
push.

When the sequence is complete, update `.tasks/$ARGUMENTS/state.md` to
`phase: implemented` and stop. Do not merge. Do not open a pull request.
