---
description: Write or rewrite the execution plan for a task already in progress
argument-hint: "<task id>"
allowed-tools: Read, Glob, Grep, Bash(git status:*), Bash(git diff:*), Write
model: opus
---

Read `CLAUDE.md`, `docs/TASKS.md` and any existing `.tasks/$ARGUMENTS/` files.

Produce or replace `.tasks/$ARGUMENTS/plan.md` using the structure defined in
`/next-task`. If a previous plan exists, state plainly what changed and why.

Write no production code. Print the plan and stop for approval.
