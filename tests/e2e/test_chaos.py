import shutil
from datetime import timedelta
from pathlib import Path
from typing import Final

from tests.e2e.test_scan_pipeline import (
    NOW,
    ScanPipeline,
    build_listing,
    open_scan_pipeline,
)
from tests.fakes.in_memory_listing_source import InMemoryListingSource
from tests.fakes.recording_notifier import RecordingNotifier
from tests.shared.fakes import FrozenClock

OMEGA_QUERY: Final = "omega query"
FAILURE_ALERT_PREFIX: Final = "Keywords failing repeatedly:"
CYCLES_PAST_FAILURE_THRESHOLD: Final = 5


def build_source_with_existing_listing() -> InMemoryListingSource:
    source = InMemoryListingSource()
    source.listings_by_query[OMEGA_QUERY] = [build_listing("m1", NOW - timedelta(days=1))]
    return source


async def create_seeded_omega_rule(pipeline: ScanPipeline) -> None:
    await pipeline.keyword_rule_service.create_rule("omega", OMEGA_QUERY, is_enabled=True)
    await pipeline.run_scan_cycle()


def copy_database_files_while_open(database_path: Path, crash_directory: Path) -> Path:
    crash_directory.mkdir()
    for suffix in ("", "-wal"):
        source_file = database_path.with_name(database_path.name + suffix)
        if source_file.exists():
            shutil.copy(source_file, crash_directory / source_file.name)
    return crash_directory / database_path.name


def failure_system_alerts(notifier: RecordingNotifier) -> list[str]:
    return [alert for alert in notifier.system_alerts if alert.startswith(FAILURE_ALERT_PREFIX)]


async def test_source_outage_raises_one_system_alert_within_cooldown(tmp_path: Path) -> None:
    source = build_source_with_existing_listing()
    notifier = RecordingNotifier()
    async with open_scan_pipeline(
        tmp_path / "bot.sqlite3", source, notifier, FrozenClock(NOW)
    ) as pipeline:
        await create_seeded_omega_rule(pipeline)
        source.failing_queries.add(OMEGA_QUERY)

        for _ in range(CYCLES_PAST_FAILURE_THRESHOLD):
            await pipeline.run_scan_cycle()

    assert failure_system_alerts(notifier) == [
        "Keywords failing repeatedly:\n- omega: 3 scans in a row"
    ]


async def test_source_recovery_resumes_alerts_without_replay(tmp_path: Path) -> None:
    source = build_source_with_existing_listing()
    notifier = RecordingNotifier()
    async with open_scan_pipeline(
        tmp_path / "bot.sqlite3", source, notifier, FrozenClock(NOW)
    ) as pipeline:
        await create_seeded_omega_rule(pipeline)
        source.failing_queries.add(OMEGA_QUERY)
        for _ in range(CYCLES_PAST_FAILURE_THRESHOLD):
            await pipeline.run_scan_cycle()
        source.listings_by_query[OMEGA_QUERY].append(pipeline.new_listing("m2"))
        source.failing_queries.clear()

        await pipeline.run_scan_cycle()
        await pipeline.run_scan_cycle()

    assert pipeline.listing_alert_item_ids() == ["m2"]


async def test_notifier_outage_does_not_duplicate_alert_after_recovery(tmp_path: Path) -> None:
    source = build_source_with_existing_listing()
    notifier = RecordingNotifier()
    async with open_scan_pipeline(
        tmp_path / "bot.sqlite3", source, notifier, FrozenClock(NOW)
    ) as pipeline:
        await create_seeded_omega_rule(pipeline)
        source.listings_by_query[OMEGA_QUERY].append(pipeline.new_listing("m2"))
        notifier.is_failing = True
        await pipeline.run_scan_cycle()
        notifier.is_failing = False

        await pipeline.run_scan_cycle()
        await pipeline.run_scan_cycle()

    assert pipeline.listing_alert_item_ids() == []


async def test_abrupt_close_keeps_dedup_state_on_reopen(tmp_path: Path) -> None:
    database_path = tmp_path / "bot.sqlite3"
    source = build_source_with_existing_listing()
    notifier = RecordingNotifier()
    clock = FrozenClock(NOW)
    async with open_scan_pipeline(database_path, source, notifier, clock) as first_pipeline:
        await create_seeded_omega_rule(first_pipeline)
        source.listings_by_query[OMEGA_QUERY].append(first_pipeline.new_listing("m2"))
        await first_pipeline.run_scan_cycle()
        crashed_database_path = copy_database_files_while_open(database_path, tmp_path / "crashed")

    async with open_scan_pipeline(
        crashed_database_path, source, notifier, clock
    ) as second_pipeline:
        await second_pipeline.run_scan_cycle()
        await second_pipeline.run_scan_cycle()

    assert [listing.item_id for listing, _ in notifier.listing_alerts] == ["m2"]
