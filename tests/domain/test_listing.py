from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from mercari_alert_bot.domain.errors import InvalidDomainValueError
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.money import JpyAmount

CREATED_AT = datetime(2026, 9, 29, 3, 0, tzinfo=UTC)


def build_listing() -> Listing:
    return Listing(
        item_id=ItemId("m22267384686"),
        kind=ListingKind.MERCARI,
        title="OMEGA Constellation",
        price=JpyAmount(45000),
        url="https://jp.mercari.com/item/m22267384686",
        image_urls=("https://static.mercdn.net/item/detail/orig/photos/m22267384686_1.jpg",),
        created_at=CREATED_AT,
    )


def test_valid_listing_keeps_its_fields() -> None:
    listing = build_listing()

    assert listing.item_id == "m22267384686"
    assert listing.kind is ListingKind.MERCARI
    assert listing.title == "OMEGA Constellation"
    assert listing.price == JpyAmount(45000)
    assert listing.url == "https://jp.mercari.com/item/m22267384686"
    assert len(listing.image_urls) == 1
    assert listing.created_at == CREATED_AT


def test_blank_item_id_is_rejected() -> None:
    with pytest.raises(InvalidDomainValueError):
        replace(build_listing(), item_id=ItemId("  "))


def test_naive_created_at_is_rejected() -> None:
    with pytest.raises(InvalidDomainValueError):
        replace(build_listing(), created_at=datetime(2026, 9, 29))


def test_listing_is_immutable() -> None:
    listing = build_listing()

    with pytest.raises(FrozenInstanceError):
        listing.title = "changed"  # type: ignore[misc]


def test_listings_with_same_values_are_equal() -> None:
    assert build_listing() == build_listing()
    assert hash(build_listing()) == hash(build_listing())
