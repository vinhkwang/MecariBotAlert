import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import TypeVar

import structlog

from mercari_alert_bot.domain.errors import ListingSourceError
from mercari_alert_bot.domain.models.listing import Listing
from mercari_alert_bot.domain.ports.listing_source import ListingSource
from mercari_alert_bot.shared.jitter import apply_jitter

Sleep = Callable[[float], Awaitable[None]]
FetchResult = TypeVar("FetchResult")

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 2.0
    max_delay_seconds: float = 60.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError(f"max_attempts must be at least 1: {self.max_attempts}")
        if self.base_delay_seconds < 0:
            raise ValueError(f"base_delay_seconds must not be negative: {self.base_delay_seconds}")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError(
                f"max_delay_seconds must be at least base_delay_seconds: {self.max_delay_seconds}"
            )
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError(f"jitter_ratio must be within [0, 1]: {self.jitter_ratio}")

    def backoff_delay_seconds(self, retry_index: int, rng: random.Random) -> float:
        capped_delay_seconds = min(self.base_delay_seconds * 2**retry_index, self.max_delay_seconds)
        return apply_jitter(capped_delay_seconds, self.jitter_ratio, rng)


class RetryingListingSource:
    def __init__(
        self,
        inner_source: ListingSource,
        retry_policy: RetryPolicy,
        rng: random.Random,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._inner_source = inner_source
        self._retry_policy = retry_policy
        self._rng = rng
        self._sleep = sleep

    async def fetch_latest_listings(self, query: str) -> Sequence[Listing]:
        return await self._call_with_retry(
            "fetch_latest_listings",
            lambda: self._inner_source.fetch_latest_listings(query),
        )

    async def fetch_listing_image_urls(self, listing: Listing) -> tuple[str, ...]:
        return await self._call_with_retry(
            "fetch_listing_image_urls",
            lambda: self._inner_source.fetch_listing_image_urls(listing),
        )

    async def _call_with_retry(
        self,
        operation: str,
        fetch: Callable[[], Awaitable[FetchResult]],
    ) -> FetchResult:
        final_attempt = self._retry_policy.max_attempts
        for attempt in range(1, final_attempt):
            try:
                return await fetch()
            except ListingSourceError as error:
                delay_seconds = self._retry_policy.backoff_delay_seconds(attempt - 1, self._rng)
                logger.warning(
                    "listing_source_retry_scheduled",
                    operation=operation,
                    attempt=attempt,
                    delay_seconds=delay_seconds,
                    error=str(error),
                )
                await self._sleep(delay_seconds)
        return await fetch()
