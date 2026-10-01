from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from mercari_alert_bot.application.services.scan_cycle_service import ScanCycleReport
from mercari_alert_bot.application.services.system_status_service import SystemStatusService
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.listing_history import ListingHistoryEntry
from mercari_alert_bot.domain.models.money import JpyAmount
from mercari_alert_bot.web.app import create_web_app
from mercari_alert_bot.web.dependencies import provide_system_status_service
from tests.fakes.in_memory_listing_history_reader import InMemoryListingHistoryReader
from tests.web.test_app import RecordingLifespan

STARTED_AT = datetime(2026, 9, 29, 4, 0, tzinfo=UTC)
FINISHED_AT = STARTED_AT + timedelta(seconds=30)


def build_entry(
    item_id: str, *, image_urls: tuple[str, ...] = (), notified_at: datetime | None = None
) -> ListingHistoryEntry:
    return ListingHistoryEntry(
        listing=Listing(
            item_id=ItemId(item_id),
            kind=ListingKind.MERCARI,
            title=f"Title {item_id}",
            price=JpyAmount(1500),
            url=f"https://jp.mercari.com/item/{item_id}",
            image_urls=image_urls,
            created_at=STARTED_AT,
        ),
        matched_rule_names=("omega", "seamaster"),
        first_seen_at=STARTED_AT,
        notified_at=notified_at,
    )


def build_report() -> ScanCycleReport:
    return ScanCycleReport(
        cycle_id="cycle-1",
        started_at=STARTED_AT,
        finished_at=FINISHED_AT,
        scanned_rule_names=("omega",),
        seeded_rule_names=(),
        failed_rule_names=("seamaster",),
        fetched_listing_count=0,
        sent_alert_count=0,
        failed_alert_count=0,
        rule_outcomes=(),
    )


@pytest.fixture
def reader() -> InMemoryListingHistoryReader:
    return InMemoryListingHistoryReader()


@pytest.fixture
def service(reader: InMemoryListingHistoryReader) -> SystemStatusService:
    return SystemStatusService(reader)


@pytest.fixture
def client(service: SystemStatusService) -> Iterator[TestClient]:
    app = create_web_app(RecordingLifespan())
    app.dependency_overrides[provide_system_status_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client


def test_status_without_cycle_returns_null_last_cycle(client: TestClient) -> None:
    response = client.get("/api/status")

    assert response.status_code == 200
    assert response.json() == {
        "last_scan_cycle": None,
        "consecutive_failed_cycle_count": 0,
        "known_listing_count": 0,
        "last_alert_sent_at": None,
    }


def test_status_returns_cycle_in_ict(client: TestClient, service: SystemStatusService) -> None:
    service.record_scan_cycle(build_report())

    body = client.get("/api/status").json()

    assert body["last_scan_cycle"] == {
        "started_at": "2026-09-29T11:00:00+07:00",
        "finished_at": "2026-09-29T11:00:30+07:00",
        "duration_seconds": 30.0,
        "succeeded_rule_count": 1,
        "failed_rule_count": 1,
    }
    assert body["consecutive_failed_cycle_count"] == 1


def test_listings_default_limit_is_twenty(
    client: TestClient, reader: InMemoryListingHistoryReader
) -> None:
    client.get("/api/listings")

    assert reader.requested_limits == [20]


def test_listings_maps_delivery_status_and_thumbnail(
    client: TestClient, reader: InMemoryListingHistoryReader
) -> None:
    reader.entries = [
        build_entry(
            "m1",
            image_urls=("https://static.mercdn.net/a.jpg", "https://static.mercdn.net/b.jpg"),
            notified_at=STARTED_AT + timedelta(minutes=1),
        ),
        build_entry("m2"),
    ]

    notified, not_notified = client.get("/api/listings").json()

    assert notified["telegram_delivery"] == "sent"
    assert notified["notified_at"] == "2026-09-29T11:01:00+07:00"
    assert notified["thumbnail_url"] == "https://static.mercdn.net/a.jpg"
    assert notified["matched_rule_names"] == ["omega", "seamaster"]
    assert notified["price_jpy"] == 1500
    assert notified["first_seen_at"] == "2026-09-29T11:00:00+07:00"
    assert not_notified["telegram_delivery"] == "not_sent"
    assert not_notified["notified_at"] is None
    assert not_notified["thumbnail_url"] is None


@pytest.mark.parametrize("limit", [0, 101])
def test_listings_rejects_out_of_range_limit(client: TestClient, limit: int) -> None:
    assert client.get("/api/listings", params={"limit": limit}).status_code == 422
