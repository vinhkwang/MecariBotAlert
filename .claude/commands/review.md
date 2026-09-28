---
description: Review the current branch against the plan and write findings for a cheaper model to fix
argument-hint: "<task id>"
allowed-tools: Read, Glob, Grep, Bash(git diff:*), Bash(git log:*), Bash(make test:*), Write
model: opus
---

Read `CLAUDE.md`, `.tasks/$ARGUMENTS/plan.md`, and the full diff of this branch
against `main`.

You are the reviewer. **You do not edit code.** Your only output is a findings
file that a cheaper model will act on without seeing this conversation, so every
finding must be self-contained and unambiguous.

Judge against, in this order:
1. Correctness against the plan and against CLAUDE.md section 7 behavioural rules.
2. Layer violations and pattern violations from section 6.
3. Missing or weak tests, especially tests that assert implementation rather
   than behaviour.
4. Comments present, poor names, unclear control flow.
5. Error handling, resource cleanup, timezone handling, secret leakage.

Write `.tasks/$ARGUMENTS/review-N.md` where N is one higher than the highest
existing review file:

```
verdict: PASS | CHANGES_REQUESTED
summary: <two sentences>

findings:
  - id: F1
    severity: blocker | major | minor
    file: src/path/to/file.py
    anchor: <the exact existing line or symbol to locate it>
    problem: <what is wrong and what it breaks>
    fix: <the precise change to make, specific enough to apply without judgement>
```

Only `blocker` and `major` block the verdict. List `minor` findings but do not
fail the task on them alone.

Update `.tasks/$ARGUMENTS/state.md` to `phase: reviewed, verdict: <verdict>, round: N`.

If this is the third `CHANGES_REQUESTED` on this task, add a section
`escalate:` explaining why you believe the plan itself is at fault, and tell the
human to stop and rethink rather than iterate again.
