# T00 — Mercari data-source spike

## Goal

Probe Mercari from a local machine and the Japanese VPS with one throwaway script, then
fill `docs/SPIKE.md` and record GO or NO-GO.

## Files

- `spike/probe_mercari.py` — create. Single throwaway script.
- `docs/SPIKE.md` — change. Filled in only after the local and VPS outputs both exist.
- `.tasks/T00/plan.md`, `.tasks/T00/state.md` — this plan and its state.

Raw run output goes to `spike/output/`, which `.gitignore` already excludes. Only the
summarised numbers reach `docs/SPIKE.md`.

Runtime: `python3.12 -m venv .venv && .venv/bin/pip install httpx "pyjwt[crypto]"`.
Both are already declared in `pyproject.toml`, so nothing new enters the project.
`pyproject.toml` is not touched: the package does not exist until T01.

## Public interfaces

None. The script is exempt from the layered architecture (see `.claude/commands/spike.md`)
and nothing imports it. Module-level functions inside it, for reviewability:

```python
SEARCH_URL: Final = "https://api.mercari.jp/v2/entities:search"
ITEM_DETAIL_URL: Final = "https://api.mercari.jp/items/get"
ITEM_PAGE_URL_TEMPLATE: Final = "https://jp.mercari.com/item/{item_id}"
PAGE_SIZE: Final = 30

@dataclass(frozen=True)
class ProbedListing:
    item_id: str
    title: str
    price_jpy: int
    created_at: datetime
    url: str
    thumbnail_url: str | None

@dataclass(frozen=True)
class RequestOutcome:
    status_code: int | None
    latency_seconds: float
    error_kind: str | None

def generate_signing_key() -> ec.EllipticCurvePrivateKey
def build_dpop_proof(signing_key: ec.EllipticCurvePrivateKey, http_method: str, target_url: str) -> str
def build_search_body(keyword: str) -> dict[str, object]
def search_newest_listings(client: httpx.Client, signing_key: ec.EllipticCurvePrivateKey, keyword: str) -> tuple[RequestOutcome, list[ProbedListing]]
def fetch_item_photo_urls(client: httpx.Client, signing_key: ec.EllipticCurvePrivateKey, item_id: str) -> tuple[RequestOutcome, list[str]]
def parse_listing(raw_item: Mapping[str, object]) -> ProbedListing
def is_newest_first(listings: Sequence[ProbedListing]) -> bool
def estimate_listings_per_day(listings: Sequence[ProbedListing]) -> float | None
def percentile(samples: Sequence[float], fraction: float) -> float
def summarise_outcomes(outcomes: Sequence[RequestOutcome]) -> str
def run_cycles(keyword: str, cycle_count: int, gap_seconds: float) -> None
def main() -> None
```

CLI: `python spike/probe_mercari.py --keyword "OMEGA 168.005" --cycles 50 --gap-seconds 60`.

Behaviour, per `.claude/commands/spike.md`:

1. DPoP proof per RFC 9449: header `typ=dpop+jwt`, `alg=ES256`, public `jwk` (P-256);
   claims `iat`, `jti` (uuid4), `htm`, `htu`, plus the `uuid` claim the Mercari web
   client sends. Fresh P-256 key per run. Headers `DPoP` and `X-Platform: web`.
2. Search body: `sort=SORT_CREATED_TIME`, `order=ORDER_DESC`, `status=[STATUS_ON_SALE]`,
   `pageSize=30`, fresh `searchSessionId`. No cookies, no login, no auth header.
3. Print `item_id | title | price | created (UTC) | url | thumbnail` per result.
4. Report `is_newest_first` over the `created` field of cycle 1.
5. Fetch detail for the first item and print how many distinct photo urls it has versus
   the thumbnails in search.
6. Print listings/day estimated from the `created` spread of the first page.
7. Loop N cycles at the gap. Record status, latency, error kind
   (`timeout`, `http_403`, `http_429`, `http_other`, `parse_error`, `transport_error`,
   `captcha_suspected` when a 200 body is HTML instead of JSON). Print success rate,
   p50, p95 and the error breakdown at the end.

No retries, no backoff: raw failures must stay visible. Strictly sequential, one request
in flight. Browser-shaped `User-Agent` only; no proxy, no fingerprint spoofing, no CAPTCHA
handling (CLAUDE.md §2, §12).

## Patterns

None of §6.1 applies. The script is a disposable probe; its purpose is to decide which
§6.1 Strategy (`ListingSource`: HTTP / browser / proxy) T14 builds. The upstream field
names it discovers become the input for `MercariSearchResponseMapper` (T11), and the
DPoP construction is re-done properly in `DpopProofFactory` (T09). No code is reused
from this script.

## Test cases

No unit tests: `tests/` and the pytest config belong to T01, and the script is
throwaway. Verification is by running it:

- `probe_local_single_cycle` — `--cycles 1` locally returns HTTP 200 and 30 parsed
  listings with id, title, price, created, url, thumbnail all present, or prints the
  exact failure kind.
- `probe_reports_ordering` — output states whether `created` is strictly descending.
- `probe_reports_detail_photos` — output shows search thumbnail count versus detail
  photo count for one item.
- `probe_reports_rate` — output shows an items/day estimate from the first page.
- `probe_local_50_cycles` — `--cycles 50 --gap-seconds 60` locally prints success rate,
  p50, p95 and an error breakdown.
- `probe_vps_50_cycles` — the human runs the identical command on the Japanese VPS and
  pastes the output back. SPIKE.md is not filled until this exists.
- `ruff check spike` and `ruff format --check spike` pass; no comments in the script.

## Commit sequence

1. `chore(spike): add mercari probe script`
2. `docs(spike): record local and vps probe results`
3. `docs(spike): record go decision` (or `record no-go decision`)

## Out of scope

- Anything under `src/`, `tests/`, `pyproject.toml`, `Makefile` (T01 onward).
- Playwright or proxy probes. Only built if the HTTP probe says NO-GO, and then as a new
  plan.
- Retries, backoff, concurrency, persistence, Telegram.
- Proxy rotation, IP cycling, fingerprint spoofing, CAPTCHA solving — never.
- Ticking GO on local results alone. The VPS column decides.
- Setting any task status in `docs/TASKS.md` other than `review` at `/finish`.
