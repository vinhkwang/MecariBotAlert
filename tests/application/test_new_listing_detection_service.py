from datetime import UTC, datetime, timedelta

from mercari_alert_bot.application.services.new_listing_detection_service import (
    NewListingDetectionService,
)
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule, KeywordRuleId
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.money import JpyAmount
from tests.fakes.in_memory_listing_repository import InMemoryListingRepository

BASELINE_AT = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
SEEN_AT = datetime(2026, 9, 30, 10, 1, tzinfo=UTC)
RULE_ID = KeywordRuleId(1)
OTHER_RULE_ID = KeywordRuleId(2)


def build_rule(baseline_established_at: datetime | None = BASELINE_AT) -> KeywordRule:
    return KeywordRule(
        rule_id=RULE_ID,
        name="omega",
        query="omega",
        is_enabled=True,
        baseline_established_at=baseline_established_at,
    )


def build_listing(item_id: str, created_at: datetime, title: str = "OMEGA") -> Listing:
    return Listing(
        item_id=ItemId(item_id),
        kind=ListingKind.MERCARI,
        title=title,
        price=JpyAmount(1000),
        url=f"https://jp.mercari.com/item/{item_id}",
        image_urls=(),
        created_at=created_at,
    )


def item_ids_of(listings: tuple[Listing, ...]) -> list[str]:
    return [listing.item_id for listing in listings]


async def test_drops_listings_already_in_dedup_table() -> None:
    repository = InMemoryListingRepository()
    known = build_listing("m1", BASELINE_AT + timedelta(minutes=5))
    unknown = build_listing("m2", BASELINE_AT + timedelta(minutes=5))
    await repository.remember_listings([known], RULE_ID, SEEN_AT)

    detected = await NewListingDetectionService(repository).detect_new_listings(
        build_rule(), [known, unknown]
    )

    assert item_ids_of(detected.fresh_listings) == ["m2"]
    assert detected.stale_listings == ()


async def test_drops_listings_known_from_another_rule() -> None:
    repository = InMemoryListingRepository()
    listing = build_listing("m1", BASELINE_AT + timedelta(minutes=5))
    await repository.remember_listings([listing], OTHER_RULE_ID, SEEN_AT)

    detected = await NewListingDetectionService(repository).detect_new_listings(
        build_rule(), [listing]
    )

    assert detected.fresh_listings == ()
    assert detected.stale_listings == ()


async def test_classifies_listing_created_after_baseline_as_fresh() -> None:
    listing = build_listing("m1", BASELINE_AT + timedelta(seconds=1))

    detected = await NewListingDetectionService(InMemoryListingRepository()).detect_new_listings(
        build_rule(), [listing]
    )

    assert item_ids_of(detected.fresh_listings) == ["m1"]
    assert detected.stale_listings == ()


async def test_classifies_listing_created_at_exact_baseline_as_fresh() -> None:
    listing = build_listing("m1", BASELINE_AT)

    detected = await NewListingDetectionService(InMemoryListingRepository()).detect_new_listings(
        build_rule(), [listing]
    )

    assert item_ids_of(detected.fresh_listings) == ["m1"]


async def test_classifies_listing_created_before_baseline_as_stale() -> None:
    listing = build_listing("m1", BASELINE_AT - timedelta(seconds=1))

    detected = await NewListingDetectionService(InMemoryListingRepository()).detect_new_listings(
        build_rule(), [listing]
    )

    assert detected.fresh_listings == ()
    assert item_ids_of(detected.stale_listings) == ["m1"]


async def test_classifies_every_unseen_listing_as_stale_when_rule_has_no_baseline() -> None:
    listings = [
        build_listing("m1", BASELINE_AT - timedelta(days=1)),
        build_listing("m2", BASELINE_AT + timedelta(days=1)),
    ]

    detected = await NewListingDetectionService(InMemoryListingRepository()).detect_new_listings(
        build_rule(baseline_established_at=None), listings
    )

    assert detected.fresh_listings == ()
    assert item_ids_of(detected.stale_listings) == ["m1", "m2"]


async def test_collapses_duplicate_item_ids_keeping_first_occurrence() -> None:
    created_at = BASELINE_AT + timedelta(minutes=1)
    first = build_listing("m1", created_at, title="first")
    second = build_listing("m1", created_at, title="second")

    detected = await NewListingDetectionService(InMemoryListingRepository()).detect_new_listings(
        build_rule(), [first, second]
    )

    assert detected.fresh_listings == (first,)


async def test_preserves_candidate_order_within_each_group() -> None:
    after = BASELINE_AT + timedelta(minutes=1)
    before = BASELINE_AT - timedelta(minutes=1)
    listings = [
        build_listing("m3", after),
        build_listing("m1", before),
        build_listing("m2", after),
        build_listing("m4", before),
    ]

    detected = await NewListingDetectionService(InMemoryListingRepository()).detect_new_listings(
        build_rule(), listings
    )

    assert item_ids_of(detected.fresh_listings) == ["m3", "m2"]
    assert item_ids_of(detected.stale_listings) == ["m1", "m4"]


async def test_returns_empty_result_for_empty_candidates() -> None:
    detected = await NewListingDetectionService(InMemoryListingRepository()).detect_new_listings(
        build_rule(), []
    )

    assert detected.fresh_listings == ()
    assert detected.stale_listings == ()


async def test_does_not_write_to_listing_repository() -> None:
    repository = InMemoryListingRepository()
    listing = build_listing("m1", BASELINE_AT + timedelta(minutes=1))

    await NewListingDetectionService(repository).detect_new_listings(build_rule(), [listing])

    assert repository.listings_by_item_id == {}
    assert repository.rule_ids_by_item_id == {}
    assert repository.first_seen_at_by_item_id == {}
    assert repository.notified_at_by_item_id == {}
