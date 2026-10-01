from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.money import JpyAmount
from mercari_alert_bot.domain.ports.listing_history_reader import ListingHistoryReader
from mercari_alert_bot.infrastructure.persistence.database import (
    SqliteDatabase,
    open_sqlite_database,
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
from tests.shared.fakes import FrozenClock

SEEN_AT = datetime(2026, 9, 29, 4, 0, tzinfo=UTC)
LISTED_AT = datetime(2026, 9, 29, 3, 0, tzinfo=UTC)


def build_listing(item_id: str, image_count: int = 2) -> Listing:
    return Listing(
        item_id=ItemId(item_id),
        kind=ListingKind.MERCARI,
        title=f"Title {item_id}",
        price=JpyAmount(120000),
        url=f"https://jp.mercari.com/item/{item_id}",
        image_urls=tuple(
            f"https://static.mercdn.net/{item_id}-{n}.jpg" for n in range(image_count)
        ),
        created_at=LISTED_AT,
    )


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "alerts.db"


@pytest.fixture
async def database(database_path: Path) -> AsyncIterator[SqliteDatabase]:
    opened = await open_sqlite_database(database_path)
    yield opened
    await opened.close()


@pytest.fixture
def reader(database: SqliteDatabase) -> SqliteListingHistoryReader:
    return SqliteListingHistoryReader(database)


@pytest.fixture
def listing_repository(database: SqliteDatabase) -> SqliteListingRepository:
    return SqliteListingRepository(database)


@pytest.fixture
def rule_repository(database: SqliteDatabase) -> SqliteKeywordRuleRepository:
    return SqliteKeywordRuleRepository(database, FrozenClock(SEEN_AT))


def test_reader_satisfies_listing_history_reader_port(database: SqliteDatabase) -> None:
    reader: ListingHistoryReader = SqliteListingHistoryReader(database)

    assert reader is not None


async def test_empty_database_reports_zero_and_no_alert(
    reader: SqliteListingHistoryReader,
) -> None:
    assert await reader.count_known_listings() == 0
    assert await reader.find_latest_notified_at() is None
    assert await reader.list_recent_listings(20) == []


async def test_count_known_listings_counts_each_item_once(
    reader: SqliteListingHistoryReader,
    listing_repository: SqliteListingRepository,
    rule_repository: SqliteKeywordRuleRepository,
) -> None:
    first_rule = await rule_repository.add_rule("omega", "omega")
    second_rule = await rule_repository.add_rule("seamaster", "seamaster")
    listing = build_listing("m1")
    await listing_repository.remember_listings([listing], first_rule.rule_id, SEEN_AT)
    await listing_repository.remember_listings([listing], second_rule.rule_id, SEEN_AT)

    assert await reader.count_known_listings() == 1


async def test_latest_notified_at_is_newest_notification(
    reader: SqliteListingHistoryReader,
    listing_repository: SqliteListingRepository,
    rule_repository: SqliteKeywordRuleRepository,
) -> None:
    rule = await rule_repository.add_rule("omega", "omega")
    await listing_repository.remember_listings(
        [build_listing("m1"), build_listing("m2"), build_listing("m3")], rule.rule_id, SEEN_AT
    )
    newest = SEEN_AT + timedelta(hours=2)
    await listing_repository.mark_listing_notified(ItemId("m1"), SEEN_AT + timedelta(hours=1))
    await listing_repository.mark_listing_notified(ItemId("m2"), newest)

    assert await reader.find_latest_notified_at() == newest


async def test_recent_listings_are_newest_first_and_limited(
    reader: SqliteListingHistoryReader,
    listing_repository: SqliteListingRepository,
    rule_repository: SqliteKeywordRuleRepository,
) -> None:
    rule = await rule_repository.add_rule("omega", "omega")
    for hour, item_id in enumerate(["m1", "m2", "m3"]):
        await listing_repository.remember_listings(
            [build_listing(item_id)], rule.rule_id, SEEN_AT + timedelta(hours=hour)
        )

    entries = await reader.list_recent_listings(2)

    assert [entry.listing.item_id for entry in entries] == ["m3", "m2"]


async def test_recent_listing_lists_every_matched_rule_name(
    reader: SqliteListingHistoryReader,
    listing_repository: SqliteListingRepository,
    rule_repository: SqliteKeywordRuleRepository,
) -> None:
    second_rule = await rule_repository.add_rule("seamaster", "seamaster")
    first_rule = await rule_repository.add_rule("omega", "omega")
    listing = build_listing("m1")
    await listing_repository.remember_listings([listing], second_rule.rule_id, SEEN_AT)
    await listing_repository.remember_listings([listing], first_rule.rule_id, SEEN_AT)

    entries = await reader.list_recent_listings(20)

    assert [entry.matched_rule_names for entry in entries] == [("omega", "seamaster")]


async def test_recent_listing_keeps_entry_after_rule_deletion(
    reader: SqliteListingHistoryReader,
    listing_repository: SqliteListingRepository,
    rule_repository: SqliteKeywordRuleRepository,
) -> None:
    rule = await rule_repository.add_rule("omega", "omega")
    await listing_repository.remember_listings([build_listing("m1")], rule.rule_id, SEEN_AT)
    await rule_repository.delete_rule(rule.rule_id)

    entries = await reader.list_recent_listings(20)

    assert [entry.listing.item_id for entry in entries] == ["m1"]
    assert entries[0].matched_rule_names == ()


async def test_recent_listing_round_trips_listing_fields_and_utc_times(
    database_path: Path,
    listing_repository: SqliteListingRepository,
    rule_repository: SqliteKeywordRuleRepository,
) -> None:
    rule = await rule_repository.add_rule("omega", "omega")
    listing = build_listing("m1")
    notified_at = SEEN_AT + timedelta(minutes=5)
    await listing_repository.remember_listings([listing], rule.rule_id, SEEN_AT)
    await listing_repository.mark_listing_notified(listing.item_id, notified_at)

    reopened = await open_sqlite_database(database_path)
    try:
        entries = await SqliteListingHistoryReader(reopened).list_recent_listings(20)
    finally:
        await reopened.close()

    assert len(entries) == 1
    assert entries[0].listing == listing
    assert entries[0].first_seen_at == SEEN_AT
    assert entries[0].notified_at == notified_at
    assert entries[0].is_notified
    assert entries[0].matched_rule_names == ("omega",)
