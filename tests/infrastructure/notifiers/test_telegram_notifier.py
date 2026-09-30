import json
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime

import httpx
import pytest
import respx
import structlog
from pydantic import SecretStr

from mercari_alert_bot.application.dto.notification_payload import build_notification_payload
from mercari_alert_bot.domain.errors import NotificationDeliveryError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule, KeywordRuleId
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.money import JpyAmount
from mercari_alert_bot.domain.ports.notifier import Notifier
from mercari_alert_bot.infrastructure.notifiers.telegram_client import (
    TELEGRAM_API_BASE_URL,
    TelegramClient,
)
from mercari_alert_bot.infrastructure.notifiers.telegram_notifier import TelegramNotifier

BOT_TOKEN = "123456:secret-token-value"
CHAT_ID = "-1009876543210"
SUCCESS_BODY = {"ok": True, "result": {"message_id": 1}}
REJECTION_BODY = {"ok": False, "description": "Bad Request: wrong file identifier"}
PHOTO_URLS = tuple(f"https://static.mercdn.net/m1-{index}.jpg" for index in range(3))

RULE = KeywordRule(
    rule_id=KeywordRuleId(1),
    name="omega",
    query="omega seamaster",
    is_enabled=True,
    baseline_established_at=None,
)

LISTING = Listing(
    item_id=ItemId("m1"),
    kind=ListingKind.MERCARI,
    title="OMEGA Seamaster",
    price=JpyAmount(12345),
    url="https://jp.mercari.com/item/m1",
    image_urls=PHOTO_URLS,
    created_at=datetime(2026, 9, 30, 10, 5, tzinfo=UTC),
)


def endpoint(method_name: str) -> str:
    return f"{TELEGRAM_API_BASE_URL}/bot{BOT_TOKEN}/{method_name}"


def listing_with_photo_count(photo_count: int) -> Listing:
    return replace(LISTING, image_urls=PHOTO_URLS[:photo_count])


@pytest.fixture
async def notifier() -> AsyncIterator[TelegramNotifier]:
    async with httpx.AsyncClient() as http_client:
        client = TelegramClient(http_client, SecretStr(BOT_TOKEN), SecretStr(CHAT_ID))
        yield TelegramNotifier(client)


async def test_listing_with_several_photos_is_sent_as_media_group(
    notifier: TelegramNotifier,
) -> None:
    with respx.mock:
        media_group_route = respx.post(endpoint("sendMediaGroup")).respond(200, json=SUCCESS_BODY)
        photo_route = respx.post(endpoint("sendPhoto")).respond(200, json=SUCCESS_BODY)
        message_route = respx.post(endpoint("sendMessage")).respond(200, json=SUCCESS_BODY)
        await notifier.send_listing_alert(listing_with_photo_count(3), [RULE])
    assert media_group_route.call_count == 1
    assert photo_route.call_count == 0
    assert message_route.call_count == 0


async def test_listing_with_one_photo_skips_media_group(notifier: TelegramNotifier) -> None:
    with respx.mock:
        media_group_route = respx.post(endpoint("sendMediaGroup")).respond(200, json=SUCCESS_BODY)
        photo_route = respx.post(endpoint("sendPhoto")).respond(200, json=SUCCESS_BODY)
        message_route = respx.post(endpoint("sendMessage")).respond(200, json=SUCCESS_BODY)
        await notifier.send_listing_alert(listing_with_photo_count(1), [RULE])
    assert media_group_route.call_count == 0
    assert photo_route.call_count == 1
    assert message_route.call_count == 0


async def test_listing_without_photos_is_sent_as_text(notifier: TelegramNotifier) -> None:
    listing = listing_with_photo_count(0)
    with respx.mock:
        message_route = respx.post(endpoint("sendMessage")).respond(200, json=SUCCESS_BODY)
        await notifier.send_listing_alert(listing, [RULE])
    sent_text = json.loads(message_route.calls.last.request.content)["text"]
    assert sent_text == build_notification_payload(listing, [RULE]).caption


async def test_media_group_rejection_falls_back_to_single_photo(
    notifier: TelegramNotifier,
) -> None:
    with respx.mock:
        respx.post(endpoint("sendMediaGroup")).respond(400, json=REJECTION_BODY)
        photo_route = respx.post(endpoint("sendPhoto")).respond(200, json=SUCCESS_BODY)
        message_route = respx.post(endpoint("sendMessage")).respond(200, json=SUCCESS_BODY)
        await notifier.send_listing_alert(listing_with_photo_count(3), [RULE])
    assert photo_route.call_count == 1
    assert message_route.call_count == 0


async def test_photo_rejection_falls_back_to_text(notifier: TelegramNotifier) -> None:
    with respx.mock:
        respx.post(endpoint("sendMediaGroup")).respond(400, json=REJECTION_BODY)
        respx.post(endpoint("sendPhoto")).respond(400, json=REJECTION_BODY)
        message_route = respx.post(endpoint("sendMessage")).respond(200, json=SUCCESS_BODY)
        await notifier.send_listing_alert(listing_with_photo_count(3), [RULE])
    assert message_route.call_count == 1


async def test_caption_too_long_falls_back_to_text(notifier: TelegramNotifier) -> None:
    caption_too_long_body = {"ok": False, "description": "Bad Request: message caption is too long"}
    with respx.mock:
        respx.post(endpoint("sendPhoto")).respond(400, json=caption_too_long_body)
        message_route = respx.post(endpoint("sendMessage")).respond(200, json=SUCCESS_BODY)
        await notifier.send_listing_alert(listing_with_photo_count(1), [RULE])
    assert message_route.call_count == 1


async def test_all_links_failing_raises_delivery_error(notifier: TelegramNotifier) -> None:
    with respx.mock:
        respx.post(endpoint("sendMediaGroup")).respond(400, json=REJECTION_BODY)
        respx.post(endpoint("sendPhoto")).respond(400, json=REJECTION_BODY)
        message_route = respx.post(endpoint("sendMessage")).respond(400, json=REJECTION_BODY)
        with pytest.raises(NotificationDeliveryError):
            await notifier.send_listing_alert(listing_with_photo_count(3), [RULE])
    assert message_route.call_count == 1


async def test_system_alert_is_sent_as_text(notifier: TelegramNotifier) -> None:
    with respx.mock:
        message_route = respx.post(endpoint("sendMessage")).respond(200, json=SUCCESS_BODY)
        await notifier.send_system_alert("scan failing")
    assert json.loads(message_route.calls.last.request.content)["text"] == "scan failing"


async def test_notifier_satisfies_notifier_port(notifier: TelegramNotifier) -> None:
    port: Notifier = notifier
    assert port is notifier


async def test_logs_never_contain_token_or_chat_id(notifier: TelegramNotifier) -> None:
    with respx.mock, structlog.testing.capture_logs() as captured_logs:
        respx.post(endpoint("sendMediaGroup")).respond(400, json=REJECTION_BODY)
        respx.post(endpoint("sendPhoto")).respond(400, json=REJECTION_BODY)
        respx.post(endpoint("sendMessage")).respond(200, json=SUCCESS_BODY)
        await notifier.send_listing_alert(listing_with_photo_count(3), [RULE])
    rendered_logs = json.dumps(captured_logs, default=str)
    assert BOT_TOKEN not in rendered_logs
    assert CHAT_ID not in rendered_logs
    assert [log["event"] for log in captured_logs if "delivery_step" in log] == [
        "telegram_delivery_step_failed",
        "telegram_delivery_step_failed",
        "listing_notification_sent",
    ]
