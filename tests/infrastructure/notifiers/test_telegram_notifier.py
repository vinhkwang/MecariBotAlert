import json
import random
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
from mercari_alert_bot.infrastructure.sources.retrying_listing_source import RetryPolicy

BOT_TOKEN = "123456:secret-token-value"
CHAT_ID = "-1009876543210"
SUCCESS_BODY = {"ok": True, "result": {"message_id": 1}}
REJECTION_BODY = {"ok": False, "description": "Bad Request: wrong file identifier"}
SERVER_ERROR_BODY = {"ok": False, "description": "Bad Gateway"}
MAX_ATTEMPTS = 3
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


class RecordingSleep:
    def __init__(self) -> None:
        self.delays_seconds: list[float] = []

    async def __call__(self, delay_seconds: float) -> None:
        self.delays_seconds.append(delay_seconds)


@pytest.fixture
def sleep() -> RecordingSleep:
    return RecordingSleep()


@pytest.fixture
async def notifier(sleep: RecordingSleep) -> AsyncIterator[TelegramNotifier]:
    async with httpx.AsyncClient() as http_client:
        client = TelegramClient(http_client, SecretStr(BOT_TOKEN), SecretStr(CHAT_ID))
        yield TelegramNotifier(
            client,
            RetryPolicy(max_attempts=MAX_ATTEMPTS),
            random.Random(7),
            sleep,
        )


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


async def test_rate_limit_is_retried_after_retry_after(
    notifier: TelegramNotifier,
    sleep: RecordingSleep,
) -> None:
    rate_limit_body = {
        "ok": False,
        "description": "Too Many Requests: retry after 17",
        "parameters": {"retry_after": 17},
    }
    with respx.mock:
        media_group_route = respx.post(endpoint("sendMediaGroup"))
        media_group_route.side_effect = [
            httpx.Response(429, json=rate_limit_body),
            httpx.Response(200, json=SUCCESS_BODY),
        ]
        photo_route = respx.post(endpoint("sendPhoto")).respond(200, json=SUCCESS_BODY)
        await notifier.send_listing_alert(listing_with_photo_count(3), [RULE])
    assert media_group_route.call_count == 2
    assert photo_route.call_count == 0
    assert len(sleep.delays_seconds) == 1
    assert sleep.delays_seconds[0] >= 17


async def test_server_error_is_retried_with_backoff(
    notifier: TelegramNotifier,
    sleep: RecordingSleep,
) -> None:
    with respx.mock:
        message_route = respx.post(endpoint("sendMessage"))
        message_route.side_effect = [
            httpx.Response(502, json=SERVER_ERROR_BODY),
            httpx.Response(200, json=SUCCESS_BODY),
        ]
        await notifier.send_listing_alert(listing_with_photo_count(0), [RULE])
    assert message_route.call_count == 2
    assert len(sleep.delays_seconds) == 1


@pytest.mark.parametrize(
    "unsent_failure",
    [
        httpx.ConnectError("refused"),
        httpx.ConnectTimeout("timed out"),
        httpx.PoolTimeout("pool exhausted"),
    ],
)
async def test_unsent_transport_failure_is_retried(
    notifier: TelegramNotifier,
    unsent_failure: httpx.TransportError,
) -> None:
    with respx.mock:
        message_route = respx.post(endpoint("sendMessage"))
        message_route.side_effect = [
            unsent_failure,
            httpx.Response(200, json=SUCCESS_BODY),
        ]
        await notifier.send_listing_alert(listing_with_photo_count(0), [RULE])
    assert message_route.call_count == 2


async def test_retries_are_bounded_then_fall_back(
    notifier: TelegramNotifier,
    sleep: RecordingSleep,
) -> None:
    with respx.mock:
        media_group_route = respx.post(endpoint("sendMediaGroup")).respond(
            502, json=SERVER_ERROR_BODY
        )
        photo_route = respx.post(endpoint("sendPhoto")).respond(200, json=SUCCESS_BODY)
        await notifier.send_listing_alert(listing_with_photo_count(3), [RULE])
    assert media_group_route.call_count == MAX_ATTEMPTS
    assert photo_route.call_count == 1
    assert len(sleep.delays_seconds) == MAX_ATTEMPTS - 1


@pytest.mark.parametrize(
    "ambiguous_failure",
    [
        httpx.ReadTimeout("read timed out"),
        httpx.WriteTimeout("write timed out"),
        httpx.RemoteProtocolError("peer closed"),
    ],
)
async def test_ambiguous_transport_failure_is_not_retried_nor_fallen_back(
    notifier: TelegramNotifier,
    sleep: RecordingSleep,
    ambiguous_failure: httpx.TransportError,
) -> None:
    with respx.mock:
        media_group_route = respx.post(endpoint("sendMediaGroup")).mock(
            side_effect=ambiguous_failure
        )
        photo_route = respx.post(endpoint("sendPhoto")).respond(200, json=SUCCESS_BODY)
        message_route = respx.post(endpoint("sendMessage")).respond(200, json=SUCCESS_BODY)
        with pytest.raises(NotificationDeliveryError):
            await notifier.send_listing_alert(listing_with_photo_count(3), [RULE])
    assert media_group_route.call_count == 1
    assert photo_route.call_count == 0
    assert message_route.call_count == 0
    assert sleep.delays_seconds == []


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


async def test_system_alert_retries_on_server_error(notifier: TelegramNotifier) -> None:
    with respx.mock:
        message_route = respx.post(endpoint("sendMessage"))
        message_route.side_effect = [
            httpx.Response(500, json=SERVER_ERROR_BODY),
            httpx.Response(200, json=SUCCESS_BODY),
        ]
        await notifier.send_system_alert("scan failing")
    assert message_route.call_count == 2


async def test_system_alert_failure_raises(
    notifier: TelegramNotifier,
    sleep: RecordingSleep,
) -> None:
    forbidden_body = {"ok": False, "description": "Forbidden: bot was blocked by the user"}
    with respx.mock:
        message_route = respx.post(endpoint("sendMessage")).respond(403, json=forbidden_body)
        with pytest.raises(NotificationDeliveryError):
            await notifier.send_system_alert("scan failing")
    assert message_route.call_count == 1
    assert sleep.delays_seconds == []


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
