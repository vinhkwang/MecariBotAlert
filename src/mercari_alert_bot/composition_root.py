import asyncio
import logging
import random
import sys
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Final

import httpx
from fastapi import FastAPI

from mercari_alert_bot.application.services.baseline_seeding_service import (
    BaselineSeedingService,
)
from mercari_alert_bot.application.services.health_monitor_service import (
    HealthMonitorService,
    SystemAlertPolicy,
)
from mercari_alert_bot.application.services.keyword_rule_service import KeywordRuleService
from mercari_alert_bot.application.services.new_listing_detection_service import (
    NewListingDetectionService,
)
from mercari_alert_bot.application.services.polling_settings_service import (
    PollingSettingsService,
)
from mercari_alert_bot.application.services.scan_cycle_service import (
    ScanCycleOptions,
    ScanCycleService,
)
from mercari_alert_bot.application.services.system_status_service import SystemStatusService
from mercari_alert_bot.domain.models.polling_settings import PollingSettings
from mercari_alert_bot.infrastructure.config.env_settings import EnvSettings
from mercari_alert_bot.infrastructure.notifiers.telegram_client import TelegramClient
from mercari_alert_bot.infrastructure.notifiers.telegram_notifier import TelegramNotifier
from mercari_alert_bot.infrastructure.persistence.database import open_sqlite_database
from mercari_alert_bot.infrastructure.persistence.keyword_rule_yaml import (
    import_seed_rules_when_empty,
)
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
from mercari_alert_bot.infrastructure.scheduling.interval_scheduler import (
    IntervalScheduler,
    ScheduledJob,
)
from mercari_alert_bot.infrastructure.sources.dpop_proof_factory import DpopProofFactory
from mercari_alert_bot.infrastructure.sources.mercari_http_listing_source import (
    MercariHttpListingSource,
)
from mercari_alert_bot.infrastructure.sources.mercari_search_response_mapper import (
    MercariSearchResponseMapper,
)
from mercari_alert_bot.infrastructure.sources.retrying_listing_source import (
    RetryingListingSource,
    RetryPolicy,
)
from mercari_alert_bot.shared.clock import SystemClock
from mercari_alert_bot.shared.logging import configure_logging
from mercari_alert_bot.web.app import create_web_app
from mercari_alert_bot.web.dependencies import (
    provide_keyword_rule_service,
    provide_polling_settings_service,
    provide_system_status_service,
)

SCHEDULER_JITTER_RATIO: Final = 0.2
HTTP_TIMEOUT_SECONDS: Final = 20.0
_URL_LOGGING_LIBRARY_NAMES: Final = ("httpx", "httpcore")


@dataclass(frozen=True, slots=True)
class ScannerRuntime:
    scheduler: IntervalScheduler
    keyword_rule_service: KeywordRuleService
    polling_settings_service: PollingSettingsService
    system_status_service: SystemStatusService


def configure_process_logging(settings: EnvSettings) -> None:
    configure_logging(logging.getLevelNamesMapping()[settings.log_level], sys.stdout)
    for library_name in _URL_LOGGING_LIBRARY_NAMES:
        logging.getLogger(library_name).setLevel(logging.WARNING)


def build_default_polling_settings(settings: EnvSettings) -> PollingSettings:
    return PollingSettings(
        polling_gap_seconds=settings.polling_gap_seconds,
        is_item_detail_fetch_enabled=settings.is_item_detail_fetch_enabled,
        max_images_per_alert=settings.max_images_per_alert,
        consecutive_failure_alert_threshold=settings.consecutive_failure_alert_threshold,
        system_alert_cooldown_seconds=settings.system_alert_cooldown_seconds,
    )


def build_scan_cycle_options(polling_settings: PollingSettings) -> ScanCycleOptions:
    return ScanCycleOptions(
        rule_gap_seconds=polling_settings.polling_gap_seconds,
        is_item_detail_fetch_enabled=polling_settings.is_item_detail_fetch_enabled,
        max_images_per_alert=polling_settings.max_images_per_alert,
    )


def build_system_alert_policy(polling_settings: PollingSettings) -> SystemAlertPolicy:
    return SystemAlertPolicy(
        consecutive_failure_threshold=polling_settings.consecutive_failure_alert_threshold,
        alert_cooldown=timedelta(seconds=polling_settings.system_alert_cooldown_seconds),
    )


def build_scan_job(
    scan_cycle_service: ScanCycleService,
    health_monitor_service: HealthMonitorService,
    polling_settings_service: PollingSettingsService,
    system_status_service: SystemStatusService,
) -> ScheduledJob:
    async def run_monitored_scan_cycle() -> None:
        polling_settings = polling_settings_service.current_polling_settings
        report = await scan_cycle_service.run_scan_cycle(build_scan_cycle_options(polling_settings))
        system_status_service.record_scan_cycle(report)
        await health_monitor_service.assess_scan_cycle(
            report.rule_outcomes, build_system_alert_policy(polling_settings)
        )

    return run_monitored_scan_cycle


@asynccontextmanager
async def open_scanner(settings: EnvSettings) -> AsyncIterator[ScannerRuntime]:
    if settings.keyword_rule_source == "yaml":
        raise ValueError("keyword_rule_source 'yaml' has no repository implementation")
    clock = SystemClock()
    rng = random.Random()
    async with AsyncExitStack() as exit_stack:
        database = await open_sqlite_database(settings.database_path)
        exit_stack.push_async_callback(database.close)
        keyword_rule_repository = SqliteKeywordRuleRepository(database, clock)
        listing_repository = SqliteListingRepository(database)
        await import_seed_rules_when_empty(keyword_rule_repository, settings.keyword_seed_path)
        polling_settings_service = PollingSettingsService(
            SqlitePollingSettingsRepository(database, clock),
            build_default_polling_settings(settings),
        )
        await polling_settings_service.load_polling_settings()
        http_client = await exit_stack.enter_async_context(
            httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS)
        )
        listing_source = RetryingListingSource(
            MercariHttpListingSource(
                http_client,
                DpopProofFactory(clock),
                MercariSearchResponseMapper(),
                settings.search_page_size,
            ),
            RetryPolicy(),
            rng,
        )
        notifier = TelegramNotifier(
            TelegramClient(http_client, settings.telegram_bot_token, settings.telegram_chat_id),
            RetryPolicy(),
            rng,
        )
        scan_cycle_service = ScanCycleService(
            keyword_rule_repository=keyword_rule_repository,
            listing_source=listing_source,
            listing_repository=listing_repository,
            notifier=notifier,
            baseline_seeding_service=BaselineSeedingService(
                listing_source, listing_repository, keyword_rule_repository, clock
            ),
            new_listing_detection_service=NewListingDetectionService(listing_repository),
            clock=clock,
            sleep=asyncio.sleep,
        )
        health_monitor_service = HealthMonitorService(notifier, clock)
        system_status_service = SystemStatusService(SqliteListingHistoryReader(database))
        scheduler = IntervalScheduler(
            build_scan_job(
                scan_cycle_service,
                health_monitor_service,
                polling_settings_service,
                system_status_service,
            ),
            lambda: polling_settings_service.current_polling_settings.polling_gap_seconds,
            jitter_ratio=SCHEDULER_JITTER_RATIO,
            rng=rng,
        )
        yield ScannerRuntime(
            scheduler,
            KeywordRuleService(keyword_rule_repository),
            polling_settings_service,
            system_status_service,
        )


@asynccontextmanager
async def run_scanner_in_background(settings: EnvSettings) -> AsyncIterator[ScannerRuntime]:
    async with open_scanner(settings) as runtime:
        scanner_task = asyncio.create_task(runtime.scheduler.run())
        try:
            yield runtime
        finally:
            runtime.scheduler.request_stop()
            await scanner_task


def build_web_app(settings: EnvSettings) -> FastAPI:
    @asynccontextmanager
    async def scanner_lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with run_scanner_in_background(settings) as runtime:
            app.dependency_overrides[provide_keyword_rule_service] = lambda: (
                runtime.keyword_rule_service
            )
            app.dependency_overrides[provide_polling_settings_service] = lambda: (
                runtime.polling_settings_service
            )
            app.dependency_overrides[provide_system_status_service] = lambda: (
                runtime.system_status_service
            )
            try:
                yield
            finally:
                app.dependency_overrides.pop(provide_system_status_service, None)

    return create_web_app(scanner_lifespan)
