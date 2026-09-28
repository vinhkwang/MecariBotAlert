---
description: Final gate before human review, then stop without merging
argument-hint: "<task id>"
allowed-tools: Read, Bash(make:*), Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git push:*), Write, Edit
model: sonnet
---

Confirm all of the following and refuse to continue if any fails:

1. The newest `.tasks/$ARGUMENTS/review-*.md` has `verdict: PASS`.
2. `make fmt lint type test` all pass.
3. The working tree is clean.
4. Every commit message follows Conventional Commits.
5. The branch is pushed to the remote.

Then update the task's row in `docs/TASKS.md` to `status: review` and commit that
change on this branch.

Print a handover summary for the human:
- What changed, in three bullets.
- Which files to look at first.
- Anything the reviewer flagged as `minor` and left unfixed.
- The exact merge command, for the human to run.

**Do not merge. Do not delete the branch. Do not open or approve a pull request.**
Stop here.
