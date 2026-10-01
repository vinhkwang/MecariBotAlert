from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from mercari_alert_bot.domain.models.listing_history import ListingHistoryEntry


class ListingHistoryReader(Protocol):
    async def count_known_listings(self) -> int: ...

    async def find_latest_notified_at(self) -> datetime | None: ...

    async def list_recent_listings(self, limit: int) -> Sequence[ListingHistoryEntry]: ...
