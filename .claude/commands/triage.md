---
description: Diagnose a failing test or defect and write a fix direction, without editing code
argument-hint: "<task id> <short description of the failure>"
allowed-tools: Read, Glob, Grep, Bash(make test:*), Bash(git diff:*), Bash(git log:*), Write
model: opus
---

Reproduce the failure described in `$ARGUMENTS`. Read enough of the code and the
test to understand the real cause, not the surface symptom.

Write `.tasks/<task id>/triage-<n>.md`:

```
symptom: <what is observed>
root_cause: <why it happens, at the level of the actual defect>
blast_radius: <what else this touches>
fix:
  - file: <path>
    change: <precise instruction>
verification: <the exact command and expected output that proves it fixed>
regression_test: <the test to add, and what it must assert>
```

Do not edit any source file. The fix is applied by `/fix` or `/implement`.
