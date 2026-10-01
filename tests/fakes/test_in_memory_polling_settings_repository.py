from dataclasses import replace

from mercari_alert_bot.domain.models.polling_settings import PollingSettings
from tests.fakes.in_memory_polling_settings_repository import InMemoryPollingSettingsRepository

POLLING_SETTINGS = PollingSettings(
    polling_gap_seconds=60,
    is_item_detail_fetch_enabled=True,
    max_images_per_alert=4,
    consecutive_failure_alert_threshold=3,
    system_alert_cooldown_seconds=1800,
)


async def test_returns_none_until_saved_then_last_saved_value() -> None:
    repository = InMemoryPollingSettingsRepository()
    assert await repository.load_polling_settings() is None

    await repository.save_polling_settings(POLLING_SETTINGS)
    latest_settings = replace(POLLING_SETTINGS, polling_gap_seconds=5)
    await repository.save_polling_settings(latest_settings)

    assert await repository.load_polling_settings() == latest_settings
