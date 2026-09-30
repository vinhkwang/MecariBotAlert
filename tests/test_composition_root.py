import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import structlog

from mercari_alert_bot.application.services.baseline_seeding_service import (
    BaselineSeedingService,
)
from mercari_alert_bot.application.services.health_monitor_service import HealthMonitorService
from mercari_alert_bot.application.services.new_listing_detection_service import (
    NewListingDetectionService,
)
from mercari_alert_bot.application.services.scan_cycle_service import (
    ScanCycleOptions,
    ScanCycleService,
)
from mercari_alert_bot.composition_root import (
    build_scan_cycle_options,
    build_scan_job,
    configure_process_logging,
    open_scanner,
)
from mercari_alert_bot.infrastructure.config.env_settings import EnvSettings
from mercari_alert_bot.infrastructure.persistence.database import open_sqlite_database
from mercari_alert_bot.infrastructure.persistence.sqlite_keyword_rule_repository import (
    SqliteKeywordRuleRepository,
)
from mercari_alert_bot.infrastructure.scheduling.interval_scheduler import IntervalScheduler
from mercari_alert_bot.shared.clock import SystemClock
from tests.fakes.in_memory_keyword_rule_repository import InMemoryKeywordRuleRepository
from tests.fakes.in_memory_listing_repository import InMemoryListingRepository
from tests.fakes.in_memory_listing_source import InMemoryListingSource
from tests.fakes.recording_notifier import RecordingNotifier
from tests.shared.fakes import FrozenClock

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
FAILURE_ALERT_PREFIX = "Keywords failing repeatedly:"


def build_settings(tmp_path: Path, **overrides: Any) -> EnvSettings:
    values: dict[str, Any] = {
        "telegram_bot_token": "test-token",
        "telegram_chat_id": "test-chat",
        "database_path": tmp_path / "bot.sqlite3",
        "keyword_seed_path": tmp_path / "keywords.yaml",
        **overrides,
    }
    return EnvSettings(_env_file=None, **values)


async def skip_sleep(_seconds: float) -> None:
    return None


class ScanJobHarness:
    def __init__(self, settings: EnvSettings) -> None:
        self.source = InMemoryListingSource()
        self.rules = InMemoryKeywordRuleRepository()
        self.notifier = RecordingNotifier()
        listings = InMemoryListingRepository()
        clock = FrozenClock(NOW)
        scan_cycle_service = ScanCycleService(
            keyword_rule_repository=self.rules,
            listing_source=self.source,
            listing_repository=listings,
            notifier=self.notifier,
            baseline_seeding_service=BaselineSeedingService(
                self.source, listings, self.rules, clock
            ),
            new_listing_detection_service=NewListingDetectionService(listings),
            clock=clock,
            sleep=skip_sleep,
        )
        health_monitor_service = HealthMonitorService(
            self.notifier,
            clock,
            consecutive_failure_threshold=settings.consecutive_failure_alert_threshold,
            alert_cooldown=timedelta(seconds=settings.system_alert_cooldown_seconds),
        )
        self.job = build_scan_job(scan_cycle_service, health_monitor_service, settings)

    async def add_seeded_rule(self, name: str, query: str) -> None:
        rule = await self.rules.add_rule(name, query)
        await self.rules.save_rule(replace(rule, baseline_established_at=NOW))

    def failure_alerts(self) -> list[str]:
        return [
            alert for alert in self.notifier.system_alerts if alert.startswith(FAILURE_ALERT_PREFIX)
        ]


def test_build_scan_cycle_options_maps_settings(tmp_path: Path) -> None:
    settings = build_settings(
        tmp_path,
        polling_gap_seconds=18,
        is_item_detail_fetch_enabled=False,
        max_images_per_alert=2,
    )

    assert build_scan_cycle_options(settings) == ScanCycleOptions(
        rule_gap_seconds=18,
        is_item_detail_fetch_enabled=False,
        max_images_per_alert=2,
    )


async def test_scan_job_alerts_when_every_rule_returns_zero_listings(tmp_path: Path) -> None:
    harness = ScanJobHarness(build_settings(tmp_path))
    await harness.add_seeded_rule("omega", "omega query")
    await harness.add_seeded_rule("seiko", "seiko query")

    await harness.job()

    assert harness.notifier.system_alerts == [
        "Every scanned keyword returned zero listings. The Mercari source may be broken."
    ]


async def test_scan_job_alerts_after_consecutive_failures_reach_threshold(
    tmp_path: Path,
) -> None:
    harness = ScanJobHarness(build_settings(tmp_path, consecutive_failure_alert_threshold=2))
    await harness.add_seeded_rule("omega", "omega query")
    harness.source.failing_queries.add("omega query")

    await harness.job()
    alerts_after_first_run = harness.failure_alerts()
    await harness.job()

    assert alerts_after_first_run == []
    assert harness.failure_alerts() == ["Keywords failing repeatedly:\n- omega: 2 scans in a row"]


async def test_open_scanner_imports_seed_rules_and_closes_database(tmp_path: Path) -> None:
    settings = build_settings(tmp_path)
    settings.keyword_seed_path.write_text(
        "keywords:\n  - name: omega\n    query: omega 168.005\n", encoding="utf-8"
    )

    async with open_scanner(settings) as scheduler:
        assert isinstance(scheduler, IntervalScheduler)

    database = await open_sqlite_database(settings.database_path)
    try:
        rules = await SqliteKeywordRuleRepository(database, SystemClock()).list_rules()
    finally:
        await database.close()
    assert [(rule.name, rule.query) for rule in rules] == [("omega", "omega 168.005")]


async def test_open_scanner_rejects_yaml_rule_source(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, keyword_rule_source="yaml")

    with pytest.raises(ValueError, match="yaml"):
        async with open_scanner(settings):
            pass

    assert not settings.database_path.exists()


def test_configure_process_logging_silences_httpx_info(tmp_path: Path) -> None:
    try:
        configure_process_logging(build_settings(tmp_path, log_level="DEBUG"))

        assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
        assert not logging.getLogger("httpcore").isEnabledFor(logging.INFO)
    finally:
        logging.getLogger("httpx").setLevel(logging.NOTSET)
        logging.getLogger("httpcore").setLevel(logging.NOTSET)
        structlog.reset_defaults()
