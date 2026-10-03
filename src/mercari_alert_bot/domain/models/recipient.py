from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType
from zoneinfo import ZoneInfo

from mercari_alert_bot.domain.errors import InvalidDomainValueError
from mercari_alert_bot.domain.models.quiet_hours import QuietHoursWindow

RecipientId = NewType("RecipientId", int)
TelegramChatId = NewType("TelegramChatId", str)


class VerificationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"


@dataclass(frozen=True, slots=True, kw_only=True)
class Recipient:
    recipient_id: RecipientId
    display_name: str
    telegram_chat_id: TelegramChatId
    verification_status: VerificationStatus
    is_enabled: bool
    timezone: ZoneInfo
    quiet_hours: QuietHoursWindow | None

    def __post_init__(self) -> None:
        if not self.display_name.strip():
            raise InvalidDomainValueError("display_name must not be blank")
        if not self.telegram_chat_id.strip():
            raise InvalidDomainValueError("telegram_chat_id must not be blank")

    @property
    def is_verified(self) -> bool:
        return self.verification_status is VerificationStatus.VERIFIED

    @property
    def can_receive_listing_alerts(self) -> bool:
        return self.is_enabled and self.is_verified

    def is_quiet_at(self, moment: datetime) -> bool:
        if moment.utcoffset() is None:
            raise InvalidDomainValueError("moment must be timezone-aware")
        if self.quiet_hours is None:
            return False
        return self.quiet_hours.contains(moment.astimezone(self.timezone).time())
