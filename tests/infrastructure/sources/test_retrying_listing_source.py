import random
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from structlog.testing import capture_logs

from mercari_alert_bot.domain.errors import ListingSourceError
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.money import JpyAmount
from mercari_alert_bot.domain.ports.listing_source import ListingSource
from mercari_alert_bot.infrastructure.sources.retrying_listing_source import (
    RetryingListingSource,
    RetryPolicy,
)

ALWAYS_FAILING = 1_000


def build_listing(item_id: str) -> Listing:
    return Listing(
        item_id=ItemId(item_id),
        kind=ListingKind.MERCARI,
        title="OMEGA Seamaster",
        price=JpyAmount(120000),
        url=f"https://jp.mercari.com/item/{item_id}",
        image_urls=(f"https://static.mercdn.net/{item_id}.jpg",),
        created_at=datetime(2026, 9, 29, 3, 0, tzinfo=UTC),
    )


class FlakyListingSource:
    def __init__(self, failure_count: int, error: Exception | None = None) -> None:
        self.remaining_failures = failure_count
        self.error = error
        self.call_count = 0
        self.raised_errors: list[Exception] = []
        self.requested_arguments: list[str | Listing] = []
        self.listings = [build_listing("m1")]
        self.image_urls = ("https://static.mercdn.net/m1_1.jpg",)

    def _fail_if_scheduled(self, requested_argument: str | Listing) -> None:
        self.requested_arguments.append(requested_argument)
        self.call_count += 1
        if self.remaining_failures > 0:
            self.remaining_failures -= 1
            error = self.error or ListingSourceError(f"failure {self.call_count}")
            self.raised_errors.append(error)
            raise error

    async def fetch_latest_listings(self, query: str) -> Sequence[Listing]:
        self._fail_if_scheduled(query)
        return self.listings

    async def fetch_listing_image_urls(self, listing: Listing) -> tuple[str, ...]:
        self._fail_if_scheduled(listing)
        return self.image_urls


class RecordingSleep:
    def __init__(self) -> None:
        self.delays_seconds: list[float] = []

    async def __call__(self, delay_seconds: float) -> None:
        self.delays_seconds.append(delay_seconds)


def build_retrying_source(
    inner_source: FlakyListingSource,
    retry_policy: RetryPolicy,
    sleep: RecordingSleep,
) -> RetryingListingSource:
    return RetryingListingSource(inner_source, retry_policy, random.Random(7), sleep)


def exact_policy(
    max_attempts: int = 3, base_delay_seconds: float = 1.0, max_delay_seconds: float = 60.0
) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=max_attempts,
        base_delay_seconds=base_delay_seconds,
        max_delay_seconds=max_delay_seconds,
        jitter_ratio=0,
    )


async def test_success_on_first_attempt_does_not_sleep() -> None:
    inner_source = FlakyListingSource(failure_count=0)
    sleep = RecordingSleep()
    source = build_retrying_source(inner_source, exact_policy(), sleep)

    assert await source.fetch_latest_listings("OMEGA") == inner_source.listings
    assert inner_source.call_count == 1
    assert sleep.delays_seconds == []


async def test_transient_failure_is_retried_until_success() -> None:
    inner_source = FlakyListingSource(failure_count=2)
    source = build_retrying_source(inner_source, exact_policy(), RecordingSleep())

    assert await source.fetch_latest_listings("OMEGA") == inner_source.listings
    assert inner_source.requested_arguments == ["OMEGA", "OMEGA", "OMEGA"]


async def test_delays_grow_exponentially() -> None:
    inner_source = FlakyListingSource(failure_count=3)
    sleep = RecordingSleep()
    source = build_retrying_source(inner_source, exact_policy(max_attempts=4), sleep)

    await source.fetch_latest_listings("OMEGA")

    assert sleep.delays_seconds == [1, 2, 4]


async def test_delay_is_capped_at_max_delay() -> None:
    inner_source = FlakyListingSource(failure_count=3)
    sleep = RecordingSleep()
    policy = exact_policy(max_attempts=4, base_delay_seconds=10, max_delay_seconds=15)
    source = build_retrying_source(inner_source, policy, sleep)

    await source.fetch_latest_listings("OMEGA")

    assert sleep.delays_seconds == [10, 15, 15]


async def test_jitter_keeps_delay_within_ratio_band() -> None:
    inner_source = FlakyListingSource(failure_count=3)
    sleep = RecordingSleep()
    policy = RetryPolicy(max_attempts=4, base_delay_seconds=1, jitter_ratio=0.5)
    source = build_retrying_source(inner_source, policy, sleep)

    await source.fetch_latest_listings("OMEGA")

    unjittered_delays_seconds = [1, 2, 4]
    assert len(sleep.delays_seconds) == len(unjittered_delays_seconds)
    for delay_seconds, unjittered_delay_seconds in zip(
        sleep.delays_seconds, unjittered_delays_seconds, strict=True
    ):
        assert 0.5 * unjittered_delay_seconds <= delay_seconds <= 1.5 * unjittered_delay_seconds


async def test_last_error_is_reraised_after_max_attempts() -> None:
    inner_source = FlakyListingSource(failure_count=ALWAYS_FAILING)
    sleep = RecordingSleep()
    policy = exact_policy(max_attempts=3)
    source = build_retrying_source(inner_source, policy, sleep)

    with pytest.raises(ListingSourceError) as raised:
        await source.fetch_latest_listings("OMEGA")

    assert raised.value is inner_source.raised_errors[-1]
    assert inner_source.call_count == policy.max_attempts
    assert len(sleep.delays_seconds) == policy.max_attempts - 1


async def test_non_source_error_is_not_retried() -> None:
    inner_source = FlakyListingSource(failure_count=1, error=RuntimeError("bug"))
    sleep = RecordingSleep()
    source = build_retrying_source(inner_source, exact_policy(), sleep)

    with pytest.raises(RuntimeError):
        await source.fetch_latest_listings("OMEGA")

    assert inner_source.call_count == 1
    assert sleep.delays_seconds == []


async def test_image_url_fetch_is_retried() -> None:
    inner_source = FlakyListingSource(failure_count=1)
    source = build_retrying_source(inner_source, exact_policy(), RecordingSleep())

    listing = build_listing("m1")

    image_urls = await source.fetch_listing_image_urls(listing)

    assert image_urls == inner_source.image_urls
    assert inner_source.requested_arguments == [listing, listing]


async def test_single_attempt_policy_never_retries() -> None:
    inner_source = FlakyListingSource(failure_count=1)
    sleep = RecordingSleep()
    source = build_retrying_source(inner_source, exact_policy(max_attempts=1), sleep)

    with pytest.raises(ListingSourceError):
        await source.fetch_latest_listings("OMEGA")

    assert inner_source.call_count == 1
    assert sleep.delays_seconds == []


async def test_retry_is_logged_with_attempt_and_delay() -> None:
    inner_source = FlakyListingSource(failure_count=2)
    source = build_retrying_source(inner_source, exact_policy(), RecordingSleep())

    with capture_logs() as captured_events:
        await source.fetch_latest_listings("OMEGA")

    retry_events = [
        event for event in captured_events if event["event"] == "listing_source_retry_scheduled"
    ]
    assert [(event["attempt"], event["delay_seconds"]) for event in retry_events] == [
        (1, 1),
        (2, 2),
    ]
    assert all(event["log_level"] == "warning" for event in retry_events)
    assert all(event["operation"] == "fetch_latest_listings" for event in retry_events)


@pytest.mark.parametrize(
    "invalid_policy_fields",
    [
        {"max_attempts": 0},
        {"base_delay_seconds": -1},
        {"base_delay_seconds": 10, "max_delay_seconds": 5},
        {"jitter_ratio": 1.5},
    ],
)
def test_invalid_policy_is_rejected(invalid_policy_fields: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        RetryPolicy(**invalid_policy_fields)  # type: ignore[arg-type]


def test_satisfies_listing_source_port() -> None:
    source: ListingSource = build_retrying_source(
        FlakyListingSource(failure_count=0), exact_policy(), RecordingSleep()
    )

    assert isinstance(source, RetryingListingSource)
