from dataclasses import replace

import pytest

from mercari_alert_bot.application.services.polling_settings_service import (
    PollingSettingsService,
)
from mercari_alert_bot.domain.models.polling_settings import PollingSettings
from tests.fakes.in_memory_polling_settings_repository import InMemoryPollingSettingsRepository

DEFAULT_SETTINGS = PollingSettings(
    polling_gap_seconds=60,
    is_item_detail_fetch_enabled=True,
    max_images_per_alert=4,
    consecutive_failure_alert_threshold=3,
    system_alert_cooldown_seconds=1800,
)
STORED_SETTINGS = replace(DEFAULT_SETTINGS, polling_gap_seconds=15, max_images_per_alert=2)
UPDATED_SETTINGS = replace(DEFAULT_SETTINGS, polling_gap_seconds=30)


def test_current_settings_are_defaults_before_load() -> None:
    service = PollingSettingsService(InMemoryPollingSettingsRepository(), DEFAULT_SETTINGS)

    assert service.current_polling_settings == DEFAULT_SETTINGS


async def test_load_uses_defaults_when_nothing_is_stored() -> None:
    service = PollingSettingsService(InMemoryPollingSettingsRepository(), DEFAULT_SETTINGS)

    assert await service.load_polling_settings() == DEFAULT_SETTINGS


async def test_load_prefers_stored_settings_over_defaults() -> None:
    service = PollingSettingsService(
        InMemoryPollingSettingsRepository(STORED_SETTINGS), DEFAULT_SETTINGS
    )

    assert await service.load_polling_settings() == STORED_SETTINGS
    assert service.current_polling_settings == STORED_SETTINGS


async def test_update_persists_and_becomes_current() -> None:
    repository = InMemoryPollingSettingsRepository()
    service = PollingSettingsService(repository, DEFAULT_SETTINGS)

    returned_settings = await service.update_polling_settings(UPDATED_SETTINGS)

    assert returned_settings == UPDATED_SETTINGS
    assert await repository.load_polling_settings() == UPDATED_SETTINGS
    assert service.current_polling_settings == UPDATED_SETTINGS


async def test_failed_save_keeps_current_settings() -> None:
    repository = InMemoryPollingSettingsRepository()
    repository.should_fail_on_save = True
    service = PollingSettingsService(repository, DEFAULT_SETTINGS)

    with pytest.raises(RuntimeError, match="save failed"):
        await service.update_polling_settings(UPDATED_SETTINGS)

    assert service.current_polling_settings == DEFAULT_SETTINGS
