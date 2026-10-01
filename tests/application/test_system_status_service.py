from datetime import UTC, datetime, timedelta

import pytest

from mercari_alert_bot.application.services.scan_cycle_service import ScanCycleReport
from mercari_alert_bot.application.services.system_status_service import SystemStatusService
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.listing_history import ListingHistoryEntry
from mercari_alert_bot.domain.models.money import JpyAmount
from tests.fakes.in_memory_listing_history_reader import InMemoryListingHistoryReader

STARTED_AT = datetime(2026, 9, 29, 4, 0, tzinfo=UTC)
FINISHED_AT = STARTED_AT + timedelta(seconds=30)


def build_report(
    *,
    scanned: tuple[str, ...] = (),
    seeded: tuple[str, ...] = (),
    failed: tuple[str, ...] = (),
) -> ScanCycleReport:
    return ScanCycleReport(
        cycle_id="cycle-1",
        started_at=STARTED_AT,
        finished_at=FINISHED_AT,
        scanned_rule_names=scanned,
        seeded_rule_names=seeded,
        failed_rule_names=failed,
        fetched_listing_count=0,
        sent_alert_count=0,
        failed_alert_count=0,
        rule_outcomes=(),
    )


def build_entry(item_id: str) -> ListingHistoryEntry:
    return ListingHistoryEntry(
        listing=Listing(
            item_id=ItemId(item_id),
            kind=ListingKind.MERCARI,
            title="OMEGA",
            price=JpyAmount(1000),
            url=f"https://jp.mercari.com/item/{item_id}",
            image_urls=(),
            created_at=STARTED_AT,
        ),
        matched_rule_names=("omega",),
        first_seen_at=STARTED_AT,
        notified_at=None,
    )


async def test_status_before_any_cycle_has_no_last_cycle() -> None:
    service = SystemStatusService(InMemoryListingHistoryReader())

    status = await service.describe_system_status()

    assert status.last_scan_cycle is None
    assert status.consecutive_failed_cycle_count == 0


async def test_status_reports_last_cycle_counts_and_times() -> None:
    service = SystemStatusService(InMemoryListingHistoryReader())

    service.record_scan_cycle(build_report(scanned=("a", "b"), seeded=("c",), failed=("d",)))
    status = await service.describe_system_status()

    assert status.last_scan_cycle is not None
    assert status.last_scan_cycle.started_at == STARTED_AT
    assert status.last_scan_cycle.finished_at == FINISHED_AT
    assert status.last_scan_cycle.succeeded_rule_count == 3
    assert status.last_scan_cycle.failed_rule_count == 1


async def test_failed_cycles_extend_streak_until_clean_cycle_resets_it() -> None:
    service = SystemStatusService(InMemoryListingHistoryReader())

    service.record_scan_cycle(build_report(failed=("a",)))
    service.record_scan_cycle(build_report(scanned=("b",), failed=("a",)))
    streak_after_failures = (await service.describe_system_status()).consecutive_failed_cycle_count
    service.record_scan_cycle(build_report(scanned=("a", "b")))
    streak_after_clean_cycle = (
        await service.describe_system_status()
    ).consecutive_failed_cycle_count

    assert streak_after_failures == 2
    assert streak_after_clean_cycle == 0


async def test_status_reads_known_count_and_last_alert_from_reader() -> None:
    notified_at = STARTED_AT + timedelta(hours=1)
    reader = InMemoryListingHistoryReader(known_listing_count=7, latest_notified_at=notified_at)
    service = SystemStatusService(reader)

    status = await service.describe_system_status()

    assert status.known_listing_count == 7
    assert status.last_alert_sent_at == notified_at


async def test_list_recent_listings_passes_limit_to_reader() -> None:
    reader = InMemoryListingHistoryReader([build_entry("m1"), build_entry("m2")])
    service = SystemStatusService(reader)

    entries = await service.list_recent_listings(1)

    assert reader.requested_limits == [1]
    assert [entry.listing.item_id for entry in entries] == ["m1"]


@pytest.mark.parametrize("limit", [0, -1])
async def test_list_recent_listings_rejects_non_positive_limit(limit: int) -> None:
    service = SystemStatusService(InMemoryListingHistoryReader())

    with pytest.raises(ValueError, match="limit"):
        await service.list_recent_listings(limit)
