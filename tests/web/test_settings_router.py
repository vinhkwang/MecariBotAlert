from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mercari_alert_bot.application.services.polling_settings_service import (
    PollingSettingsService,
)
from mercari_alert_bot.domain.models.polling_settings import PollingSettings
from mercari_alert_bot.web.app import create_web_app
from mercari_alert_bot.web.routers.settings import get_polling_settings_service
from tests.fakes.in_memory_polling_settings_repository import InMemoryPollingSettingsRepository

DEFAULT_SETTINGS = PollingSettings(
    polling_gap_seconds=60,
    is_item_detail_fetch_enabled=True,
    max_images_per_alert=4,
    consecutive_failure_alert_threshold=3,
    system_alert_cooldown_seconds=1800,
)
UPDATED_BODY = {
    "polling_gap_seconds": 30,
    "is_item_detail_fetch_enabled": False,
    "max_images_per_alert": 2,
    "consecutive_failure_alert_threshold": 5,
    "system_alert_cooldown_seconds": 0,
}
TELEGRAM_BOT_TOKEN = "123456:secret-bot-token"
TELEGRAM_CHAT_ID = "-1009876543210"


@asynccontextmanager
async def idle_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield


@pytest.fixture
def service() -> PollingSettingsService:
    return PollingSettingsService(InMemoryPollingSettingsRepository(), DEFAULT_SETTINGS)


@pytest.fixture
def client(service: PollingSettingsService) -> Iterator[TestClient]:
    app = create_web_app(idle_lifespan)
    app.dependency_overrides[get_polling_settings_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client


def test_get_returns_current_settings(client: TestClient) -> None:
    response = client.get("/api/settings")

    assert response.status_code == 200
    assert response.json() == {
        "polling_gap_seconds": 60,
        "is_item_detail_fetch_enabled": True,
        "max_images_per_alert": 4,
        "consecutive_failure_alert_threshold": 3,
        "system_alert_cooldown_seconds": 1800,
    }


def test_put_saves_and_returns_new_settings(client: TestClient) -> None:
    put_response = client.put("/api/settings", json=UPDATED_BODY)
    get_response = client.get("/api/settings")

    assert put_response.status_code == 200
    assert put_response.json() == UPDATED_BODY
    assert get_response.json() == UPDATED_BODY


@pytest.mark.parametrize(
    "overrides",
    [
        {"polling_gap_seconds": 0},
        {"max_images_per_alert": 0},
        {"max_images_per_alert": 11},
        {"consecutive_failure_alert_threshold": 0},
        {"system_alert_cooldown_seconds": -1},
    ],
)
def test_put_rejects_out_of_range_value_with_422(
    client: TestClient, service: PollingSettingsService, overrides: dict[str, int]
) -> None:
    response = client.put("/api/settings", json={**UPDATED_BODY, **overrides})

    assert response.status_code == 422
    assert service.current_polling_settings == DEFAULT_SETTINGS


def test_put_rejects_unknown_field_with_422(
    client: TestClient, service: PollingSettingsService
) -> None:
    response = client.put("/api/settings", json={**UPDATED_BODY, "search_page_size": 30})

    assert response.status_code == 422
    assert service.current_polling_settings == DEFAULT_SETTINGS


def test_settings_responses_never_contain_telegram_secrets(client: TestClient) -> None:
    get_response = client.get("/api/settings")
    put_response = client.put("/api/settings", json=UPDATED_BODY)

    for response in (get_response, put_response):
        assert TELEGRAM_BOT_TOKEN not in response.text
        assert TELEGRAM_CHAT_ID not in response.text
        assert "telegram" not in response.text.lower()
