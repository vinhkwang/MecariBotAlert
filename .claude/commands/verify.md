---
description: Run every quality gate and report pass or fail, nothing else
allowed-tools: Bash(make:*), Bash(git status:*), Bash(git diff:*), Read
model: haiku
---

Run, in order, and report the result of each:

```
make fmt
make lint
make type
make test
```

Then check and report:
- Any comment characters added in the diff against `main` in `src/`.
- Any import of `infrastructure` from `domain/`, `application/` or `web/`.
- Any construction of a concrete adapter outside `composition_root.py`.
- Whether the working tree is clean and the branch is pushed.

Print a short pass/fail table. Fix nothing. Explain nothing. Stop.
