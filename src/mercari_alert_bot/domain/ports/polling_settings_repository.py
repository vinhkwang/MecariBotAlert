from typing import Protocol

from mercari_alert_bot.domain.models.polling_settings import PollingSettings


class PollingSettingsRepository(Protocol):
    async def load_polling_settings(self) -> PollingSettings | None: ...

    async def save_polling_settings(self, polling_settings: PollingSettings) -> None: ...
