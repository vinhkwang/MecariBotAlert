import asyncio
import random
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Final

import structlog

from mercari_alert_bot.application.dto.notification_payload import (
    NotificationPayload,
    build_notification_payload,
)
from mercari_alert_bot.domain.errors import NotificationDeliveryError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule
from mercari_alert_bot.domain.models.listing import Listing
from mercari_alert_bot.infrastructure.notifiers.telegram_client import (
    TelegramApiError,
    TelegramClient,
    TelegramTransportError,
)
from mercari_alert_bot.infrastructure.sources.retrying_listing_source import RetryPolicy, Sleep

UNSENT_TRANSPORT_FAILURE_KINDS: Final = frozenset({"ConnectError", "ConnectTimeout", "PoolTimeout"})

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _DeliveryStep:
    name: str
    min_photo_count: int
    send: Callable[[TelegramClient, NotificationPayload], Awaitable[None]]


async def _send_media_group(client: TelegramClient, payload: NotificationPayload) -> None:
    await client.send_media_group(payload.photo_urls, payload.caption)


async def _send_single_photo(client: TelegramClient, payload: NotificationPayload) -> None:
    await client.send_photo(payload.photo_urls[0], payload.caption)


async def _send_text(client: TelegramClient, payload: NotificationPayload) -> None:
    await client.send_message(payload.caption)


_DELIVERY_CHAIN = (
    _DeliveryStep("media_group", 2, _send_media_group),
    _DeliveryStep("single_photo", 1, _send_single_photo),
    _DeliveryStep("text", 0, _send_text),
)


def _is_proven_unsent(error: NotificationDeliveryError) -> bool:
    if isinstance(error, TelegramTransportError):
        return error.failure_kind in UNSENT_TRANSPORT_FAILURE_KINDS
    return isinstance(error, TelegramApiError)


def _is_retryable(error: NotificationDeliveryError) -> bool:
    if isinstance(error, TelegramApiError):
        return error.is_retryable
    return _is_proven_unsent(error)


class TelegramNotifier:
    def __init__(
        self,
        client: TelegramClient,
        retry_policy: RetryPolicy,
        rng: random.Random,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._client = client
        self._retry_policy = retry_policy
        self._rng = rng
        self._sleep = sleep

    async def send_listing_alert(
        self,
        listing: Listing,
        matched_rules: Sequence[KeywordRule],
    ) -> None:
        payload = build_notification_payload(listing, matched_rules)
        applicable_steps = [
            step for step in _DELIVERY_CHAIN if len(payload.photo_urls) >= step.min_photo_count
        ]
        for step in applicable_steps:
            try:
                await self._send_with_retry(step.name, partial(step.send, self._client, payload))
            except NotificationDeliveryError as error:
                if step is applicable_steps[-1] or not _is_proven_unsent(error):
                    raise
                continue
            logger.info(
                "listing_notification_sent",
                item_id=listing.item_id,
                delivery_step=step.name,
            )
            return

    async def send_system_alert(self, message: str) -> None:
        await self._send_with_retry("text", partial(self._client.send_message, message))

    async def _send_with_retry(
        self,
        delivery_step: str,
        send: Callable[[], Awaitable[None]],
    ) -> None:
        final_attempt = self._retry_policy.max_attempts
        for attempt in range(1, final_attempt + 1):
            try:
                await send()
                return
            except NotificationDeliveryError as error:
                if attempt == final_attempt or not _is_retryable(error):
                    logger.warning(
                        "telegram_delivery_step_failed",
                        delivery_step=delivery_step,
                        attempt=attempt,
                        error=str(error),
                    )
                    raise
                await self._sleep(self._retry_delay_seconds(attempt, error))

    def _retry_delay_seconds(self, attempt: int, error: NotificationDeliveryError) -> float:
        backoff_delay_seconds = self._retry_policy.backoff_delay_seconds(attempt - 1, self._rng)
        retry_after_seconds = (
            error.retry_after_seconds if isinstance(error, TelegramApiError) else None
        )
        return max(backoff_delay_seconds, retry_after_seconds or 0)
