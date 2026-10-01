from collections.abc import Iterable, Sequence
from datetime import datetime

from mercari_alert_bot.domain.models.listing_history import ListingHistoryEntry


class InMemoryListingHistoryReader:
    def __init__(
        self,
        entries: Iterable[ListingHistoryEntry] = (),
        *,
        known_listing_count: int = 0,
        latest_notified_at: datetime | None = None,
    ) -> None:
        self.entries = list(entries)
        self.known_listing_count = known_listing_count
        self.latest_notified_at = latest_notified_at
        self.requested_limits: list[int] = []

    async def count_known_listings(self) -> int:
        return self.known_listing_count

    async def find_latest_notified_at(self) -> datetime | None:
        return self.latest_notified_at

    async def list_recent_listings(self, limit: int) -> Sequence[ListingHistoryEntry]:
        self.requested_limits.append(limit)
        return self.entries[:limit]
