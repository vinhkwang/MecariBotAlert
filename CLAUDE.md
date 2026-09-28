# CLAUDE.md

Operating manual for any AI agent working in this repository. Read fully before
touching code. `docs/TASKS.md` is the board; this file is the law.

---

## 1. What this project is

A one-way alert pipeline: **new Mercari Japan listing -> Telegram push**, plus a
small local web UI for managing keywords and watching health.

**In scope:** scan keywords, detect genuinely new item IDs, enrich with images,
push a Telegram alert, never resend, and let the owner manage all of that from a
simple settings UI.

**Out of scope, permanently:** login to Mercari, account management, automated
purchase, comments, seller contact, price filtering, AI scoring, translation,
market valuation, mobile app, other marketplaces.

---

## 2. Hard guardrails

- No Mercari login, no user cookies, no borrowed account, no session token.
- No CAPTCHA solving, no authentication bypass, no anti-bot evasion beyond a
  normal browser-shaped request.
- No automated purchase, bid, comment, favourite or message.
- Sequential or low-concurrency requests only. Exponential backoff after errors.
- A parser returning zero results across **all** keywords is a suspected system
  failure, never an empty market. It must raise an alert.
- The web UI binds to `127.0.0.1` by default and is never exposed publicly
  without authentication.

---

## 3. Working agreement

### 3.1 One task, one branch, one review

Every task in `docs/TASKS.md` gets its own branch. Never commit to `main`.

```
feature/<short-kebab-name>     new behaviour
fix/<short-kebab-name>         bug fix
chore/<short-kebab-name>       tooling, deps, packaging
test/<short-kebab-name>        test-only work
docs/<short-kebab-name>        documentation only
spike/<short-kebab-name>       throwaway investigation
```

Names are short and obvious: `feature/listing-repository`, not
`feature/implement-the-sqlite-listing-repository-with-dedup`.

**The agent never merges.** After pushing, it stops and reports. The human
reviews and merges. An agent that merges a branch has broken the one rule that
matters most here.

### 3.2 Plan before code

Never write or modify code before a written plan has been proposed and
approved. The plan lists:

1. Files created or changed, with full paths.
2. Public interfaces added.
3. Test cases.
4. The commit messages.

Wait for approval. Then implement exactly that and nothing more.

### 3.3 Atomic commits

Conventional Commits, imperative, scoped. Commit after each logical unit, push
frequently. Never leave more than one unit uncommitted.

```
feat(persistence): add sqlite listing repository
fix(source): keep item ids stable across relisted items
refactor(notifier): extract delivery chain from telegram client
test(detection): cover first-run baseline suppression
chore(deps): pin httpx to 0.27
docs(tasks): mark B12 merged
```

### 3.4 The task loop

Every task runs the same loop. `docs/WORKFLOW.md` has the detail.

```
/next-task <ID>   plan, branch                -> human approves the plan
/implement <ID>   code + tests + commits
/verify           quality gates
/review <ID>      findings file                -> PASS or CHANGES_REQUESTED
/fix <ID>         apply findings
/finish <ID>      push, mark review            -> human reviews and merges
```

Handoff happens through files in `.tasks/<ID>/`, never through conversation: a
later step may run in a different session with a different model that cannot see
this one. A finding a cheaper model has to guess at was written badly.

### 3.5 Definition of done

`make gates` passes, the newest review file says `PASS`, the branch is pushed,
and a handover summary is written. Nothing is merged by the agent.

---

## 4. Parallel sessions

Several sessions work this repo at once. Conflicts come from two sessions
editing the same file, so the board is arranged to prevent that.

1. **Only tasks in the same Wave of `docs/TASKS.md` may run in parallel.** Waves
   are built so that tasks inside one have non-overlapping file sets. Tasks in
   different Waves depend on each other; running them together produces
   conflicts and a rewritten review.
2. **One worktree per session.** Never two sessions in one working directory.

   ```
   git worktree add ../mab-T07 -b feature/listing-repository
   cd ../mab-T07 && claude
   ```

3. A task edits only the files its plan declares. Needing a file the plan did
   not list means the plan is wrong — stop and report rather than reaching
   across into another task's territory.
4. These files are **frozen** after T01 and may only be touched by the task that
   owns them: `pyproject.toml`, `Makefile`, `.pre-commit-config.yaml`,
   `tests/conftest.py`, `src/mercari_alert_bot/composition_root.py`,
   `src/mercari_alert_bot/__main__.py`, `Dockerfile`, `docker-compose.yml`.
   Every dependency the project will ever need is declared in T01 precisely so
   no later task has to reopen `pyproject.toml`.
5. A task depends only on the **ports** of tasks before it, never on their
   concrete classes, and is tested against the in-memory fakes. If a task cannot
   be built without another task's implementation, the abstraction is leaking —
   stop and report.
6. Always branch from an up-to-date `main`. Rebase, never merge `main` into a
   feature branch.
7. Only the human sets a task to `merged` in `docs/TASKS.md`. `/next-task`
   relies on that being true, so an agent marking its own task merged breaks
   every other session.
8. `.claude/hooks/guard-git.sh` blocks merges, force pushes and commits on
   `main` at the tool level. A blocked command is a signal that the plan took a
   wrong turn — report it, never work around it.
8. `.claude/settings.json` denies `git merge`, force push, `git reset --hard`
   and `git commit --no-verify`. Those denials exist to catch mistakes, not to
   contain a determined process — never look for another route around one.
   Hitting a denial means stop and report, every time.
9. `.tasks/<ID>/` is committed with the branch. The plan and the review
   findings are what justify the diff, so the human reads them alongside it.

---

## 5. Code style

### 5.1 No comments

Generated code contains **no comments**. None. Not headers, not section
dividers, not `# TODO`, not docstrings on private helpers.

Readability comes from names. If a line needs a comment, the line is wrong:
extract it into a well-named function, rename the variables, or introduce a
named constant.

Allowed exceptions, and only these: a module docstring on a public package
`__init__.py`; `# type: ignore[code]` with a specific error code when a
third-party stub is wrong; tooling pragmas.

Bad:

```python
def check(items, seen):
    result = []
    for i in items:
        if i.id not in seen:
            result.append(i)
    return result
```

Good:

```python
def select_unseen_listings(
    candidates: Sequence[Listing],
    known_item_ids: AbstractSet[ItemId],
) -> list[Listing]:
    return [listing for listing in candidates if listing.item_id not in known_item_ids]
```

HTML templates follow the same rule: no `<!-- -->` commentary.

### 5.2 Naming

Functions are verb phrases (`fetch_latest_listings`, `seed_baseline_state`).
Booleans read as assertions (`is_already_notified`, `has_usable_images`).
Collections are plural. No abbreviations except `id`, `url`, `jpy`, `utc`.
Domain language matches the spec: item, listing, keyword rule, baseline,
deduplication, notification, scan cycle.

### 5.3 Typing

`mypy --strict` must pass. `NewType` for identifiers
(`ItemId = NewType("ItemId", str)`), `int` for JPY never `float`, timezone-aware
`datetime` never naive.

---

## 6. Architecture

Clean Architecture, strict inward dependency. With the web UI the layering is
literally Controller -> Service -> Repository.

```
src/mercari_alert_bot/
  domain/            imports nothing but shared
    models/          entities and value objects
    ports/           Protocol interfaces only
    errors.py
  application/       imports domain only
    dto/
    services/
  infrastructure/    imports domain and application
    sources/
    persistence/
    notifiers/
    config/
    scheduling/
  web/               imports domain and application; NEVER infrastructure
    routers/         the Controller layer, JSON only
    schemas/         request and response models, separate from domain
    static/          index.html, app.js, app.css
    dependencies.py
    app.py
  shared/            leaf utilities
  composition_root.py
  __main__.py
```

`web/routers/` receives services through FastAPI dependency overrides wired in
`composition_root.py`. A router that imports a concrete repository or adapter is
a bug.

### 6.1 Required patterns

| Pattern | Where | Why |
|---|---|---|
| **Strategy** | `ListingSource` with HTTP / browser / proxy implementations | The data source is the only high risk. Swapping it costs one line in the composition root. |
| **Repository** | `ListingRepository`, `KeywordRuleRepository` | Services never see SQL. |
| **DTO** | `ListingDto`, `NotificationPayload`, `KeywordRuleDto` | Upstream JSON never reaches domain; domain objects never reach templates. |
| **Mapper** | `MercariSearchResponseMapper` | One file knows the upstream shape. When Mercari changes, one file changes. |
| **Decorator** | `RetryingListingSource` | Retry and backoff wrap the strategy without modifying it. |
| **Chain of Responsibility** | media group -> single photo -> text only | Encodes the image-failure fallback. |
| **Factory** | `ListingSourceFactory`, `DpopProofFactory` | Construction stays out of services. |
| **Dependency Injection** | constructor injection, wired only in `composition_root.py` | No globals, no singletons, no service locator. |

### 6.2 Process model

One process. `__main__.py` starts uvicorn; the FastAPI lifespan starts the
scanner as an asyncio background task and cancels it cleanly on shutdown. One
process means one SQLite writer, which is why this is not split into two
containers.

SQLite runs in WAL mode. All writes go through a single connection guarded by an
async lock inside the repository layer.

### 6.3 Keyword storage

**Keywords are runtime data, never code and never a fixed list.** They live in
SQLite so the UI can create, edit, enable, disable and delete them at any time.

`config/keywords.yaml` is a seed and export format, not the source of truth:

- It ships with `keywords: []`. The bot starts with nothing to scan and the
  owner adds rules in the UI. `config/keywords.example.yaml` exists only to
  show the shape and is never loaded.
- On first boot with an empty table, whatever is in the seed file is imported.
- From then on the UI writes to SQLite and the seed file is ignored.
- Export back to YAML is available for backup and for moving machines.

`KeywordRuleProvider` stays a port with both a YAML and a SQLite implementation,
selected by configuration.

---

## 7. Behavioural rules the code must enforce

1. Deduplication key is the Mercari item ID, nothing else.
2. Deduplication survives restart. State is written before a notification counts
   as complete.
3. First run seeds, never notifies. Then one initialisation summary is sent.
4. One item matching several rules produces exactly one alert listing all
   matched rules.
5. Image failure never suppresses the text alert.
6. A failing keyword never stops the others.
7. Repeated source failure raises a Telegram system alert after a configurable
   consecutive-failure threshold, rate limited so an outage cannot spam.
8. Zero results across all rules raises an alert.
9. Telegram send failure retries with a bounded policy and must not duplicate.
10. Times stored in UTC, displayed in ICT (`Asia/Ho_Chi_Minh`).
11. **Rules are re-read from the repository at the start of every scan cycle.**
    Never cache the rule list at startup. Adding, editing, disabling or deleting
    a rule in the UI takes effect on the next cycle, with no restart.
12. **Baseline is per rule, not per application.** A rule added six months after
    launch is seeded on its own first cycle and sends no alerts for the listings
    that already existed. Otherwise adding a keyword would fire dozens of alerts
    at once.
13. **Editing a rule's query re-seeds that rule's baseline automatically**,
    because the previous baseline describes a different search. Editing only the
    display name does not. The UI states which of the two is about to happen
    before the change is saved.
14. Deleting a rule does not delete the listing history attributed to it, and a
    deleted rule's item IDs stay in the dedup table so re-adding it later cannot
    replay old alerts.

---

## 8. Web UI

Full specification in `docs/UI.md`. The constraints that matter here:

One static page served by FastAPI, vanilla JS against a JSON API. No framework,
no build step, no npm, no CDN. Four blocks on that page: keywords, polling
settings, status, recent listings.

A controller does exactly three things: validate input, call **one** application
service, map the result to a response schema. No business logic, no SQL, no
import of `infrastructure`. Response schemas live in `web/schemas/` and are
never domain models — the API must not break every time the domain changes.

No endpoint returns `TELEGRAM_BOT_TOKEN` or `TELEGRAM_CHAT_ID`, not even
partially masked. A test asserts this.

Default bind is `127.0.0.1:8080` with no authentication, because it is never
exposed. Remote access is an SSH tunnel:

```
ssh -L 8080:127.0.0.1:8080 user@vps
```

---

## 9. Testing

Local first. Nothing is deployed until the full suite passes on a developer
machine.

| Layer | Tool | Rule |
|---|---|---|
| domain, application | pytest + in-memory fakes | no network, no filesystem |
| persistence | pytest + temp SQLite file | real file, reopened to prove durability |
| sources | respx against recorded fixtures | never hits real Mercari |
| notifiers | respx against Telegram Bot API shapes | never sends a real message |
| web | FastAPI `TestClient` | routers tested against fake services |
| e2e | fake source + fake notifier, real SQLite | full cycle, restart, dedup |

Coverage gate: 90% on `domain/` and `application/`, 75% overall, checked with
`make cov`.

Mandatory cases: baseline suppression, restart deduplication, multi-rule single
alert, image fallback chain, per-rule error isolation, zero-result alarm,
keyword edit takes effect next cycle.

No test hits the real Mercari API or sends a real Telegram message. Ever.

---

## 10. Configuration and secrets

All secrets come from environment variables via `pydantic-settings`.
`TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are never logged, never committed,
never printed in an error or a template. `.env.example` holds names only.

---

## 11. Logging

`structlog`, JSON output. One event per scan cycle, one per notification. Every
line carries `rule_name` and `cycle_id`. Log status and duration of every
upstream request. Never log secrets or full response bodies at INFO.

---

## 12. Deployment

Local until acceptance passes. The deployment target is a Japanese VPS and that
decision is settled — do not propose, script or document any other host.

Mercari performs ASN and datacenter detection, so if an IP is refused, do not
add proxy rotation, IP cycling or fingerprint spoofing to work around it. Report
it; choosing a different host is the human's decision, not a code workaround.
