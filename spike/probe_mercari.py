import argparse
import base64
import math
import time
import uuid
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from typing import Final

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import ec

SEARCH_URL: Final = "https://api.mercari.jp/v2/entities:search"
ITEM_DETAIL_URL: Final = "https://api.mercari.jp/items/get"
ITEM_PAGE_URL_PREFIX: Final = "https://jp.mercari.com/item/"
ITEM_PAGE_URL_TEMPLATE: Final = ITEM_PAGE_URL_PREFIX + "{item_id}"
SHOPS_PRODUCT_PAGE_URL_TEMPLATE: Final = "https://jp.mercari.com/shops/product/{item_id}"
SHOPS_ITEM_TYPE: Final = "ITEM_TYPE_BEYOND"
PAGE_SIZE: Final = 30
REQUEST_TIMEOUT_SECONDS: Final = 15.0
SECONDS_PER_DAY: Final = 86_400
P256_COORDINATE_BYTES: Final = 32
BROWSER_USER_AGENT: Final = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class ProbeParseError(Exception):
    pass


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


def generate_signing_key() -> ec.EllipticCurvePrivateKey:
    return ec.generate_private_key(ec.SECP256R1())


def encode_base64url(raw_bytes: bytes) -> str:
    return base64.urlsafe_b64encode(raw_bytes).rstrip(b"=").decode("ascii")


def build_public_jwk(signing_key: ec.EllipticCurvePrivateKey) -> dict[str, str]:
    public_numbers = signing_key.public_key().public_numbers()
    return {
        "crv": "P-256",
        "kty": "EC",
        "x": encode_base64url(public_numbers.x.to_bytes(P256_COORDINATE_BYTES, "big")),
        "y": encode_base64url(public_numbers.y.to_bytes(P256_COORDINATE_BYTES, "big")),
    }


def build_dpop_proof(
    signing_key: ec.EllipticCurvePrivateKey, http_method: str, target_url: str
) -> str:
    claims = {
        "iat": int(time.time()),
        "jti": str(uuid.uuid4()),
        "htu": target_url,
        "htm": http_method,
        "uuid": str(uuid.uuid4()),
    }
    headers = {"typ": "dpop+jwt", "jwk": build_public_jwk(signing_key)}
    return jwt.encode(claims, signing_key, algorithm="ES256", headers=headers)


def build_request_headers(
    signing_key: ec.EllipticCurvePrivateKey, http_method: str, target_url: str
) -> dict[str, str]:
    return {
        "DPoP": build_dpop_proof(signing_key, http_method, target_url),
        "X-Platform": "web",
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": "application/json",
    }


def build_search_body(keyword: str) -> dict[str, object]:
    return {
        "userId": "",
        "pageSize": PAGE_SIZE,
        "pageToken": "",
        "searchSessionId": uuid.uuid4().hex,
        "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
        "thumbnailTypes": [],
        "searchCondition": {
            "keyword": keyword,
            "excludeKeyword": "",
            "sort": "SORT_CREATED_TIME",
            "order": "ORDER_DESC",
            "status": ["STATUS_ON_SALE"],
        },
        "defaultDatasets": ["DATASET_TYPE_MERCARI", "DATASET_TYPE_BEYOND"],
        "serviceFrom": "suruga",
        "withItemBrand": False,
        "withItemSize": False,
        "withItemPromotions": False,
        "withItemSizes": False,
        "withShopname": False,
    }


def build_item_page_url(item_id: str, item_type: object) -> str:
    if item_type == SHOPS_ITEM_TYPE:
        return SHOPS_PRODUCT_PAGE_URL_TEMPLATE.format(item_id=item_id)
    return ITEM_PAGE_URL_TEMPLATE.format(item_id=item_id)


def parse_listing(raw_item: Mapping[str, object]) -> ProbedListing:
    try:
        item_id = str(raw_item["id"])
        thumbnails = raw_item.get("thumbnails")
        first_thumbnail = (
            str(thumbnails[0]) if isinstance(thumbnails, list) and thumbnails else None
        )
        return ProbedListing(
            item_id=item_id,
            title=str(raw_item["name"]),
            price_jpy=int(str(raw_item["price"])),
            created_at=datetime.fromtimestamp(int(str(raw_item["created"])), tz=UTC),
            url=build_item_page_url(item_id, raw_item.get("itemType")),
            thumbnail_url=first_thumbnail,
        )
    except (KeyError, ValueError, TypeError) as missing_or_malformed_field:
        raise ProbeParseError(repr(missing_or_malformed_field)) from missing_or_malformed_field


def classify_response(response: httpx.Response) -> str | None:
    if response.status_code == httpx.codes.FORBIDDEN:
        return "http_403"
    if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
        return "http_429"
    if response.status_code != httpx.codes.OK:
        return "http_other"
    if "json" not in response.headers.get("content-type", ""):
        is_html_page = response.text.lstrip().lower().startswith("<")
        return "captcha_suspected" if is_html_page else "parse_error"
    return None


def send_request(
    client: httpx.Client, request: httpx.Request
) -> tuple[RequestOutcome, httpx.Response | None]:
    started_at = time.perf_counter()
    try:
        response = client.send(request)
    except httpx.TimeoutException:
        return RequestOutcome(None, time.perf_counter() - started_at, "timeout"), None
    except httpx.TransportError:
        return RequestOutcome(None, time.perf_counter() - started_at, "transport_error"), None
    latency_seconds = time.perf_counter() - started_at
    error_kind = classify_response(response)
    outcome = RequestOutcome(response.status_code, latency_seconds, error_kind)
    return outcome, response if error_kind is None else None


def search_newest_listings(
    client: httpx.Client, signing_key: ec.EllipticCurvePrivateKey, keyword: str
) -> tuple[RequestOutcome, list[ProbedListing]]:
    request = client.build_request(
        "POST",
        SEARCH_URL,
        json=build_search_body(keyword),
        headers=build_request_headers(signing_key, "POST", SEARCH_URL),
    )
    outcome, response = send_request(client, request)
    if response is None:
        return outcome, []
    try:
        raw_items = response.json()["items"]
        return outcome, [parse_listing(raw_item) for raw_item in raw_items]
    except (ValueError, KeyError, TypeError, ProbeParseError):
        return RequestOutcome(outcome.status_code, outcome.latency_seconds, "parse_error"), []


def fetch_item_photo_urls(
    client: httpx.Client, signing_key: ec.EllipticCurvePrivateKey, item_id: str
) -> tuple[RequestOutcome, list[str]]:
    request = client.build_request(
        "GET",
        ITEM_DETAIL_URL,
        params={"id": item_id},
        headers=build_request_headers(signing_key, "GET", ITEM_DETAIL_URL),
    )
    outcome, response = send_request(client, request)
    if response is None:
        return outcome, []
    try:
        photo_urls = response.json()["data"]["photos"]
        return outcome, list(dict.fromkeys(str(photo_url) for photo_url in photo_urls))
    except (ValueError, KeyError, TypeError):
        return RequestOutcome(outcome.status_code, outcome.latency_seconds, "parse_error"), []


def is_newest_first(listings: Sequence[ProbedListing]) -> bool:
    return all(newer.created_at >= older.created_at for newer, older in pairwise(listings))


def estimate_listings_per_day(listings: Sequence[ProbedListing]) -> float | None:
    if len(listings) < 2:
        return None
    created_times = [listing.created_at for listing in listings]
    spread_seconds = (max(created_times) - min(created_times)).total_seconds()
    if spread_seconds <= 0:
        return None
    return (len(listings) - 1) * SECONDS_PER_DAY / spread_seconds


def percentile(samples: Sequence[float], fraction: float) -> float:
    ordered_samples = sorted(samples)
    nearest_rank = max(1, math.ceil(fraction * len(ordered_samples)))
    return ordered_samples[nearest_rank - 1]


def summarise_outcomes(outcomes: Sequence[RequestOutcome]) -> str:
    successful_outcomes = [outcome for outcome in outcomes if outcome.error_kind is None]
    latencies = [outcome.latency_seconds for outcome in outcomes]
    status_counts = Counter(str(outcome.status_code) for outcome in outcomes)
    error_counts = Counter(outcome.error_kind for outcome in outcomes if outcome.error_kind)
    success_rate = len(successful_outcomes) / len(outcomes) if outcomes else 0.0
    lines = [
        f"requests: {len(outcomes)}",
        f"success rate: {success_rate:.1%}",
        f"latency p50: {percentile(latencies, 0.5):.3f}s" if latencies else "latency p50: n/a",
        f"latency p95: {percentile(latencies, 0.95):.3f}s" if latencies else "latency p95: n/a",
        f"status codes: {dict(status_counts)}",
        f"errors: {dict(error_counts)}",
    ]
    return "\n".join(lines)


def print_listings(listings: Sequence[ProbedListing]) -> None:
    for listing in listings:
        print(
            f"{listing.item_id} | {listing.title} | {listing.price_jpy} JPY | "
            f"{listing.created_at.isoformat()} | {listing.url} | {listing.thumbnail_url}"
        )


def report_first_page(
    client: httpx.Client,
    signing_key: ec.EllipticCurvePrivateKey,
    listings: Sequence[ProbedListing],
) -> None:
    print_listings(listings)
    print(f"newest first by created: {is_newest_first(listings)}")
    listings_per_day = estimate_listings_per_day(listings)
    rate_text = f"{listings_per_day:.2f}" if listings_per_day is not None else "n/a"
    print(f"estimated listings per day: {rate_text}")
    detail_candidate = next(
        (listing for listing in listings if listing.url.startswith(ITEM_PAGE_URL_PREFIX)),
        None,
    )
    if detail_candidate is None:
        print("detail: no marketplace item on first page")
        return
    detail_outcome, photo_urls = fetch_item_photo_urls(
        client, signing_key, detail_candidate.item_id
    )
    print(
        f"detail {detail_candidate.item_id}: status={detail_outcome.status_code} "
        f"error={detail_outcome.error_kind} distinct photos={len(photo_urls)} "
        f"search thumbnails={int(detail_candidate.thumbnail_url is not None)}"
    )


def run_cycles(keyword: str, cycle_count: int, gap_seconds: float) -> None:
    signing_key = generate_signing_key()
    search_outcomes: list[RequestOutcome] = []
    has_reported_first_page = False
    with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        for cycle_number in range(1, cycle_count + 1):
            outcome, listings = search_newest_listings(client, signing_key, keyword)
            search_outcomes.append(outcome)
            print(
                f"cycle {cycle_number} {datetime.now(UTC).isoformat()} "
                f"status={outcome.status_code} latency={outcome.latency_seconds:.3f}s "
                f"items={len(listings)} error={outcome.error_kind} "
                f"newest={listings[0].item_id if listings else None}",
                flush=True,
            )
            if listings and not has_reported_first_page:
                report_first_page(client, signing_key, listings)
                has_reported_first_page = True
            if cycle_number < cycle_count:
                time.sleep(gap_seconds)
    print(summarise_outcomes(search_outcomes))


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe the Mercari search endpoint.")
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--gap-seconds", type=float, default=60.0)
    arguments = parser.parse_args()
    run_cycles(arguments.keyword, arguments.cycles, arguments.gap_seconds)


if __name__ == "__main__":
    main()
