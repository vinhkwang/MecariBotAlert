from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel

from mercari_alert_bot.application.services.system_status_service import (
    ScanCycleSummary,
    SystemStatus,
)
from mercari_alert_bot.domain.models.listing_history import ListingHistoryEntry
from mercari_alert_bot.shared.ict_time import ICT_TIMEZONE


def _to_ict(moment: datetime) -> datetime:
    return moment.astimezone(ICT_TIMEZONE)


class ScanCycleResponse(BaseModel):
    started_at: datetime
    finished_at: datetime
    duration_seconds: float
    succeeded_rule_count: int
    failed_rule_count: int

    @classmethod
    def from_summary(cls, summary: ScanCycleSummary) -> Self:
        return cls(
            started_at=_to_ict(summary.started_at),
            finished_at=_to_ict(summary.finished_at),
            duration_seconds=(summary.finished_at - summary.started_at).total_seconds(),
            succeeded_rule_count=summary.succeeded_rule_count,
            failed_rule_count=summary.failed_rule_count,
        )


class SystemStatusResponse(BaseModel):
    last_scan_cycle: ScanCycleResponse | None
    consecutive_failed_cycle_count: int
    known_listing_count: int
    last_alert_sent_at: datetime | None

    @classmethod
    def from_status(cls, status: SystemStatus) -> Self:
        last_scan_cycle = status.last_scan_cycle
        last_alert_sent_at = status.last_alert_sent_at
        return cls(
            last_scan_cycle=(
                None if last_scan_cycle is None else ScanCycleResponse.from_summary(last_scan_cycle)
            ),
            consecutive_failed_cycle_count=status.consecutive_failed_cycle_count,
            known_listing_count=status.known_listing_count,
            last_alert_sent_at=None if last_alert_sent_at is None else _to_ict(last_alert_sent_at),
        )


class RecentListingResponse(BaseModel):
    item_id: str
    title: str
    price_jpy: int
    url: str
    thumbnail_url: str | None
    matched_rule_names: list[str]
    first_seen_at: datetime
    telegram_delivery: Literal["sent", "not_sent"]
    notified_at: datetime | None

    @classmethod
    def from_entry(cls, entry: ListingHistoryEntry) -> Self:
        listing = entry.listing
        notified_at = entry.notified_at
        return cls(
            item_id=listing.item_id,
            title=listing.title,
            price_jpy=listing.price.yen,
            url=listing.url,
            thumbnail_url=listing.image_urls[0] if listing.image_urls else None,
            matched_rule_names=list(entry.matched_rule_names),
            first_seen_at=_to_ict(entry.first_seen_at),
            telegram_delivery="sent" if entry.is_notified else "not_sent",
            notified_at=None if notified_at is None else _to_ict(notified_at),
        )
