from collections.abc import Sequence

from mercari_alert_bot.domain.errors import ListingSourceError
from mercari_alert_bot.domain.models.listing import ItemId, Listing


class InMemoryListingSource:
    def __init__(self) -> None:
        self.listings_by_query: dict[str, list[Listing]] = {}
        self.image_urls_by_item_id: dict[ItemId, tuple[str, ...]] = {}
        self.failing_queries: set[str] = set()
        self.fetched_queries: list[str] = []

    async def fetch_latest_listings(self, query: str) -> Sequence[Listing]:
        self.fetched_queries.append(query)
        if query in self.failing_queries:
            raise ListingSourceError(f"search failed for {query!r}")
        return list(self.listings_by_query.get(query, []))

    async def fetch_listing_image_urls(self, listing: Listing) -> tuple[str, ...]:
        return self.image_urls_by_item_id.get(listing.item_id, listing.image_urls)
