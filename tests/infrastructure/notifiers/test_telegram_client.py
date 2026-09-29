import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import respx
import structlog
from pydantic import SecretStr

from mercari_alert_bot.domain.errors import NotificationDeliveryError
from mercari_alert_bot.infrastructure.notifiers.telegram_client import (
    TELEGRAM_API_BASE_URL,
    TelegramApiError,
    TelegramClient,
    TelegramTransportError,
)

BOT_TOKEN = "123456:secret-token-value"
CHAT_ID = "-1009876543210"
SUCCESS_BODY = {"ok": True, "result": {"message_id": 1}}


def endpoint(method_name: str) -> str:
    return f"{TELEGRAM_API_BASE_URL}/bot{BOT_TOKEN}/{method_name}"


def sent_json(route: respx.Route) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(route.calls.last.request.content)
    return body


@pytest.fixture
async def client() -> AsyncIterator[TelegramClient]:
    async with httpx.AsyncClient() as http_client:
        yield TelegramClient(http_client, SecretStr(BOT_TOKEN), SecretStr(CHAT_ID))


async def test_send_message_posts_text_to_chat(client: TelegramClient) -> None:
    with respx.mock:
        route = respx.post(endpoint("sendMessage")).respond(200, json=SUCCESS_BODY)
        await client.send_message("hello")
    assert sent_json(route) == {"chat_id": CHAT_ID, "text": "hello"}


async def test_send_photo_posts_photo_url_with_caption(client: TelegramClient) -> None:
    with respx.mock:
        route = respx.post(endpoint("sendPhoto")).respond(200, json=SUCCESS_BODY)
        await client.send_photo("https://img.example/1.jpg", "caption text")
    assert sent_json(route) == {
        "chat_id": CHAT_ID,
        "photo": "https://img.example/1.jpg",
        "caption": "caption text",
    }


async def test_send_media_group_puts_caption_on_first_photo_only(
    client: TelegramClient,
) -> None:
    photo_urls = [f"https://img.example/{index}.jpg" for index in range(3)]
    with respx.mock:
        route = respx.post(endpoint("sendMediaGroup")).respond(200, json=SUCCESS_BODY)
        await client.send_media_group(photo_urls, "caption text")
    assert sent_json(route) == {
        "chat_id": CHAT_ID,
        "media": [
            {"type": "photo", "media": photo_urls[0], "caption": "caption text"},
            {"type": "photo", "media": photo_urls[1]},
            {"type": "photo", "media": photo_urls[2]},
        ],
    }


async def test_api_error_exposes_status_and_description(client: TelegramClient) -> None:
    error_body = {
        "ok": False,
        "error_code": 400,
        "description": "Bad Request: wrong file identifier",
    }
    with respx.mock:
        respx.post(endpoint("sendPhoto")).respond(400, json=error_body)
        with pytest.raises(TelegramApiError) as raised:
            await client.send_photo("https://img.example/1.jpg", "caption")
    assert raised.value.method_name == "sendPhoto"
    assert raised.value.status_code == 400
    assert raised.value.description == "Bad Request: wrong file identifier"
    assert raised.value.retry_after_seconds is None
    assert raised.value.is_retryable is False


async def test_rate_limit_error_exposes_retry_after(client: TelegramClient) -> None:
    error_body = {
        "ok": False,
        "error_code": 429,
        "description": "Too Many Requests: retry after 17",
        "parameters": {"retry_after": 17},
    }
    with respx.mock:
        respx.post(endpoint("sendMessage")).respond(429, json=error_body)
        with pytest.raises(TelegramApiError) as raised:
            await client.send_message("hello")
    assert raised.value.retry_after_seconds == 17
    assert raised.value.is_retryable is True


async def test_server_error_is_retryable(client: TelegramClient) -> None:
    with respx.mock:
        respx.post(endpoint("sendMessage")).respond(502, content=b"<html>Bad Gateway</html>")
        with pytest.raises(TelegramApiError) as raised:
            await client.send_message("hello")
    assert raised.value.status_code == 502
    assert raised.value.description == "non-json response"
    assert raised.value.is_retryable is True


async def test_ok_false_with_http_200_is_an_error(client: TelegramClient) -> None:
    with respx.mock:
        respx.post(endpoint("sendMessage")).respond(
            200, json={"ok": False, "description": "unexpected"}
        )
        with pytest.raises(TelegramApiError) as raised:
            await client.send_message("hello")
    assert raised.value.description == "unexpected"
    assert raised.value.is_retryable is False


async def test_transport_failure_raises_transport_error_without_cause(
    client: TelegramClient,
) -> None:
    with respx.mock:
        respx.post(endpoint("sendMessage")).mock(side_effect=httpx.ConnectTimeout("timed out"))
        with pytest.raises(TelegramTransportError) as raised:
            await client.send_message("hello")
    assert raised.value.method_name == "sendMessage"
    assert raised.value.failure_kind == "ConnectTimeout"
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__ is True
    assert isinstance(raised.value, NotificationDeliveryError)


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(
            httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"}),
            id="api-error",
        ),
        pytest.param(httpx.ConnectError("refused"), id="transport-error"),
    ],
)
async def test_errors_never_contain_secrets(
    client: TelegramClient, failure: httpx.Response | Exception
) -> None:
    with respx.mock:
        route = respx.post(endpoint("sendMessage"))
        if isinstance(failure, Exception):
            route.mock(side_effect=failure)
        else:
            route.mock(return_value=failure)
        with pytest.raises(NotificationDeliveryError) as raised:
            await client.send_message("hello")
    for rendered in (str(raised.value), repr(raised.value)):
        assert BOT_TOKEN not in rendered
        assert CHAT_ID not in rendered


async def test_client_repr_never_contains_secrets(client: TelegramClient) -> None:
    for rendered in (repr(client), str(client)):
        assert BOT_TOKEN not in rendered
        assert CHAT_ID not in rendered


async def test_request_is_logged_without_secrets(client: TelegramClient) -> None:
    with respx.mock, structlog.testing.capture_logs() as captured_logs:
        respx.post(endpoint("sendMessage")).respond(200, json=SUCCESS_BODY)
        await client.send_message("private message text")
    assert len(captured_logs) == 1
    event = captured_logs[0]
    assert event["event"] == "telegram_request"
    assert event["method_name"] == "sendMessage"
    assert event["status_code"] == 200
    assert isinstance(event["duration_ms"], int)
    rendered_event = json.dumps(event, default=str)
    assert BOT_TOKEN not in rendered_event
    assert CHAT_ID not in rendered_event
    assert "private message text" not in rendered_event


async def test_every_method_is_attempted_exactly_once_on_failure(
    client: TelegramClient,
) -> None:
    with respx.mock:
        send_message_route = respx.post(endpoint("sendMessage")).respond(503)
        send_photo_route = respx.post(endpoint("sendPhoto")).respond(503)
        send_media_group_route = respx.post(endpoint("sendMediaGroup")).respond(503)
        with pytest.raises(TelegramApiError):
            await client.send_message("hello")
        with pytest.raises(TelegramApiError):
            await client.send_photo("https://img.example/1.jpg", "caption")
        with pytest.raises(TelegramApiError):
            await client.send_media_group(["https://img.example/1.jpg"], "caption")
    assert send_message_route.call_count == 1
    assert send_photo_route.call_count == 1
    assert send_media_group_route.call_count == 1
