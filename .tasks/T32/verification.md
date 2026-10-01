# T32 — Verification

Run 2026-10-01 against branch `chore/operator-guide` at 76d03a7.

| Check | Result | Evidence |
|---|---|---|
| V1 commands-exist | PASS | `deploy/backup.sh`, `.env.example`, `config/keywords.yaml`, service `alert-bot`, `RETAIN_DAYS` all present. Every UI label quoted in the guide (`Send test alert`, `Export YAML`, `Import YAML`, `Reset baseline`, `Seeds on next cycle`, the five settings labels, `Estimated p95 latency`, the six Status labels) found once in `src/mercari_alert_bot/web/static/`. System alert texts match `scan_cycle_service.py` and `health_monitor_service.py`. |
| V2 defaults-match | PASS | 60 s, detail fetch on, 4 images, threshold 3, cooldown 1800 s match `env_settings.py`. Healthcheck 120 s and 10m × 5 log cap match `Dockerfile` and `docker-compose.yml`. UI-saved settings persist via `SqlitePollingSettingsRepository`. |
| V3 api-match | PASS | Every action in the guide maps to a button in `index.html` / `app.js`. Import skips by duplicate `query`, as in `operator_action_service.py`. |
| V4 restore-dry-run | PASS | Dummy `.env`. `compose up -d --build`; added a **disabled** rule (so no Mercari request); `deploy/backup.sh` ok; deleted the rule; `compose down` + `up` showed `[]`; ran section 9 commands verbatim; `/api/keywords` returned the rule again. Teardown: `compose down`, removed `.env` and `backups/`. Volume `mab-t32_listings-data` left in place (`down -v` is denied). |
| V5 no-secrets | PASS | Only `127.0.0.1` and `<vps-ip>` placeholders; no token or chat id. Container logs contained no `token` string. |
| V6 gates | PASS | ruff check, ruff format --check, mypy src (74 files), pytest 548 passed. |

## Plan amendment

Guide moved from `docs/OPERATOR.md` to root `OPERATOR.md` because `.gitignore`
ignores `docs/`. Approved by the human (option 1) before implementation.

## Notes for review

- `SEARCH_PAGE_SIZE` is not editable in the UI, so the guide's settings table
  omits it.
- The fixed `container_name: mercari-alert-bot` in `docker-compose.yml` means
  two checkouts cannot run the stack at the same time. Out of scope here.
