from datetime import UTC, datetime

import pytest

from mercari_alert_bot.domain.errors import InvalidDomainValueError
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.listing_history import ListingHistoryEntry
from mercari_alert_bot.domain.models.money import JpyAmount

AWARE_MOMENT = datetime(2026, 9, 29, 4, 0, tzinfo=UTC)
NAIVE_MOMENT = datetime(2026, 9, 29, 4, 0)


def build_listing() -> Listing:
    return Listing(
        item_id=ItemId("m1"),
        kind=ListingKind.MERCARI,
        title="OMEGA",
        price=JpyAmount(1000),
        url="https://jp.mercari.com/item/m1",
        image_urls=(),
        created_at=AWARE_MOMENT,
    )


def test_entry_rejects_naive_first_seen_at() -> None:
    with pytest.raises(InvalidDomainValueError, match="first_seen_at"):
        ListingHistoryEntry(
            listing=build_listing(),
            matched_rule_names=(),
            first_seen_at=NAIVE_MOMENT,
            notified_at=None,
        )


def test_entry_rejects_naive_notified_at() -> None:
    with pytest.raises(InvalidDomainValueError, match="notified_at"):
        ListingHistoryEntry(
            listing=build_listing(),
            matched_rule_names=(),
            first_seen_at=AWARE_MOMENT,
            notified_at=NAIVE_MOMENT,
        )
