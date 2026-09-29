from collections.abc import Collection, Sequence
from datetime import datetime
from typing import Protocol

from mercari_alert_bot.domain.models.keyword_rule import KeywordRuleId
from mercari_alert_bot.domain.models.listing import ItemId, Listing


class ListingRepository(Protocol):
    async def find_known_item_ids(self, item_ids: Collection[ItemId]) -> frozenset[ItemId]: ...

    async def remember_listings(
        self,
        listings: Sequence[Listing],
        rule_id: KeywordRuleId,
        seen_at: datetime,
    ) -> None: ...

    async def mark_listing_notified(self, item_id: ItemId, notified_at: datetime) -> None: ...
