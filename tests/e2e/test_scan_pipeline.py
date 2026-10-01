from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Final

from mercari_alert_bot.application.services.baseline_seeding_service import (
    BaselineSeedingService,
)
from mercari_alert_bot.application.services.health_monitor_service import HealthMonitorService
from mercari_alert_bot.application.services.keyword_rule_service import KeywordRuleService
from mercari_alert_bot.application.services.new_listing_detection_service import (
    NewListingDetectionService,
)
from mercari_alert_bot.application.services.polling_settings_service import (
    PollingSettingsService,
)
from mercari_alert_bot.application.services.scan_cycle_service import ScanCycleService
from mercari_alert_bot.application.services.system_status_service import SystemStatusService
from mercari_alert_bot.composition_root import build_default_polling_settings, build_scan_job
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.money import JpyAmount
from mercari_alert_bot.infrastructure.config.env_settings import EnvSettings
from mercari_alert_bot.infrastructure.persistence.database import open_sqlite_database
from mercari_alert_bot.infrastructure.persistence.sqlite_keyword_rule_repository import (
    SqliteKeywordRuleRepository,
)
from mercari_alert_bot.infrastructure.persistence.sqlite_listing_history_reader import (
    SqliteListingHistoryReader,
)
from mercari_alert_bot.infrastructure.persistence.sqlite_listing_repository import (
    SqliteListingRepository,
)
from mercari_alert_bot.infrastructure.persistence.sqlite_polling_settings_repository import (
    SqlitePollingSettingsRepository,
)
from mercari_alert_bot.infrastructure.scheduling.interval_scheduler import ScheduledJob
from tests.fakes.in_memory_listing_source import InMemoryListingSource
from tests.fakes.recording_notifier import RecordingNotifier
from tests.shared.fakes import FrozenClock

NOW: Final = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
CYCLE_INTERVAL: Final = timedelta(minutes=5)


def build_listing(item_id: str, created_at: datetime) -> Listing:
    return Listing(
        item_id=ItemId(item_id),
        kind=ListingKind.MERCARI,
        title=f"title {item_id}",
        price=JpyAmount(1000),
        url=f"https://jp.mercari.com/item/{item_id}",
        image_urls=(),
        created_at=created_at,
    )


async def skip_sleep(_seconds: float) -> None:
    return None


class ScanPipeline:
    def __init__(
        self,
        scan_job: ScheduledJob,
        source: InMemoryListingSource,
        notifier: RecordingNotifier,
        clock: FrozenClock,
        keyword_rule_service: KeywordRuleService,
        system_status_service: SystemStatusService,
    ) -> None:
        self._scan_job = scan_job
        self.source = source
        self.notifier = notifier
        self.clock = clock
        self.keyword_rule_service = keyword_rule_service
        self.system_status_service = system_status_service

    async def run_scan_cycle(self) -> None:
        self.clock.advance(CYCLE_INTERVAL)
        await self._scan_job()

    def listing_alert_item_ids(self) -> list[str]:
        return [listing.item_id for listing, _ in self.notifier.listing_alerts]

    def new_listing(self, item_id: str) -> Listing:
        return build_listing(item_id, self.clock.now() + timedelta(seconds=1))


def build_settings(database_path: Path) -> EnvSettings:
    return EnvSettings(
        _env_file=None,
        telegram_bot_token="test-token",
        telegram_chat_id="test-chat",
        database_path=database_path,
        keyword_seed_path=database_path.parent / "keywords.yaml",
    )


@asynccontextmanager
async def open_scan_pipeline(
    database_path: Path,
    source: InMemoryListingSource,
    notifier: RecordingNotifier,
    clock: FrozenClock,
) -> AsyncIterator[ScanPipeline]:
    database = await open_sqlite_database(database_path)
    try:
        keyword_rule_repository = SqliteKeywordRuleRepository(database, clock)
        listing_repository = SqliteListingRepository(database)
        polling_settings_service = PollingSettingsService(
            SqlitePollingSettingsRepository(database, clock),
            build_default_polling_settings(build_settings(database_path)),
        )
        await polling_settings_service.load_polling_settings()
        scan_cycle_service = ScanCycleService(
            keyword_rule_repository=keyword_rule_repository,
            listing_source=source,
            listing_repository=listing_repository,
            notifier=notifier,
            baseline_seeding_service=BaselineSeedingService(
                source, listing_repository, keyword_rule_repository, clock
            ),
            new_listing_detection_service=NewListingDetectionService(listing_repository),
            clock=clock,
            sleep=skip_sleep,
        )
        system_status_service = SystemStatusService(SqliteListingHistoryReader(database))
        scan_job = build_scan_job(
            scan_cycle_service,
            HealthMonitorService(notifier, clock),
            polling_settings_service,
            system_status_service,
        )
        yield ScanPipeline(
            scan_job,
            source,
            notifier,
            clock,
            KeywordRuleService(keyword_rule_repository),
            system_status_service,
        )
    finally:
        await database.close()


async def test_first_cycle_seeds_baseline_without_listing_alerts(tmp_path: Path) -> None:
    source = InMemoryListingSource()
    source.listings_by_query["omega query"] = [
        build_listing(f"m{number}", NOW - timedelta(days=1)) for number in range(3)
    ]
    notifier = RecordingNotifier()
    async with open_scan_pipeline(
        tmp_path / "bot.sqlite3", source, notifier, FrozenClock(NOW)
    ) as pipeline:
        await pipeline.keyword_rule_service.create_rule("omega", "omega query", is_enabled=True)

        await pipeline.run_scan_cycle()

    assert notifier.listing_alerts == []
    assert notifier.system_alerts == [
        "Baseline seeded for 1 rule(s): omega. Alerts start next cycle."
    ]


async def test_new_listing_after_baseline_sends_one_alert(tmp_path: Path) -> None:
    source = InMemoryListingSource()
    source.listings_by_query["omega query"] = [build_listing("m1", NOW - timedelta(days=1))]
    notifier = RecordingNotifier()
    async with open_scan_pipeline(
        tmp_path / "bot.sqlite3", source, notifier, FrozenClock(NOW)
    ) as pipeline:
        await pipeline.keyword_rule_service.create_rule("omega", "omega query", is_enabled=True)
        await pipeline.run_scan_cycle()
        source.listings_by_query["omega query"].append(pipeline.new_listing("m2"))

        await pipeline.run_scan_cycle()

    assert pipeline.listing_alert_item_ids() == ["m2"]


async def test_same_listing_is_not_alerted_twice(tmp_path: Path) -> None:
    source = InMemoryListingSource()
    source.listings_by_query["omega query"] = []
    notifier = RecordingNotifier()
    async with open_scan_pipeline(
        tmp_path / "bot.sqlite3", source, notifier, FrozenClock(NOW)
    ) as pipeline:
        await pipeline.keyword_rule_service.create_rule("omega", "omega query", is_enabled=True)
        await pipeline.run_scan_cycle()
        source.listings_by_query["omega query"].append(pipeline.new_listing("m2"))

        await pipeline.run_scan_cycle()
        await pipeline.run_scan_cycle()

    assert pipeline.listing_alert_item_ids() == ["m2"]
