from dataclasses import dataclass
from typing import Final

from mercari_alert_bot.domain.errors import InvalidDomainValueError

MIN_POLLING_GAP_SECONDS: Final = 1
MIN_IMAGES_PER_ALERT: Final = 1
MAX_IMAGES_PER_ALERT: Final = 10
MIN_CONSECUTIVE_FAILURE_ALERT_THRESHOLD: Final = 1
MIN_SYSTEM_ALERT_COOLDOWN_SECONDS: Final = 0


@dataclass(frozen=True, slots=True, kw_only=True)
class PollingSettings:
    polling_gap_seconds: int
    is_item_detail_fetch_enabled: bool
    max_images_per_alert: int
    consecutive_failure_alert_threshold: int
    system_alert_cooldown_seconds: int

    def __post_init__(self) -> None:
        if self.polling_gap_seconds < MIN_POLLING_GAP_SECONDS:
            raise InvalidDomainValueError(
                f"polling_gap_seconds must be at least {MIN_POLLING_GAP_SECONDS}"
            )
        if not MIN_IMAGES_PER_ALERT <= self.max_images_per_alert <= MAX_IMAGES_PER_ALERT:
            raise InvalidDomainValueError(
                f"max_images_per_alert must be between {MIN_IMAGES_PER_ALERT} "
                f"and {MAX_IMAGES_PER_ALERT}"
            )
        if self.consecutive_failure_alert_threshold < MIN_CONSECUTIVE_FAILURE_ALERT_THRESHOLD:
            raise InvalidDomainValueError(
                "consecutive_failure_alert_threshold must be at least "
                f"{MIN_CONSECUTIVE_FAILURE_ALERT_THRESHOLD}"
            )
        if self.system_alert_cooldown_seconds < MIN_SYSTEM_ALERT_COOLDOWN_SECONDS:
            raise InvalidDomainValueError(
                "system_alert_cooldown_seconds must be at least "
                f"{MIN_SYSTEM_ALERT_COOLDOWN_SECONDS}"
            )
