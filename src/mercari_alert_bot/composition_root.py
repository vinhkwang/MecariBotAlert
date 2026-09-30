import asyncio
import logging
import random
import sys
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import timedelta
from typing import Final

import httpx

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
from mercari_alert_bot.infrastructure.persistence.sqlite_listing_repository import (
    SqliteListingRepository,
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

SCHEDULER_JITTER_RATIO: Final = 0.2
HTTP_TIMEOUT_SECONDS: Final = 20.0
_URL_LOGGING_LIBRARY_NAMES: Final = ("httpx", "httpcore")


def configure_process_logging(settings: EnvSettings) -> None:
    configure_logging(logging.getLevelNamesMapping()[settings.log_level], sys.stdout)
    for library_name in _URL_LOGGING_LIBRARY_NAMES:
        logging.getLogger(library_name).setLevel(logging.WARNING)


def build_scan_cycle_options(settings: EnvSettings) -> ScanCycleOptions:
    return ScanCycleOptions(
        rule_gap_seconds=settings.polling_gap_seconds,
        is_item_detail_fetch_enabled=settings.is_item_detail_fetch_enabled,
        max_images_per_alert=settings.max_images_per_alert,
    )


def build_scan_job(
    scan_cycle_service: ScanCycleService,
    health_monitor_service: HealthMonitorService,
    settings: EnvSettings,
) -> ScheduledJob:
    async def run_monitored_scan_cycle() -> None:
        report = await scan_cycle_service.run_scan_cycle(build_scan_cycle_options(settings))
        await health_monitor_service.assess_scan_cycle(report.rule_outcomes)

    return run_monitored_scan_cycle


@asynccontextmanager
async def open_scanner(settings: EnvSettings) -> AsyncIterator[IntervalScheduler]:
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
        health_monitor_service = HealthMonitorService(
            notifier,
            clock,
            consecutive_failure_threshold=settings.consecutive_failure_alert_threshold,
            alert_cooldown=timedelta(seconds=settings.system_alert_cooldown_seconds),
        )
        yield IntervalScheduler(
            build_scan_job(scan_cycle_service, health_monitor_service, settings),
            lambda: settings.polling_gap_seconds,
            jitter_ratio=SCHEDULER_JITTER_RATIO,
            rng=rng,
        )
