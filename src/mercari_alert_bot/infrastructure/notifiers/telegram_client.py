import time
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any, Final

import httpx
import structlog
from pydantic import SecretStr

from mercari_alert_bot.domain.errors import NotificationDeliveryError

TELEGRAM_API_BASE_URL: Final = "https://api.telegram.org"
NON_JSON_RESPONSE_DESCRIPTION: Final = "non-json response"
MILLISECONDS_PER_SECOND: Final = 1000
MAX_MEDIA_GROUP_SIZE: Final = 10

logger = structlog.get_logger()


class TelegramApiError(NotificationDeliveryError):
    def __init__(
        self,
        method_name: str,
        status_code: int,
        description: str,
        retry_after_seconds: int | None,
    ) -> None:
        super().__init__(f"telegram {method_name} failed with {status_code}: {description}")
        self.method_name = method_name
        self.status_code = status_code
        self.description = description
        self.retry_after_seconds = retry_after_seconds

    @property
    def is_retryable(self) -> bool:
        return (
            self.status_code == HTTPStatus.TOO_MANY_REQUESTS
            or self.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
        )


class TelegramTransportError(NotificationDeliveryError):
    def __init__(self, method_name: str, failure_kind: str) -> None:
        super().__init__(f"telegram {method_name} transport failure: {failure_kind}")
        self.method_name = method_name
        self.failure_kind = failure_kind


class TelegramClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        bot_token: SecretStr,
        chat_id: SecretStr,
    ) -> None:
        self._http_client = http_client
        self._bot_token = bot_token
        self._chat_id = chat_id

    async def send_message(self, text: str) -> None:
        await self._call("sendMessage", {"text": text})

    async def send_photo(self, photo_url: str, caption: str) -> None:
        await self._call("sendPhoto", {"photo": photo_url, "caption": caption})

    async def send_media_group(self, photo_urls: Sequence[str], caption: str) -> None:
        media = [
            {"type": "photo", "media": photo_url} for photo_url in photo_urls[:MAX_MEDIA_GROUP_SIZE]
        ]
        if media:
            media[0]["caption"] = caption
        await self._call("sendMediaGroup", {"media": media})

    async def _call(self, method_name: str, payload: Mapping[str, Any]) -> None:
        url = f"{TELEGRAM_API_BASE_URL}/bot{self._bot_token.get_secret_value()}/{method_name}"
        body = {"chat_id": self._chat_id.get_secret_value(), **payload}
        started_at = time.perf_counter()
        try:
            response = await self._http_client.post(url, json=body)
        except httpx.TransportError as error:
            failure_kind = type(error).__name__
            self._log_request(method_name, started_at, failure_kind=failure_kind)
            raise TelegramTransportError(method_name, failure_kind) from None
        self._log_request(method_name, started_at, status_code=response.status_code)
        raise_for_failed_response(method_name, response)

    def _log_request(
        self,
        method_name: str,
        started_at: float,
        status_code: int | None = None,
        failure_kind: str | None = None,
    ) -> None:
        logger.bind(method_name=method_name).info(
            "telegram_request",
            status_code=status_code,
            failure_kind=failure_kind,
            duration_ms=round((time.perf_counter() - started_at) * MILLISECONDS_PER_SECOND),
        )


def raise_for_failed_response(method_name: str, response: httpx.Response) -> None:
    parsed_body = parse_json_object(response)
    if response.status_code == HTTPStatus.OK and parsed_body.get("ok") is True:
        return
    description = parsed_body.get("description")
    raise TelegramApiError(
        method_name=method_name,
        status_code=response.status_code,
        description=description
        if isinstance(description, str)
        else describe_missing_body(parsed_body),
        retry_after_seconds=read_retry_after_seconds(parsed_body),
    )


def parse_json_object(response: httpx.Response) -> Mapping[str, Any]:
    try:
        parsed = response.json()
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def describe_missing_body(parsed_body: Mapping[str, Any]) -> str:
    return "no description" if parsed_body else NON_JSON_RESPONSE_DESCRIPTION


def read_retry_after_seconds(parsed_body: Mapping[str, Any]) -> int | None:
    parameters = parsed_body.get("parameters")
    if not isinstance(parameters, dict):
        return None
    retry_after = parameters.get("retry_after")
    return retry_after if isinstance(retry_after, int) else None
