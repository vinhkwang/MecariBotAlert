from mercari_alert_bot.domain.models.polling_settings import PollingSettings


class InMemoryPollingSettingsRepository:
    def __init__(self, stored_polling_settings: PollingSettings | None = None) -> None:
        self._stored_polling_settings = stored_polling_settings
        self.should_fail_on_save = False

    async def load_polling_settings(self) -> PollingSettings | None:
        return self._stored_polling_settings

    async def save_polling_settings(self, polling_settings: PollingSettings) -> None:
        if self.should_fail_on_save:
            raise RuntimeError("save failed")
        self._stored_polling_settings = polling_settings
