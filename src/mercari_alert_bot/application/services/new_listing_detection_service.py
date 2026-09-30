from collections.abc import Sequence
from dataclasses import dataclass

from mercari_alert_bot.domain.models.keyword_rule import KeywordRule
from mercari_alert_bot.domain.models.listing import ItemId, Listing
from mercari_alert_bot.domain.ports.listing_repository import ListingRepository


@dataclass(frozen=True, slots=True, kw_only=True)
class DetectedListings:
    fresh_listings: tuple[Listing, ...]
    stale_listings: tuple[Listing, ...]


class NewListingDetectionService:
    def __init__(self, listing_repository: ListingRepository) -> None:
        self._listing_repository = listing_repository

    async def detect_new_listings(
        self,
        rule: KeywordRule,
        candidates: Sequence[Listing],
    ) -> DetectedListings:
        distinct_candidates = collapse_duplicate_item_ids(candidates)
        known_item_ids = await self._listing_repository.find_known_item_ids(
            [listing.item_id for listing in distinct_candidates]
        )
        unseen_listings = [
            listing for listing in distinct_candidates if listing.item_id not in known_item_ids
        ]
        fresh_listings = [
            listing for listing in unseen_listings if is_created_since_baseline(listing, rule)
        ]
        stale_listings = [
            listing for listing in unseen_listings if not is_created_since_baseline(listing, rule)
        ]
        return DetectedListings(
            fresh_listings=tuple(fresh_listings),
            stale_listings=tuple(stale_listings),
        )


def collapse_duplicate_item_ids(candidates: Sequence[Listing]) -> list[Listing]:
    first_listing_by_item_id: dict[ItemId, Listing] = {}
    for listing in candidates:
        first_listing_by_item_id.setdefault(listing.item_id, listing)
    return list(first_listing_by_item_id.values())


def is_created_since_baseline(listing: Listing, rule: KeywordRule) -> bool:
    if rule.baseline_established_at is None:
        return False
    return listing.created_at >= rule.baseline_established_at
