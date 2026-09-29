from collections.abc import Collection, Sequence
from datetime import datetime

from mercari_alert_bot.domain.models.keyword_rule import KeywordRuleId
from mercari_alert_bot.domain.models.listing import ItemId, Listing


class InMemoryListingRepository:
    def __init__(self) -> None:
        self.listings_by_item_id: dict[ItemId, Listing] = {}
        self.rule_ids_by_item_id: dict[ItemId, set[KeywordRuleId]] = {}
        self.notified_at_by_item_id: dict[ItemId, datetime] = {}
        self.first_seen_at_by_item_id: dict[ItemId, datetime] = {}

    async def find_known_item_ids(self, item_ids: Collection[ItemId]) -> frozenset[ItemId]:
        return frozenset(item_id for item_id in item_ids if item_id in self.listings_by_item_id)

    async def remember_listings(
        self,
        listings: Sequence[Listing],
        rule_id: KeywordRuleId,
        seen_at: datetime,
    ) -> None:
        for listing in listings:
            self.listings_by_item_id.setdefault(listing.item_id, listing)
            self.first_seen_at_by_item_id.setdefault(listing.item_id, seen_at)
            self.rule_ids_by_item_id.setdefault(listing.item_id, set()).add(rule_id)

    async def mark_listing_notified(self, item_id: ItemId, notified_at: datetime) -> None:
        self.notified_at_by_item_id[item_id] = notified_at
