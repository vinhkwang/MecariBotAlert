# T32 — Operator guide

## Goal

Write an operations README for a non-developer owner: how to start, use, watch,
back up, restore and recover the bot without reading code.

Work happens in worktree `../mab-T32` on branch `chore/operator-guide`
(created from `main` at a86b015). Documentation only; no code, no tests.

## Files

Create:

- `OPERATOR.md` (repo root) — the guide, in Vietnamese like the other docs.

Amended after approval: `.gitignore` ignores `docs/`, `CLAUDE.md`, `.claude/`
and `.tasks/`, so a guide under `docs/` cannot be committed and `docs/` does
not exist in a fresh checkout. The guide lives at the root and is
self-contained: facts it needs from `docs/UI.md` and `docs/VPS.md` are copied
into it, never linked. `.tasks/T32/` is force-added as in earlier tasks.

Change:

- `README.md`
  - Add a row `OPERATOR.md` to the "Đọc theo thứ tự" table.
  - Repair that table: the `docs/PLAN.md` row is orphaned under the
    "Keyword" section; move it back into the table.
  - Replace the body of the "Vận hành" section with a two-line pointer to
    `OPERATOR.md`. The current `tar` backup there copies the live
    SQLite file while WAL is active, which `docs/VPS.md` §6 says can produce a
    corrupt copy. The guide uses `deploy/backup.sh` instead.

Nothing else. VPS provisioning (`deploy/bootstrap.sh`) stays out of the
guide; the guide starts from a machine with Docker installed.

## Content of `OPERATOR.md`

Sections, in order. Every command is copy-pasteable; every fact below was
checked against the repo at a86b015.

1. **Bot làm gì, không làm gì** — 5 lines. New listing -> Telegram. No login,
   no purchase, no price filter (CLAUDE.md §1).
2. **Lần đầu cài** — create `.env` from `.env.example` with
   `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (how to get each: @BotFather,
   `getUpdates`); `docker compose up -d --build`; open UI. Warn: never share
   `.env`, never paste the token anywhere.
3. **Mở UI** — local `http://127.0.0.1:8080`; on VPS via
   `ssh -L 8080:127.0.0.1:8080 <user>@<vps-ip>`. Never open port 8080 publicly.
4. **Quản lý keyword** — the four UI blocks in plain words. Rule lifecycle
   table condensed from the UI spec (add = silent baseline first cycle; edit
   query = re-seed; rename = no re-seed; disable; delete keeps history; reset
   baseline). Changes apply next cycle, no restart. "Gửi alert thử" button to
   check Telegram works.
5. **Polling settings** — what each field means in one line each, defaults from
   `EnvSettings` (gap 60 s, page size 30, detail fetch on, 4 images, failure
   threshold 3, cooldown 1800 s). Latency estimate = gap × enabled rules.
6. **Đọc thông báo hệ thống** — the Telegram messages the bot itself sends and
   what to do for each: initialisation summary (normal), source failure after
   threshold, zero results across all rules (suspected breakage, not an empty
   market). Action list: check Status block, check logs, restart, then report.
7. **Kiểm tra sức khoẻ** — `docker compose ps` (healthy/unhealthy, healthcheck
   every 120 s), `docker compose logs --since 1h`, Status block fields.
8. **Sao lưu** — `deploy/backup.sh`, output `backups/listings-<UTC>.db.gz`,
   14-day retention via `RETAIN_DAYS`; daily cron line. Export
   keywords to YAML from the UI as a second, human-readable backup.
9. **Khôi phục** — stop container, decompress the chosen backup, copy it to
   `/data/listings.db` in the `listings-data` volume, remove stale
   `listings.db-wal` / `listings.db-shm`, start. Exact commands are written and
   then dry-run once locally (see Verification).
10. **Xử lý sự cố** — table: symptom -> cause -> action. Rows: no alerts at all;
    Telegram test fails; container `unhealthy`; Mercari refuses the VPS IP
    (report it, do not add proxies — CLAUDE.md §12); disk full; alerts for old
    items after adding a keyword (should not happen — report).
11. **Cập nhật phiên bản** — `git pull` then `docker compose up -d --build`;
    data volume survives; back up first.
12. **Điều không được làm** — `docker compose down -v` (deletes all history and
    dedup, bot will re-baseline), exposing port 8080, committing `.env`,
    editing `config/keywords.yaml` expecting it to change running rules (it is
    only a first-boot seed).

## Public interfaces

None.

## Patterns

None from CLAUDE.md §6.1 apply; no code changes.

## Test cases

No automated tests (docs only). Verification checklist the implementer runs
and records in `.tasks/T32/verification.md`:

- `V1 commands-exist` — every `make`, `docker compose`, script path and env var
  named in the guide exists in the repo (grep each one).
- `V2 defaults-match` — every default quoted in section 5 matches
  `src/mercari_alert_bot/infrastructure/config/env_settings.py`.
- `V3 api-match` — every UI action named matches a button or route in
  `src/mercari_alert_bot/web/static/`.
- `V4 restore-dry-run` — locally: `docker compose up -d`, add one rule, run
  `deploy/backup.sh`, `docker compose down` (no `-v`), restore per section 9,
  start, confirm the rule is still listed in the UI. Uses a throwaway `.env`
  with dummy Telegram values; no real message is sent beyond what the dummy
  token rejects.
- `V5 no-secrets` — the guide contains no token, chat id or real IP.
- `V6 gates` — `make gates` still passes (sanity; nothing in `src/` changed).

## Commit sequence

```
docs(operator): add operator guide for non-developer owner
docs(readme): link operator guide and drop unsafe tar backup
docs(tasks): add T32 plan and verification notes
```

## Out of scope

- Any change to `src/`, `tests/`, `deploy/`, `Dockerfile`,
  `docker-compose.yml`, `Makefile` — if V4 shows the restore needs a script,
  stop and report rather than writing one.
- Rewriting `docs/VPS.md` or `docs/UI.md`, or changing `.gitignore`.
- English translation.
- Actual VPS deployment and cron setup (T33).
- Marking T32 status in `docs/TASKS.md` (done by `/finish` / the human).
