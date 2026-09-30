import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Final

import structlog

from mercari_alert_bot.application.services.baseline_seeding_service import (
    BaselineSeedingService,
)
from mercari_alert_bot.application.services.new_listing_detection_service import (
    NewListingDetectionService,
)
from mercari_alert_bot.domain.errors import (
    KeywordRuleNotFoundError,
    ListingSourceError,
    NotificationDeliveryError,
)
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule
from mercari_alert_bot.domain.models.listing import ItemId, Listing
from mercari_alert_bot.domain.ports.keyword_rule_repository import KeywordRuleRepository
from mercari_alert_bot.domain.ports.listing_repository import ListingRepository
from mercari_alert_bot.domain.ports.listing_source import ListingSource
from mercari_alert_bot.domain.ports.notifier import Notifier
from mercari_alert_bot.shared.clock import Clock

Sleep = Callable[[float], Awaitable[None]]

_ISOLATED_RULE_ERRORS: Final = (ListingSourceError, KeywordRuleNotFoundError)
_RULE_NAME_SEPARATOR: Final = ", "

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class ScanCycleOptions:
    rule_gap_seconds: float
    is_item_detail_fetch_enabled: bool
    max_images_per_alert: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ScanCycleReport:
    cycle_id: str
    started_at: datetime
    finished_at: datetime
    scanned_rule_names: tuple[str, ...]
    seeded_rule_names: tuple[str, ...]
    failed_rule_names: tuple[str, ...]
    fetched_listing_count: int
    sent_alert_count: int
    failed_alert_count: int


@dataclass(slots=True)
class _MatchedListing:
    listing: Listing
    matched_rules: list[KeywordRule] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _ScannedRule:
    rule: KeywordRule
    unseen_listings: tuple[Listing, ...]


@dataclass(slots=True)
class _CycleTally:
    scanned_rules: list[_ScannedRule] = field(default_factory=list)
    seeded_rule_names: list[str] = field(default_factory=list)
    failed_rule_names: list[str] = field(default_factory=list)
    matches_by_item_id: dict[ItemId, _MatchedListing] = field(default_factory=dict)
    fetched_listing_count: int = 0
    sent_alert_count: int = 0
    failed_alert_count: int = 0


class ScanCycleService:
    def __init__(
        self,
        keyword_rule_repository: KeywordRuleRepository,
        listing_source: ListingSource,
        listing_repository: ListingRepository,
        notifier: Notifier,
        baseline_seeding_service: BaselineSeedingService,
        new_listing_detection_service: NewListingDetectionService,
        clock: Clock,
        sleep: Sleep,
    ) -> None:
        self._keyword_rule_repository = keyword_rule_repository
        self._listing_source = listing_source
        self._listing_repository = listing_repository
        self._notifier = notifier
        self._baseline_seeding_service = baseline_seeding_service
        self._new_listing_detection_service = new_listing_detection_service
        self._clock = clock
        self._sleep = sleep

    async def run_scan_cycle(self, options: ScanCycleOptions) -> ScanCycleReport:
        cycle_id = uuid.uuid4().hex
        started_at = self._clock.now()
        with structlog.contextvars.bound_contextvars(cycle_id=cycle_id):
            tally = _CycleTally()
            await self._scan_enabled_rules(options, tally)
            await self._remember_unseen_listings(tally)
            await self._send_listing_alerts(options, tally)
            await self._send_seed_summary(tally)
            report = self._build_report(cycle_id, started_at, tally)
            logger.info(
                "scan_cycle_completed",
                scanned_rule_count=len(report.scanned_rule_names),
                seeded_rule_count=len(report.seeded_rule_names),
                failed_rule_count=len(report.failed_rule_names),
                fetched_listing_count=report.fetched_listing_count,
                sent_alert_count=report.sent_alert_count,
                failed_alert_count=report.failed_alert_count,
                duration_seconds=(report.finished_at - report.started_at).total_seconds(),
            )
            return report

    async def _scan_enabled_rules(self, options: ScanCycleOptions, tally: _CycleTally) -> None:
        rules = await self._keyword_rule_repository.list_rules()
        enabled_rules = [rule for rule in rules if rule.is_enabled]
        for position, rule in enumerate(enabled_rules):
            if position > 0:
                await self._sleep(options.rule_gap_seconds)
            with structlog.contextvars.bound_contextvars(rule_name=rule.name):
                await self._scan_rule_isolated(rule, tally)

    async def _scan_rule_isolated(self, rule: KeywordRule, tally: _CycleTally) -> None:
        try:
            if rule.has_baseline:
                await self._detect_rule_listings(rule, tally)
            else:
                await self._seed_rule(rule, tally)
        except _ISOLATED_RULE_ERRORS as error:
            logger.warning("rule_scan_failed", error_type=type(error).__name__)
            tally.failed_rule_names.append(rule.name)

    async def _seed_rule(self, rule: KeywordRule, tally: _CycleTally) -> None:
        seeded_rule = await self._baseline_seeding_service.seed_rule_baseline(rule)
        if seeded_rule.has_baseline:
            tally.seeded_rule_names.append(rule.name)

    async def _detect_rule_listings(self, rule: KeywordRule, tally: _CycleTally) -> None:
        listings = await self._listing_source.fetch_latest_listings(rule.query)
        tally.fetched_listing_count += len(listings)
        detected = await self._new_listing_detection_service.detect_new_listings(rule, listings)
        for listing in detected.fresh_listings:
            match = tally.matches_by_item_id.setdefault(listing.item_id, _MatchedListing(listing))
            match.matched_rules.append(rule)
        unseen_listings = detected.fresh_listings + detected.stale_listings
        tally.scanned_rules.append(_ScannedRule(rule, unseen_listings))

    async def _remember_unseen_listings(self, tally: _CycleTally) -> None:
        seen_at = self._clock.now()
        for scanned in tally.scanned_rules:
            await self._listing_repository.remember_listings(
                scanned.unseen_listings, scanned.rule.rule_id, seen_at
            )

    async def _send_listing_alerts(self, options: ScanCycleOptions, tally: _CycleTally) -> None:
        for match in tally.matches_by_item_id.values():
            listing = await self._attach_alert_images(match.listing, options)
            await self._send_listing_alert(listing, match.matched_rules, tally)

    async def _attach_alert_images(self, listing: Listing, options: ScanCycleOptions) -> Listing:
        image_urls = listing.image_urls
        if options.is_item_detail_fetch_enabled:
            try:
                image_urls = await self._listing_source.fetch_listing_image_urls(listing)
            except ListingSourceError as error:
                logger.warning(
                    "listing_image_fetch_failed",
                    item_id=listing.item_id,
                    error_type=type(error).__name__,
                )
        return replace(listing, image_urls=image_urls[: options.max_images_per_alert])

    async def _send_listing_alert(
        self, listing: Listing, matched_rules: list[KeywordRule], tally: _CycleTally
    ) -> None:
        matched_rule_names = [rule.name for rule in matched_rules]
        try:
            await self._notifier.send_listing_alert(listing, matched_rules)
        except NotificationDeliveryError as error:
            tally.failed_alert_count += 1
            logger.warning(
                "listing_alert_failed",
                item_id=listing.item_id,
                matched_rule_names=matched_rule_names,
                error_type=type(error).__name__,
            )
            return
        await self._listing_repository.mark_listing_notified(listing.item_id, self._clock.now())
        tally.sent_alert_count += 1
        logger.info(
            "listing_alert_sent",
            item_id=listing.item_id,
            matched_rule_names=matched_rule_names,
        )

    async def _send_seed_summary(self, tally: _CycleTally) -> None:
        if not tally.seeded_rule_names:
            return
        rule_names = _RULE_NAME_SEPARATOR.join(tally.seeded_rule_names)
        message = (
            f"Baseline seeded for {len(tally.seeded_rule_names)} rule(s): {rule_names}. "
            "Alerts start next cycle."
        )
        try:
            await self._notifier.send_system_alert(message)
        except NotificationDeliveryError as error:
            logger.warning("seed_summary_failed", error_type=type(error).__name__)

    def _build_report(
        self, cycle_id: str, started_at: datetime, tally: _CycleTally
    ) -> ScanCycleReport:
        return ScanCycleReport(
            cycle_id=cycle_id,
            started_at=started_at,
            finished_at=self._clock.now(),
            scanned_rule_names=tuple(scanned.rule.name for scanned in tally.scanned_rules),
            seeded_rule_names=tuple(tally.seeded_rule_names),
            failed_rule_names=tuple(tally.failed_rule_names),
            fetched_listing_count=tally.fetched_listing_count,
            sent_alert_count=tally.sent_alert_count,
            failed_alert_count=tally.failed_alert_count,
        )
