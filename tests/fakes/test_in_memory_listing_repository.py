from datetime import UTC, datetime

from mercari_alert_bot.domain.models.keyword_rule import KeywordRuleId
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.money import JpyAmount
from mercari_alert_bot.domain.ports.listing_repository import ListingRepository
from tests.fakes.in_memory_listing_repository import InMemoryListingRepository

SEEN_AT = datetime(2026, 9, 29, 4, 0, tzinfo=UTC)


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


async def test_unremembered_item_is_not_known() -> None:
    repository: ListingRepository = InMemoryListingRepository()

    assert await repository.find_known_item_ids([ItemId("m1")]) == frozenset()


async def test_remembered_item_is_known() -> None:
    repository = InMemoryListingRepository()
    await repository.remember_listings([build_listing("m1")], KeywordRuleId(1), SEEN_AT)

    known = await repository.find_known_item_ids([ItemId("m1"), ItemId("m2")])

    assert known == frozenset({ItemId("m1")})
    assert repository.first_seen_at_by_item_id == {ItemId("m1"): SEEN_AT}


async def test_remembering_twice_keeps_one_attribution() -> None:
    repository = InMemoryListingRepository()
    listing = build_listing("m1")

    await repository.remember_listings([listing], KeywordRuleId(1), SEEN_AT)
    await repository.remember_listings([listing], KeywordRuleId(1), SEEN_AT)

    assert repository.rule_ids_by_item_id[listing.item_id] == {KeywordRuleId(1)}


async def test_item_under_two_rules_keeps_both_attributions() -> None:
    repository = InMemoryListingRepository()
    listing = build_listing("m1")

    await repository.remember_listings([listing], KeywordRuleId(1), SEEN_AT)
    await repository.remember_listings([listing], KeywordRuleId(2), SEEN_AT)

    assert repository.rule_ids_by_item_id[listing.item_id] == {KeywordRuleId(1), KeywordRuleId(2)}


async def test_marking_notified_records_time() -> None:
    repository = InMemoryListingRepository()

    await repository.mark_listing_notified(ItemId("m1"), SEEN_AT)

    assert repository.notified_at_by_item_id[ItemId("m1")] == SEEN_AT
