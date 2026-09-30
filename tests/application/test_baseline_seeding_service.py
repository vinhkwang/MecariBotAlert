from collections.abc import Awaitable, Callable, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
import structlog

from mercari_alert_bot.application.services.baseline_seeding_service import (
    BaselineSeedingService,
)
from mercari_alert_bot.domain.errors import KeywordRuleNotFoundError, ListingSourceError
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.money import JpyAmount
from tests.fakes.in_memory_keyword_rule_repository import InMemoryKeywordRuleRepository
from tests.fakes.in_memory_listing_repository import InMemoryListingRepository
from tests.fakes.in_memory_listing_source import InMemoryListingSource
from tests.shared.fakes import FrozenClock

START = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)


def build_listing(item_id: str) -> Listing:
    return Listing(
        item_id=ItemId(item_id),
        kind=ListingKind.MERCARI,
        title=f"title {item_id}",
        price=JpyAmount(1000),
        url=f"https://jp.mercari.com/item/{item_id}",
        image_urls=(),
        created_at=START,
    )


class MutatingListingSource(InMemoryListingSource):
    def __init__(self, before_return: Callable[[], Awaitable[None]]) -> None:
        super().__init__()
        self._before_return = before_return

    async def fetch_latest_listings(self, query: str) -> Sequence[Listing]:
        listings = await super().fetch_latest_listings(query)
        await self._before_return()
        return listings


class Harness:
    def __init__(
        self,
        listing_source: InMemoryListingSource | None = None,
        rules: InMemoryKeywordRuleRepository | None = None,
    ) -> None:
        self.source = listing_source or InMemoryListingSource()
        self.listings = InMemoryListingRepository()
        self.rules = rules or InMemoryKeywordRuleRepository()
        self.clock = FrozenClock(START)
        self.service = BaselineSeedingService(self.source, self.listings, self.rules, self.clock)


async def test_seeding_remembers_every_listing_under_the_rule() -> None:
    harness = Harness()
    rule = await harness.rules.add_rule("omega", "omega query")
    harness.source.listings_by_query["omega query"] = [build_listing("m1"), build_listing("m2")]

    await harness.service.seed_rule_baseline(rule)

    assert harness.listings.rule_ids_by_item_id == {
        ItemId("m1"): {rule.rule_id},
        ItemId("m2"): {rule.rule_id},
    }
    assert set(harness.listings.first_seen_at_by_item_id.values()) == {START}


async def test_seeding_sets_baseline_timestamp_on_the_rule() -> None:
    harness = Harness()
    rule = await harness.rules.add_rule("omega", "omega query")

    returned_rule = await harness.service.seed_rule_baseline(rule)

    assert returned_rule.baseline_established_at == START
    assert (await harness.rules.get_rule(rule.rule_id)).baseline_established_at == START


async def test_seeding_queries_the_source_with_the_rule_query() -> None:
    harness = Harness()
    rule = await harness.rules.add_rule("omega", "omega query")

    await harness.service.seed_rule_baseline(rule)

    assert harness.source.fetched_queries == ["omega query"]


async def test_rule_added_later_is_seeded_independently() -> None:
    harness = Harness()
    first_rule = await harness.rules.add_rule("omega", "omega query")
    await harness.service.seed_rule_baseline(first_rule)
    harness.clock.advance(timedelta(days=180))
    second_rule = await harness.rules.add_rule("seiko", "seiko query")

    await harness.service.seed_rule_baseline(second_rule)

    stored_first = await harness.rules.get_rule(first_rule.rule_id)
    stored_second = await harness.rules.get_rule(second_rule.rule_id)
    assert stored_first.baseline_established_at == START
    assert stored_second.baseline_established_at == START + timedelta(days=180)


async def test_listing_already_known_from_another_rule_is_attributed_to_the_new_rule() -> None:
    harness = Harness()
    first_rule = await harness.rules.add_rule("omega", "omega query")
    second_rule = await harness.rules.add_rule("seamaster", "seamaster query")
    shared_listing = build_listing("m1")
    harness.source.listings_by_query["omega query"] = [shared_listing]
    harness.source.listings_by_query["seamaster query"] = [shared_listing]

    await harness.service.seed_rule_baseline(first_rule)
    await harness.service.seed_rule_baseline(second_rule)

    assert harness.listings.rule_ids_by_item_id[ItemId("m1")] == {
        first_rule.rule_id,
        second_rule.rule_id,
    }


async def test_empty_result_still_establishes_baseline() -> None:
    harness = Harness()
    rule = await harness.rules.add_rule("omega", "omega query")

    returned_rule = await harness.service.seed_rule_baseline(rule)

    assert returned_rule.has_baseline
    assert harness.listings.listings_by_item_id == {}


async def test_source_failure_leaves_rule_without_baseline() -> None:
    harness = Harness()
    rule = await harness.rules.add_rule("omega", "omega query")
    harness.source.failing_queries.add("omega query")

    with pytest.raises(ListingSourceError):
        await harness.service.seed_rule_baseline(rule)

    assert harness.listings.listings_by_item_id == {}
    assert not (await harness.rules.get_rule(rule.rule_id)).has_baseline


async def test_query_edited_during_seed_does_not_set_baseline() -> None:
    rules = InMemoryKeywordRuleRepository()
    rule = await rules.add_rule("omega", "omega query")

    async def edit_query() -> None:
        await rules.save_rule(replace(rule, query="new query"))

    harness = Harness(MutatingListingSource(edit_query), rules=rules)

    returned_rule = await harness.service.seed_rule_baseline(rule)

    assert not returned_rule.has_baseline
    stored_rule = await rules.get_rule(rule.rule_id)
    assert stored_rule.query == "new query"
    assert not stored_rule.has_baseline


async def test_name_edited_during_seed_is_preserved() -> None:
    rules = InMemoryKeywordRuleRepository()
    rule = await rules.add_rule("omega", "omega query")

    async def edit_name() -> None:
        await rules.save_rule(replace(rule, name="renamed"))

    harness = Harness(MutatingListingSource(edit_name), rules=rules)

    await harness.service.seed_rule_baseline(rule)

    stored_rule = await rules.get_rule(rule.rule_id)
    assert stored_rule.name == "renamed"
    assert stored_rule.baseline_established_at == START


async def test_rule_deleted_during_seed_raises_not_found() -> None:
    rules = InMemoryKeywordRuleRepository()
    rule = await rules.add_rule("omega", "omega query")

    async def delete_rule() -> None:
        await rules.delete_rule(rule.rule_id)

    source = MutatingListingSource(delete_rule)
    source.listings_by_query["omega query"] = [build_listing("m1")]
    harness = Harness(source, rules=rules)

    with pytest.raises(KeywordRuleNotFoundError):
        await harness.service.seed_rule_baseline(rule)

    assert ItemId("m1") in harness.listings.listings_by_item_id


async def test_reseeding_overwrites_previous_baseline() -> None:
    harness = Harness()
    rule = await harness.rules.add_rule("omega", "omega query")
    seeded_rule = await harness.service.seed_rule_baseline(rule)
    harness.clock.advance(timedelta(hours=1))

    reseeded_rule = await harness.service.seed_rule_baseline(seeded_rule)

    assert reseeded_rule.baseline_established_at == START + timedelta(hours=1)


async def test_seeded_listings_are_reported_as_known() -> None:
    harness = Harness()
    rule = await harness.rules.add_rule("omega", "omega query")
    harness.source.listings_by_query["omega query"] = [build_listing("m1"), build_listing("m2")]

    await harness.service.seed_rule_baseline(rule)

    known_item_ids = await harness.listings.find_known_item_ids([ItemId("m1"), ItemId("m2")])
    assert known_item_ids == {ItemId("m1"), ItemId("m2")}


async def test_seeding_logs_rule_name_and_seeded_item_count() -> None:
    harness = Harness()
    rule = await harness.rules.add_rule("omega", "omega query")
    harness.source.listings_by_query["omega query"] = [build_listing("m1")]

    with structlog.testing.capture_logs() as captured_logs:
        await harness.service.seed_rule_baseline(rule)

    assert captured_logs == [
        {
            "event": "rule_baseline_seeded",
            "rule_name": "omega",
            "seeded_item_count": 1,
            "log_level": "info",
        }
    ]
