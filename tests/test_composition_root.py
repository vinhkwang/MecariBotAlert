import asyncio
import logging
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
import structlog
from fastapi.testclient import TestClient

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
    build_web_app,
    configure_process_logging,
    open_scanner,
    run_scanner_in_background,
)
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule
from mercari_alert_bot.infrastructure.config.env_settings import EnvSettings
from mercari_alert_bot.infrastructure.persistence.database import (
    SqliteDatabase,
    open_sqlite_database,
)
from mercari_alert_bot.infrastructure.persistence.sqlite_keyword_rule_repository import (
    SqliteKeywordRuleRepository,
)
from mercari_alert_bot.infrastructure.scheduling.interval_scheduler import (
    IntervalScheduler,
    ScheduledJob,
)
from mercari_alert_bot.shared.clock import SystemClock
from tests.fakes.in_memory_keyword_rule_repository import InMemoryKeywordRuleRepository
from tests.fakes.in_memory_listing_repository import InMemoryListingRepository
from tests.fakes.in_memory_listing_source import InMemoryListingSource
from tests.fakes.recording_notifier import RecordingNotifier
from tests.shared.fakes import FrozenClock

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
FAILURE_ALERT_PREFIX = "Keywords failing repeatedly:"


async def list_stored_rules(settings: EnvSettings) -> Sequence[KeywordRule]:
    database = await open_sqlite_database(settings.database_path)
    try:
        return await SqliteKeywordRuleRepository(database, SystemClock()).list_rules()
    finally:
        await database.close()


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


async def test_open_scanner_imports_seed_rules_and_closes_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build_settings(tmp_path)
    settings.keyword_seed_path.write_text(
        "keywords:\n  - name: omega\n    query: omega 168.005\n", encoding="utf-8"
    )
    captured_databases: list[SqliteDatabase] = []
    captured_clients: list[httpx.AsyncClient] = []

    async def open_and_capture_database(database_path: Path) -> SqliteDatabase:
        database = await open_sqlite_database(database_path)
        captured_databases.append(database)
        return database

    class CapturingAsyncClient(httpx.AsyncClient):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            captured_clients.append(self)

    monkeypatch.setattr(
        "mercari_alert_bot.composition_root.open_sqlite_database", open_and_capture_database
    )
    monkeypatch.setattr(
        "mercari_alert_bot.composition_root.httpx.AsyncClient", CapturingAsyncClient
    )

    async with open_scanner(settings) as runtime:
        assert isinstance(runtime.scheduler, IntervalScheduler)

    assert captured_clients[0].is_closed
    with pytest.raises(ValueError, match="no active connection"):
        await captured_databases[0].connection.execute("SELECT 1")

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


async def test_background_scanner_stops_promptly_on_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build_settings(tmp_path, polling_gap_seconds=3600)
    first_cycle_finished = asyncio.Event()

    def build_signalling_scan_job(*_args: Any) -> ScheduledJob:
        async def signal_first_cycle() -> None:
            first_cycle_finished.set()

        return signal_first_cycle

    monkeypatch.setattr(
        "mercari_alert_bot.composition_root.build_scan_job", build_signalling_scan_job
    )

    async with asyncio.timeout(5):
        async with run_scanner_in_background(settings):
            await first_cycle_finished.wait()


def test_build_web_app_starts_scanner_and_serves_index(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, polling_gap_seconds=3600)

    with TestClient(build_web_app(settings)) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert settings.database_path.exists()


def test_build_web_app_fails_startup_for_yaml_rule_source(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, keyword_rule_source="yaml")

    with pytest.raises(ValueError, match="yaml"), TestClient(build_web_app(settings)):
        pass


def test_build_web_app_serves_keywords_from_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def build_idle_scan_job(*_args: Any) -> ScheduledJob:
        async def run_nothing() -> None:
            return None

        return run_nothing

    monkeypatch.setattr("mercari_alert_bot.composition_root.build_scan_job", build_idle_scan_job)
    settings = build_settings(tmp_path, polling_gap_seconds=3600)
    settings.keyword_seed_path.write_text(
        "keywords:\n  - name: omega\n    query: omega 168.005\n", encoding="utf-8"
    )

    with TestClient(build_web_app(settings)) as client:
        listed = client.get("/api/keywords")
        created = client.post("/api/keywords", json={"name": "seiko", "query": "seiko 6139"})

    assert [rule["name"] for rule in listed.json()] == ["omega"]
    assert created.status_code == 201
    assert [rule.name for rule in asyncio.run(list_stored_rules(settings))] == ["omega", "seiko"]
