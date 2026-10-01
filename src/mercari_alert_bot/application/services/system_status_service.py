from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from mercari_alert_bot.application.services.scan_cycle_service import ScanCycleReport
from mercari_alert_bot.domain.models.listing_history import ListingHistoryEntry
from mercari_alert_bot.domain.ports.listing_history_reader import ListingHistoryReader


@dataclass(frozen=True, slots=True, kw_only=True)
class ScanCycleSummary:
    started_at: datetime
    finished_at: datetime
    succeeded_rule_count: int
    failed_rule_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SystemStatus:
    last_scan_cycle: ScanCycleSummary | None
    consecutive_failed_cycle_count: int
    known_listing_count: int
    last_alert_sent_at: datetime | None


class SystemStatusService:
    def __init__(self, listing_history_reader: ListingHistoryReader) -> None:
        self._listing_history_reader = listing_history_reader
        self._last_scan_cycle: ScanCycleSummary | None = None
        self._consecutive_failed_cycle_count = 0

    def record_scan_cycle(self, report: ScanCycleReport) -> None:
        self._last_scan_cycle = ScanCycleSummary(
            started_at=report.started_at,
            finished_at=report.finished_at,
            succeeded_rule_count=len(report.scanned_rule_names) + len(report.seeded_rule_names),
            failed_rule_count=len(report.failed_rule_names),
        )
        if report.failed_rule_names:
            self._consecutive_failed_cycle_count += 1
        else:
            self._consecutive_failed_cycle_count = 0

    async def describe_system_status(self) -> SystemStatus:
        return SystemStatus(
            last_scan_cycle=self._last_scan_cycle,
            consecutive_failed_cycle_count=self._consecutive_failed_cycle_count,
            known_listing_count=await self._listing_history_reader.count_known_listings(),
            last_alert_sent_at=await self._listing_history_reader.find_latest_notified_at(),
        )

    async def list_recent_listings(self, limit: int) -> Sequence[ListingHistoryEntry]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        return await self._listing_history_reader.list_recent_listings(limit)
