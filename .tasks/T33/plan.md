# T33 — VPS deploy and 48h soak

## Goal

Run `deploy/bootstrap.sh`, deploy per `docs/VPS.md`, set up the backup cron,
and open the 48-hour soak.

Work happens in worktree `../mab-T33` on branch `chore/vps-deploy` (created from
`main` at 3cc8162). This is an operations task: no code, no tests, no change to
any tracked file outside `.tasks/T33/`.

## Who does what

The agent has no access to the VPS and no Telegram credentials, and must not
get them. Every command on the VPS is run by the human, in their own terminal
or through `! <command>` in the session. The agent writes the runbook, reads the
output the human pastes back, checks it against the pass criteria below, and
records the result. A failed step stops the run; the agent reports and does not
improvise a workaround (CLAUDE.md §12).

Target machine is the one already used for the spike: VPS Siêu Tốc 1 GB, JP,
AS22439 (`docs/SPIKE.md` §1). No other host is proposed.

## Files

Create (force-added, `.tasks/` is gitignored):

- `.tasks/T33/plan.md` — this file.
- `.tasks/T33/state.md` — phase marker.
- `.tasks/T33/runbook.md` — the exact command sequence for steps R1–R7 below,
  copy-pasteable, with `<vps-ip>` and `<user>` as the only placeholders.
- `.tasks/T33/deploy-log.md` — per step: date (UTC), pass/fail, the decisive
  lines of output. No IP address, token, chat id or SSH key is recorded.
- `.tasks/T33/soak-report.md` — the 48h result against criteria S1–S6.

Change: none. In particular `deploy/`, `docs/VPS.md`, `OPERATOR.md`,
`docker-compose.yml`, `Dockerfile`, `config/` stay untouched. If a step shows
one of them is wrong, stop and report; the fix is a separate `fix/` task.

## Runbook steps

- `R1 bootstrap` — `scp deploy/bootstrap.sh` to the VPS, run as root with the
  user name and public key (`docs/VPS.md` §4). Then, **before closing the root
  session**, open a second terminal and confirm `ssh <user>@<vps-ip>` works
  and `docker run --rm hello-world` succeeds. Pass: both succeed; `sudo ufw
  status` shows only the SSH port; `timedatectl` shows UTC; `swapon --show`
  shows `/swapfile`.
- `R2 checkout` — as `<user>`: `git clone` the repo to `~/mercari-alert-bot` at
  `main` (3cc8162 or later). Pass: `git log -1` matches `main`.
- `R3 secrets` — create `~/mercari-alert-bot/.env` from `.env.example` on the
  VPS itself (typed or `scp` from the human's machine), `chmod 600`. Pass:
  `ls -l .env` shows `-rw-------`; content is never pasted into the session.
- `R4 start` — `docker compose up -d --build`. Pass: `docker compose ps` shows
  `healthy` within 5 minutes; `ss -ltnp | grep 8080` shows `127.0.0.1:8080`
  only; from the human's machine `curl -m 5 http://<vps-ip>:8080` fails.
- `R5 first-run` — through `ssh -L 8080:127.0.0.1:8080`, open the UI, press
  "Gửi alert thử", add the production keyword rules. Pass: test alert arrives
  in Telegram; after the first cycle exactly one initialisation summary arrives
  and no listing alert (baseline suppression, CLAUDE.md §7.3 and §7.12).
- `R6 backup-cron` — install the cron line from `OPERATOR.md`
  (`0 3 * * * .../deploy/backup.sh >> /home/<user>/mab-backup.log 2>&1`; the
  `/var/log` path in `docs/VPS.md` §6 is not writable by `<user>`, so the
  `OPERATOR.md` path is used). Run `./deploy/backup.sh` once by hand. Pass:
  `backups/listings-<UTC>.db.gz` exists, non-empty, and
  `gunzip -c ... | sqlite3 /dev/stdin 'pragma integrity_check'` (or
  `python3 -c` equivalent) prints `ok`.
- `R7 soak-sampler` — one extra crontab line, hourly, appending a timestamp,
  `free -m`, `df -h /`, `docker stats --no-stream` and
  `docker compose logs --since 1h | grep -ci error` to `~/mab-soak.log`. No
  script file; a crontab line is enough. Soak starts at the time R7 passes.

## Soak pass criteria (48h, recorded in `soak-report.md`)

- `S1 uptime` — container never restarted unexpectedly
  (`docker inspect -f '{{.RestartCount}}'` is 0) and is `healthy` at the end.
- `S2 memory` — container memory in `mab-soak.log` does not grow steadily hour
  over hour (`docs/VPS.md` §7); host never uses more than half the swap.
- `S3 source` — no Telegram source-failure or zero-result system alert; if one
  fires, record time and cause, it is a finding, not a pass.
- `S4 alerts` — at least one real listing alert received, and no item alerted
  twice (spot-check the Recent listings block against Telegram).
- `S5 backup` — the 03:00 UTC cron ran on both nights; `mab-backup.log` shows
  `backup ok` twice.
- `S6 restart` — once during the soak, `docker compose restart`; afterwards no
  replayed alerts (dedup survives restart, CLAUDE.md §7.2).

## Public interfaces

None.

## Patterns

None from CLAUDE.md §6.1 apply; no code changes.

## Test cases

No automated tests. R1–R7 and S1–S6 above are the checks; each gets a pass/fail
line in `deploy-log.md` or `soak-report.md`. `make gates` is run once on the
branch as a sanity check (nothing in `src/` changes).

## Commit sequence

```
docs(tasks): add T33 plan
docs(tasks): add T33 deploy runbook
docs(tasks): record T33 deploy steps R1-R7
docs(tasks): record T33 48h soak result
```

## Out of scope

- Any change to code, tests, `deploy/` scripts, compose, Dockerfile, docs or
  `OPERATOR.md`. Mismatches found (e.g. the `docs/VPS.md` cron log path) are
  listed in `soak-report.md` as follow-ups, not fixed here.
- Tightening the polling gap after the soak (`docs/PLAN.md` strategy); that is a
  settings change the owner makes in the UI after acceptance.
- Proxies, IP rotation, another provider, a domain, TLS, or opening port 8080.
- Off-site copies of backups.
- Marking T33 status in `docs/TASKS.md` (done by `/finish` / the human).
