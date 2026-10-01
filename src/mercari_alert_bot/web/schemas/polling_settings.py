from typing import Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from mercari_alert_bot.domain.models.polling_settings import (
    MAX_IMAGES_PER_ALERT,
    MIN_CONSECUTIVE_FAILURE_ALERT_THRESHOLD,
    MIN_IMAGES_PER_ALERT,
    MIN_POLLING_GAP_SECONDS,
    MIN_SYSTEM_ALERT_COOLDOWN_SECONDS,
    PollingSettings,
)


class PollingSettingsSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    polling_gap_seconds: StrictInt = Field(ge=MIN_POLLING_GAP_SECONDS)
    is_item_detail_fetch_enabled: StrictBool
    max_images_per_alert: StrictInt = Field(ge=MIN_IMAGES_PER_ALERT, le=MAX_IMAGES_PER_ALERT)
    consecutive_failure_alert_threshold: StrictInt = Field(
        ge=MIN_CONSECUTIVE_FAILURE_ALERT_THRESHOLD
    )
    system_alert_cooldown_seconds: StrictInt = Field(ge=MIN_SYSTEM_ALERT_COOLDOWN_SECONDS)

    @classmethod
    def from_polling_settings(cls, polling_settings: PollingSettings) -> Self:
        return cls(
            polling_gap_seconds=polling_settings.polling_gap_seconds,
            is_item_detail_fetch_enabled=polling_settings.is_item_detail_fetch_enabled,
            max_images_per_alert=polling_settings.max_images_per_alert,
            consecutive_failure_alert_threshold=polling_settings.consecutive_failure_alert_threshold,
            system_alert_cooldown_seconds=polling_settings.system_alert_cooldown_seconds,
        )

    def to_polling_settings(self) -> PollingSettings:
        return PollingSettings(
            polling_gap_seconds=self.polling_gap_seconds,
            is_item_detail_fetch_enabled=self.is_item_detail_fetch_enabled,
            max_images_per_alert=self.max_images_per_alert,
            consecutive_failure_alert_threshold=self.consecutive_failure_alert_threshold,
            system_alert_cooldown_seconds=self.system_alert_cooldown_seconds,
        )
