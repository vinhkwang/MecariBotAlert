import structlog

from mercari_alert_bot.domain.models.polling_settings import PollingSettings
from mercari_alert_bot.domain.ports.polling_settings_repository import PollingSettingsRepository

logger = structlog.get_logger(__name__)


class PollingSettingsService:
    def __init__(
        self,
        repository: PollingSettingsRepository,
        default_polling_settings: PollingSettings,
    ) -> None:
        self._repository = repository
        self._current_polling_settings = default_polling_settings

    @property
    def current_polling_settings(self) -> PollingSettings:
        return self._current_polling_settings

    async def load_polling_settings(self) -> PollingSettings:
        stored_polling_settings = await self._repository.load_polling_settings()
        if stored_polling_settings is not None:
            self._current_polling_settings = stored_polling_settings
        return self._current_polling_settings

    async def update_polling_settings(self, polling_settings: PollingSettings) -> PollingSettings:
        await self._repository.save_polling_settings(polling_settings)
        self._current_polling_settings = polling_settings
        logger.info(
            "polling_settings_updated",
            polling_gap_seconds=polling_settings.polling_gap_seconds,
            is_item_detail_fetch_enabled=polling_settings.is_item_detail_fetch_enabled,
            max_images_per_alert=polling_settings.max_images_per_alert,
            consecutive_failure_alert_threshold=polling_settings.consecutive_failure_alert_threshold,
            system_alert_cooldown_seconds=polling_settings.system_alert_cooldown_seconds,
        )
        return polling_settings
