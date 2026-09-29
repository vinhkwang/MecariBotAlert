from datetime import UTC, datetime

import pytest

from mercari_alert_bot.domain.errors import ListingSourceError
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.money import JpyAmount
from mercari_alert_bot.domain.ports.listing_source import ListingSource
from tests.fakes.in_memory_listing_source import InMemoryListingSource


def build_listing(item_id: str) -> Listing:
    return Listing(
        item_id=ItemId(item_id),
        kind=ListingKind.MERCARI,
        title="OMEGA Seamaster",
        price=JpyAmount(120000),
        url=f"https://jp.mercari.com/item/{item_id}",
        image_urls=(f"https://static.mercdn.net/{item_id}.jpg",),
        created_at=datetime(2026, 9, 29, 3, 0, tzinfo=UTC),
    )


async def test_configured_query_returns_its_listings() -> None:
    source = InMemoryListingSource()
    listing = build_listing("m1")
    source.listings_by_query["OMEGA"] = [listing]

    assert list(await source.fetch_latest_listings("OMEGA")) == [listing]


async def test_unknown_query_returns_no_listings() -> None:
    source: ListingSource = InMemoryListingSource()

    assert list(await source.fetch_latest_listings("SEIKO")) == []


async def test_failing_query_raises_listing_source_error() -> None:
    source = InMemoryListingSource()
    source.failing_queries.add("OMEGA")

    with pytest.raises(ListingSourceError):
        await source.fetch_latest_listings("OMEGA")


async def test_fetched_queries_are_recorded_in_order() -> None:
    source = InMemoryListingSource()

    await source.fetch_latest_listings("OMEGA")
    await source.fetch_latest_listings("SEIKO")

    assert source.fetched_queries == ["OMEGA", "SEIKO"]


async def test_image_urls_fall_back_to_listing_images() -> None:
    source = InMemoryListingSource()
    known_listing = build_listing("m1")
    unknown_listing = build_listing("m2")
    source.image_urls_by_item_id[known_listing.item_id] = ("a.jpg", "b.jpg")

    assert await source.fetch_listing_image_urls(known_listing) == ("a.jpg", "b.jpg")
    assert await source.fetch_listing_image_urls(unknown_listing) == unknown_listing.image_urls
