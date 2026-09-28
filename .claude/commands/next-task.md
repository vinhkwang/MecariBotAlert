---
description: Pick the next unblocked task, create its branch, write an execution plan, then stop for approval
argument-hint: "[optional task id, e.g. T07]"
allowed-tools: Read, Glob, Grep, Bash(git status:*), Bash(git branch:*), Bash(git log:*), Bash(git worktree:*), Bash(git checkout:*), Write
model: opus
---

Read `CLAUDE.md` and `docs/TASKS.md`.

If a task id was given in `$ARGUMENTS`, use it. Otherwise choose the lowest-numbered
task whose status is `todo` and whose every dependency is `merged`.

Then:

1. Confirm the dependencies are actually merged into `main`, not merely planned.
   If any is not, say so and pick a different task.
2. Create the branch named in the task row. Do not switch branches if the working
   tree is dirty; report that instead.
3. Write `.tasks/<TASK_ID>/plan.md` containing, and nothing else:
   - **Goal** in one sentence, taken from the task row.
   - **Files** to create or change, full paths.
   - **Public interfaces** added, with exact signatures.
   - **Patterns** applied and why, referencing CLAUDE.md section 6.1.
   - **Test cases**, named, each with the behaviour it pins down.
   - **Commit sequence**, one Conventional Commit line per atomic unit.
   - **Out of scope** for this task, so the implementer does not drift.
4. Write `.tasks/<TASK_ID>/state.md` with a single line: `phase: planned`.

Do not write any production code. Do not touch files outside `.tasks/`.

End by printing the plan and asking the human to approve, amend or reject it.
Then stop.
