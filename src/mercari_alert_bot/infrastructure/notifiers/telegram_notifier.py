from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

import structlog

from mercari_alert_bot.application.dto.notification_payload import (
    NotificationPayload,
    build_notification_payload,
)
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule
from mercari_alert_bot.domain.models.listing import Listing
from mercari_alert_bot.infrastructure.notifiers.telegram_client import (
    TelegramApiError,
    TelegramClient,
)

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


class TelegramNotifier:
    def __init__(self, client: TelegramClient) -> None:
        self._client = client

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
                await step.send(self._client, payload)
            except TelegramApiError as error:
                logger.warning(
                    "telegram_delivery_step_failed",
                    delivery_step=step.name,
                    error=str(error),
                )
                if step is applicable_steps[-1]:
                    raise
                continue
            logger.info(
                "listing_notification_sent",
                item_id=listing.item_id,
                delivery_step=step.name,
            )
            return

    async def send_system_alert(self, message: str) -> None:
        await self._client.send_message(message)
