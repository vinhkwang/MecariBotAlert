from collections.abc import Sequence
from typing import Protocol

from mercari_alert_bot.domain.models.listing import Listing


class ListingSource(Protocol):
    async def fetch_latest_listings(self, query: str) -> Sequence[Listing]: ...

    async def fetch_listing_image_urls(self, listing: Listing) -> tuple[str, ...]: ...
