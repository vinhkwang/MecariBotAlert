---
description: Apply the findings from the newest review file
argument-hint: "<task id>"
allowed-tools: Read, Glob, Grep, Write, Edit, Bash
model: sonnet
---

Read `CLAUDE.md`, `.tasks/$ARGUMENTS/plan.md`, and the newest
`.tasks/$ARGUMENTS/review-*.md`.

Apply every `blocker` and `major` finding exactly as its `fix` describes. Apply
`minor` findings too unless doing so would exceed the plan's scope.

Do not redesign. Do not refactor anything the review did not raise. Do not add
features. If a finding cannot be applied as written because it conflicts with
another, stop and report the conflict instead of choosing.

Group the fixes into logical commits, run `make fmt lint type test` after each,
and push. Use `fix(<scope>): <what>` messages.

Update `.tasks/$ARGUMENTS/state.md` to `phase: fixed, round: N` and stop.
Re-review is a separate command.
