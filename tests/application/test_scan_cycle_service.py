import json
import logging
from collections.abc import Awaitable, Callable, Collection, Iterator, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from io import StringIO

import pytest
import structlog

from mercari_alert_bot.application.services.baseline_seeding_service import (
    BaselineSeedingService,
)
from mercari_alert_bot.application.services.health_monitor_service import RuleScanOutcome
from mercari_alert_bot.application.services.new_listing_detection_service import (
    NewListingDetectionService,
)
from mercari_alert_bot.application.services.scan_cycle_service import (
    ScanCycleOptions,
    ScanCycleReport,
    ScanCycleService,
)
from mercari_alert_bot.domain.errors import ListingSourceError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.money import JpyAmount
from mercari_alert_bot.shared.logging import configure_logging
from tests.fakes.in_memory_keyword_rule_repository import InMemoryKeywordRuleRepository
from tests.fakes.in_memory_listing_repository import InMemoryListingRepository
from tests.fakes.in_memory_listing_source import InMemoryListingSource
from tests.fakes.recording_notifier import RecordingNotifier
from tests.shared.fakes import FrozenClock

BASELINE_AT = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
FRESH_AT = BASELINE_AT + timedelta(minutes=5)
STALE_AT = BASELINE_AT - timedelta(hours=1)
NOW = BASELINE_AT + timedelta(hours=1)
RULE_GAP_SECONDS = 12.0
OPTIONS = ScanCycleOptions(
    rule_gap_seconds=RULE_GAP_SECONDS,
    is_item_detail_fetch_enabled=False,
    max_images_per_alert=4,
)


def build_listing(item_id: str, created_at: datetime = FRESH_AT) -> Listing:
    return Listing(
        item_id=ItemId(item_id),
        kind=ListingKind.MERCARI,
        title=f"title {item_id}",
        price=JpyAmount(1000),
        url=f"https://jp.mercari.com/item/{item_id}",
        image_urls=(),
        created_at=created_at,
    )


class MutatingListingSource(InMemoryListingSource):
    def __init__(self, before_return: Callable[[], Awaitable[None]]) -> None:
        super().__init__()
        self._before_return = before_return

    async def fetch_latest_listings(self, query: str) -> Sequence[Listing]:
        listings = await super().fetch_latest_listings(query)
        await self._before_return()
        return listings


class DetailFetchingListingSource(InMemoryListingSource):
    def __init__(self) -> None:
        super().__init__()
        self.is_detail_failing = False
        self.detail_fetch_count = 0

    async def fetch_listing_image_urls(self, listing: Listing) -> tuple[str, ...]:
        self.detail_fetch_count += 1
        if self.is_detail_failing:
            raise ListingSourceError("detail failed")
        return await super().fetch_listing_image_urls(listing)


class KnownAtSendNotifier(RecordingNotifier):
    def __init__(
        self, find_known_item_ids: Callable[[Collection[ItemId]], Awaitable[frozenset[ItemId]]]
    ) -> None:
        super().__init__()
        self._find_known_item_ids = find_known_item_ids
        self.known_item_ids_at_send: list[frozenset[ItemId]] = []

    async def send_listing_alert(
        self, listing: Listing, matched_rules: Sequence[KeywordRule]
    ) -> None:
        self.known_item_ids_at_send.append(await self._find_known_item_ids([listing.item_id]))
        await super().send_listing_alert(listing, matched_rules)


class Harness:
    def __init__(
        self,
        listing_source: InMemoryListingSource | None = None,
        notifier: RecordingNotifier | None = None,
    ) -> None:
        self.source = listing_source or InMemoryListingSource()
        self.listings = InMemoryListingRepository()
        self.rules = InMemoryKeywordRuleRepository()
        self.notifier = notifier or RecordingNotifier()
        self.clock = FrozenClock(NOW)
        self.sleeps: list[float] = []
        self.service = ScanCycleService(
            keyword_rule_repository=self.rules,
            listing_source=self.source,
            listing_repository=self.listings,
            notifier=self.notifier,
            baseline_seeding_service=BaselineSeedingService(
                self.source, self.listings, self.rules, self.clock
            ),
            new_listing_detection_service=NewListingDetectionService(self.listings),
            clock=self.clock,
            sleep=self.record_sleep,
        )

    async def record_sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    async def add_seeded_rule(self, name: str, query: str) -> KeywordRule:
        rule = await self.rules.add_rule(name, query)
        seeded_rule = replace(rule, baseline_established_at=BASELINE_AT)
        await self.rules.save_rule(seeded_rule)
        return seeded_rule

    async def run_cycle(self, options: ScanCycleOptions = OPTIONS) -> ScanCycleReport:
        return await self.service.run_scan_cycle(options)

    def alerted_item_ids(self) -> list[ItemId]:
        return [listing.item_id for listing, _ in self.notifier.listing_alerts]


@pytest.fixture
def log_stream() -> Iterator[StringIO]:
    stream = StringIO()
    configure_logging(logging.INFO, stream)
    yield stream
    structlog.reset_defaults()


async def test_rule_without_baseline_is_seeded_and_sends_no_listing_alert() -> None:
    harness = Harness()
    rule = await harness.rules.add_rule("omega", "omega query")
    harness.source.listings_by_query["omega query"] = [build_listing("m1")]

    report = await harness.run_cycle()

    assert harness.notifier.listing_alerts == []
    assert report.seeded_rule_names == ("omega",)
    assert (await harness.rules.get_rule(rule.rule_id)).has_baseline


async def test_seeding_sends_one_initialisation_summary_naming_seeded_rules() -> None:
    harness = Harness()
    await harness.rules.add_rule("omega", "omega query")
    await harness.rules.add_rule("seiko", "seiko query")

    await harness.run_cycle()

    assert harness.notifier.system_alerts == [
        "Baseline seeded for 2 rule(s): omega, seiko. Alerts start next cycle."
    ]


async def test_cycle_without_seeding_sends_no_summary() -> None:
    harness = Harness()
    await harness.add_seeded_rule("omega", "omega query")

    await harness.run_cycle()

    assert harness.notifier.system_alerts == []


async def test_fresh_listing_is_alerted_once_and_marked_notified() -> None:
    harness = Harness()
    rule = await harness.add_seeded_rule("omega", "omega query")
    listing = build_listing("m1")
    harness.source.listings_by_query["omega query"] = [listing]

    report = await harness.run_cycle()

    assert harness.notifier.listing_alerts == [(listing, (rule,))]
    assert harness.listings.notified_at_by_item_id == {listing.item_id: NOW}
    assert report.sent_alert_count == 1


async def test_second_cycle_does_not_resend_alerted_listing() -> None:
    harness = Harness()
    await harness.add_seeded_rule("omega", "omega query")
    harness.source.listings_by_query["omega query"] = [build_listing("m1")]

    await harness.run_cycle()
    await harness.run_cycle()

    assert harness.alerted_item_ids() == [ItemId("m1")]


async def test_listing_created_before_baseline_is_remembered_but_not_alerted() -> None:
    harness = Harness()
    await harness.add_seeded_rule("omega", "omega query")
    harness.source.listings_by_query["omega query"] = [build_listing("m1", STALE_AT)]

    await harness.run_cycle()
    await harness.run_cycle()

    assert harness.notifier.listing_alerts == []
    assert ItemId("m1") in harness.listings.listings_by_item_id


async def test_item_matched_by_two_rules_produces_one_alert_listing_both_rules() -> None:
    harness = Harness()
    first_rule = await harness.add_seeded_rule("omega", "omega query")
    second_rule = await harness.add_seeded_rule("seamaster", "seamaster query")
    listing = build_listing("m1")
    harness.source.listings_by_query["omega query"] = [listing]
    harness.source.listings_by_query["seamaster query"] = [listing]

    await harness.run_cycle()

    assert harness.notifier.listing_alerts == [(listing, (first_rule, second_rule))]


async def test_item_matched_by_two_rules_is_attributed_to_both_rules() -> None:
    harness = Harness()
    first_rule = await harness.add_seeded_rule("omega", "omega query")
    second_rule = await harness.add_seeded_rule("seamaster", "seamaster query")
    listing = build_listing("m1")
    harness.source.listings_by_query["omega query"] = [listing]
    harness.source.listings_by_query["seamaster query"] = [listing]

    await harness.run_cycle()

    assert harness.listings.rule_ids_by_item_id[listing.item_id] == {
        first_rule.rule_id,
        second_rule.rule_id,
    }


async def test_rule_added_between_cycles_is_picked_up_without_restart() -> None:
    harness = Harness()
    first_report = await harness.run_cycle()
    await harness.add_seeded_rule("omega", "omega query")
    harness.source.listings_by_query["omega query"] = [build_listing("m1")]

    second_report = await harness.run_cycle()

    assert first_report.scanned_rule_names == ()
    assert second_report.scanned_rule_names == ("omega",)
    assert harness.alerted_item_ids() == [ItemId("m1")]


async def test_rule_disabled_between_cycles_is_not_scanned() -> None:
    harness = Harness()
    rule = await harness.add_seeded_rule("omega", "omega query")
    harness.source.listings_by_query["omega query"] = [build_listing("m1")]
    await harness.rules.save_rule(replace(rule, is_enabled=False))

    report = await harness.run_cycle()

    assert harness.source.fetched_queries == []
    assert report.scanned_rule_names == ()
    assert harness.notifier.listing_alerts == []


async def test_rule_query_edited_between_cycles_uses_new_query() -> None:
    harness = Harness()
    rule = await harness.add_seeded_rule("omega", "old query")
    harness.source.listings_by_query["new query"] = [build_listing("m1")]
    await harness.run_cycle()
    await harness.rules.save_rule(replace(rule, query="new query"))

    await harness.run_cycle()

    assert harness.source.fetched_queries == ["old query", "new query"]
    assert harness.alerted_item_ids() == [ItemId("m1")]


async def test_rule_added_later_is_seeded_without_alerting_existing_listings() -> None:
    harness = Harness()
    await harness.add_seeded_rule("omega", "omega query")
    harness.source.listings_by_query["omega query"] = [build_listing("m1")]
    await harness.run_cycle()
    await harness.rules.add_rule("seiko", "seiko query")
    harness.source.listings_by_query["seiko query"] = [build_listing("m1"), build_listing("m2")]

    report = await harness.run_cycle()

    assert harness.alerted_item_ids() == [ItemId("m1")]
    assert report.seeded_rule_names == ("seiko",)
    assert ItemId("m2") in harness.listings.listings_by_item_id


async def test_failing_rule_does_not_stop_other_rules() -> None:
    harness = Harness()
    await harness.add_seeded_rule("omega", "omega query")
    await harness.add_seeded_rule("seiko", "seiko query")
    harness.source.failing_queries.add("omega query")
    harness.source.listings_by_query["seiko query"] = [build_listing("m1")]

    report = await harness.run_cycle()

    assert report.failed_rule_names == ("omega",)
    assert report.scanned_rule_names == ("seiko",)
    assert harness.alerted_item_ids() == [ItemId("m1")]


async def test_rule_deleted_during_cycle_is_reported_as_failed() -> None:
    async def delete_omega_rule() -> None:
        for rule in await harness.rules.list_rules():
            if rule.name == "omega":
                await harness.rules.delete_rule(rule.rule_id)

    harness = Harness(MutatingListingSource(delete_omega_rule))
    await harness.rules.add_rule("omega", "omega query")
    await harness.add_seeded_rule("seiko", "seiko query")
    harness.source.listings_by_query["seiko query"] = [build_listing("m1")]

    report = await harness.run_cycle()

    assert report.failed_rule_names == ("omega",)
    assert report.scanned_rule_names == ("seiko",)


async def test_sleeps_rule_gap_between_rules_only() -> None:
    harness = Harness()
    for name in ("omega", "seiko", "casio"):
        await harness.add_seeded_rule(name, f"{name} query")

    await harness.run_cycle()

    assert harness.sleeps == [RULE_GAP_SECONDS, RULE_GAP_SECONDS]


async def test_single_rule_never_sleeps() -> None:
    harness = Harness()
    await harness.add_seeded_rule("omega", "omega query")

    await harness.run_cycle()

    assert harness.sleeps == []


async def test_report_counts_fetched_listings_across_scanned_rules() -> None:
    harness = Harness()
    await harness.add_seeded_rule("omega", "omega query")
    await harness.add_seeded_rule("seiko", "seiko query")
    harness.source.listings_by_query["omega query"] = [build_listing("m1"), build_listing("m2")]
    harness.source.listings_by_query["seiko query"] = [build_listing("m3")]

    report = await harness.run_cycle()

    assert report.fetched_listing_count == 3


async def test_report_counts_zero_fetched_listings_for_scanned_rule() -> None:
    harness = Harness()
    await harness.add_seeded_rule("omega", "omega query")

    report = await harness.run_cycle()

    assert report.fetched_listing_count == 0
    assert report.scanned_rule_names == ("omega",)


async def test_every_log_line_carries_cycle_id_and_rule_lines_carry_rule_name(
    log_stream: StringIO,
) -> None:
    harness = Harness()
    await harness.add_seeded_rule("omega", "omega query")
    await harness.rules.add_rule("seiko", "seiko query")
    harness.source.failing_queries.add("omega query")

    report = await harness.run_cycle()

    events = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    assert events
    assert {event["cycle_id"] for event in events} == {report.cycle_id}
    events_by_name = {event["event"]: event for event in events}
    assert events_by_name["rule_scan_failed"]["rule_name"] == "omega"
    assert events_by_name["rule_baseline_seeded"]["rule_name"] == "seiko"
    assert "scan_cycle_completed" in events_by_name


DETAIL_OPTIONS = ScanCycleOptions(
    rule_gap_seconds=RULE_GAP_SECONDS,
    is_item_detail_fetch_enabled=True,
    max_images_per_alert=2,
)


async def test_listings_are_remembered_before_alert_is_sent() -> None:
    notifier = KnownAtSendNotifier(lambda item_ids: harness.listings.find_known_item_ids(item_ids))
    harness = Harness(notifier=notifier)
    await harness.add_seeded_rule("omega", "omega query")
    harness.source.listings_by_query["omega query"] = [build_listing("m1")]

    await harness.run_cycle()

    assert notifier.known_item_ids_at_send == [frozenset({ItemId("m1")})]


async def test_alert_uses_detail_images_capped_to_max_images() -> None:
    source = DetailFetchingListingSource()
    harness = Harness(source)
    await harness.add_seeded_rule("omega", "omega query")
    listing = build_listing("m1")
    source.listings_by_query["omega query"] = [listing]
    source.image_urls_by_item_id[listing.item_id] = ("a.jpg", "b.jpg", "c.jpg")

    await harness.run_cycle(DETAIL_OPTIONS)

    assert harness.notifier.listing_alerts[0][0].image_urls == ("a.jpg", "b.jpg")


async def test_image_fetch_failure_still_sends_alert_with_search_image() -> None:
    source = DetailFetchingListingSource()
    source.is_detail_failing = True
    harness = Harness(source)
    await harness.add_seeded_rule("omega", "omega query")
    listing = replace(build_listing("m1"), image_urls=("search.jpg",))
    source.listings_by_query["omega query"] = [listing]

    report = await harness.run_cycle(DETAIL_OPTIONS)

    assert harness.notifier.listing_alerts[0][0].image_urls == ("search.jpg",)
    assert report.sent_alert_count == 1


async def test_detail_fetch_disabled_skips_image_fetch() -> None:
    source = DetailFetchingListingSource()
    harness = Harness(source)
    await harness.add_seeded_rule("omega", "omega query")
    source.listings_by_query["omega query"] = [build_listing("m1")]

    await harness.run_cycle()

    assert source.detail_fetch_count == 0
    assert harness.alerted_item_ids() == [ItemId("m1")]


async def test_notification_failure_is_counted_and_not_resent_next_cycle() -> None:
    harness = Harness()
    await harness.add_seeded_rule("omega", "omega query")
    harness.source.listings_by_query["omega query"] = [build_listing("m1")]
    harness.notifier.is_failing = True

    failed_report = await harness.run_cycle()
    harness.notifier.is_failing = False
    retry_report = await harness.run_cycle()

    assert failed_report.failed_alert_count == 1
    assert failed_report.sent_alert_count == 0
    assert harness.notifier.listing_alerts == []
    assert retry_report.sent_alert_count == 0
    assert harness.listings.notified_at_by_item_id == {}


async def test_seed_summary_failure_does_not_fail_cycle() -> None:
    harness = Harness()
    rule = await harness.rules.add_rule("omega", "omega query")
    harness.notifier.is_failing = True

    report = await harness.run_cycle()

    assert report.seeded_rule_names == ("omega",)
    assert (await harness.rules.get_rule(rule.rule_id)).has_baseline


async def test_listing_alert_log_line_carries_matched_rule_names_as_rule_name(
    log_stream: StringIO,
) -> None:
    harness = Harness()
    await harness.add_seeded_rule("omega", "omega query")
    await harness.add_seeded_rule("seamaster", "seamaster query")
    harness.source.listings_by_query["omega query"] = [build_listing("m1")]
    harness.source.listings_by_query["seamaster query"] = [build_listing("m1")]

    await harness.run_cycle()

    events = [json.loads(line) for line in log_stream.getvalue().splitlines()]
    alert_event = next(event for event in events if event["event"] == "listing_alert_sent")
    assert alert_event["rule_name"] == "omega, seamaster"


async def test_report_rule_outcomes_carry_listing_count_per_detected_rule() -> None:
    harness = Harness()
    omega = await harness.add_seeded_rule("omega", "omega query")
    seiko = await harness.add_seeded_rule("seiko", "seiko query")
    harness.source.listings_by_query["omega query"] = [build_listing("m1"), build_listing("m2")]

    report = await harness.run_cycle()

    assert report.rule_outcomes == (
        RuleScanOutcome(
            rule_id=omega.rule_id, rule_name="omega", listing_count=2, has_failed=False
        ),
        RuleScanOutcome(
            rule_id=seiko.rule_id, rule_name="seiko", listing_count=0, has_failed=False
        ),
    )


async def test_report_rule_outcomes_mark_failed_rule() -> None:
    harness = Harness()
    omega = await harness.add_seeded_rule("omega", "omega query")
    seiko = await harness.add_seeded_rule("seiko", "seiko query")
    harness.source.failing_queries.add("omega query")
    harness.source.listings_by_query["seiko query"] = [build_listing("m1")]

    report = await harness.run_cycle()

    assert report.rule_outcomes == (
        RuleScanOutcome(rule_id=omega.rule_id, rule_name="omega", listing_count=0, has_failed=True),
        RuleScanOutcome(
            rule_id=seiko.rule_id, rule_name="seiko", listing_count=1, has_failed=False
        ),
    )


async def test_report_rule_outcomes_skip_rule_seeded_this_cycle() -> None:
    harness = Harness()
    await harness.rules.add_rule("omega", "omega query")
    seiko = await harness.add_seeded_rule("seiko", "seiko query")

    report = await harness.run_cycle()

    assert report.seeded_rule_names == ("omega",)
    assert [outcome.rule_id for outcome in report.rule_outcomes] == [seiko.rule_id]
