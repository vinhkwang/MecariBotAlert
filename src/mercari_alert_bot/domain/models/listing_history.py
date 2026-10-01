from dataclasses import dataclass
from datetime import datetime

from mercari_alert_bot.domain.errors import InvalidDomainValueError
from mercari_alert_bot.domain.models.listing import Listing


@dataclass(frozen=True, slots=True, kw_only=True)
class ListingHistoryEntry:
    listing: Listing
    matched_rule_names: tuple[str, ...]
    first_seen_at: datetime
    notified_at: datetime | None

    def __post_init__(self) -> None:
        if self.first_seen_at.utcoffset() is None:
            raise InvalidDomainValueError("first_seen_at must be timezone-aware")
        if self.notified_at is not None and self.notified_at.utcoffset() is None:
            raise InvalidDomainValueError("notified_at must be timezone-aware")

    @property
    def is_notified(self) -> bool:
        return self.notified_at is not None
