from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
import pytest

from mercari_alert_bot.domain.errors import InvalidDomainValueError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRuleId
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.money import JpyAmount
from mercari_alert_bot.domain.ports.listing_repository import ListingRepository
from mercari_alert_bot.infrastructure.persistence.database import (
    SqliteDatabase,
    open_sqlite_database,
)
from mercari_alert_bot.infrastructure.persistence.sqlite_listing_repository import (
    SqliteListingRepository,
    UnknownListingError,
)

RULE_ID = KeywordRuleId(1)
OTHER_RULE_ID = KeywordRuleId(2)
SEEN_AT = datetime(2026, 9, 29, 4, 0, tzinfo=UTC)
LATER_SEEN_AT = SEEN_AT + timedelta(hours=1)
JAPAN_STANDARD_TIME = timezone(timedelta(hours=9))
NAIVE_MOMENT = datetime(2026, 9, 29, 4, 0)


def build_listing(item_id: str, title: str = "OMEGA Seamaster") -> Listing:
    return Listing(
        item_id=ItemId(item_id),
        kind=ListingKind.MERCARI,
        title=title,
        price=JpyAmount(120000),
        url=f"https://jp.mercari.com/item/{item_id}",
        image_urls=(f"https://static.mercdn.net/{item_id}.jpg",),
        created_at=datetime(2026, 9, 29, 3, 0, tzinfo=UTC),
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
def repository(database: SqliteDatabase) -> SqliteListingRepository:
    return SqliteListingRepository(database)


async def fetch_rows(database_path: Path, query: str) -> list[tuple[object, ...]]:
    async with (
        aiosqlite.connect(database_path) as independent_connection,
        independent_connection.execute(query) as cursor,
    ):
        rows = await cursor.fetchall()
    return [tuple(row) for row in rows]


def test_repository_satisfies_listing_repository_port(database: SqliteDatabase) -> None:
    repository: ListingRepository = SqliteListingRepository(database)

    assert repository is not None


async def test_unremembered_item_is_not_known(repository: SqliteListingRepository) -> None:
    assert await repository.find_known_item_ids([ItemId("m1")]) == frozenset()


async def test_find_known_with_no_ids_returns_empty(repository: SqliteListingRepository) -> None:
    assert await repository.find_known_item_ids([]) == frozenset()


async def test_remembered_items_are_known(repository: SqliteListingRepository) -> None:
    await repository.remember_listings([build_listing("m1"), build_listing("m2")], RULE_ID, SEEN_AT)

    known = await repository.find_known_item_ids([ItemId("m1"), ItemId("m2"), ItemId("m3")])

    assert known == frozenset({ItemId("m1"), ItemId("m2")})


async def test_known_items_survive_restart(database_path: Path) -> None:
    first_run = await open_sqlite_database(database_path)
    await SqliteListingRepository(first_run).remember_listings(
        [build_listing("m1")], RULE_ID, SEEN_AT
    )
    await first_run.close()

    second_run = await open_sqlite_database(database_path)
    known = await SqliteListingRepository(second_run).find_known_item_ids(
        [ItemId("m1"), ItemId("m2")]
    )
    await second_run.close()

    assert known == frozenset({ItemId("m1")})


async def test_notified_state_survives_restart(database_path: Path) -> None:
    first_run = await open_sqlite_database(database_path)
    first_repository = SqliteListingRepository(first_run)
    await first_repository.remember_listings([build_listing("m1")], RULE_ID, SEEN_AT)
    await first_repository.mark_listing_notified(ItemId("m1"), LATER_SEEN_AT)
    await first_run.close()

    rows = await fetch_rows(database_path, "SELECT notified_at FROM listings")

    assert rows == [(LATER_SEEN_AT.isoformat(),)]


async def test_remembering_twice_keeps_first_sighting(
    repository: SqliteListingRepository, database_path: Path
) -> None:
    await repository.remember_listings([build_listing("m1", "first title")], RULE_ID, SEEN_AT)
    await repository.remember_listings(
        [build_listing("m1", "changed title")], RULE_ID, LATER_SEEN_AT
    )

    rows = await fetch_rows(database_path, "SELECT title, first_seen_at FROM listings")

    assert rows == [("first title", SEEN_AT.isoformat())]


async def test_item_under_two_rules_keeps_one_listing_and_both_matches(
    repository: SqliteListingRepository, database_path: Path
) -> None:
    listing = build_listing("m1")
    await repository.remember_listings([listing], RULE_ID, SEEN_AT)
    await repository.remember_listings([listing], OTHER_RULE_ID, SEEN_AT)

    listing_rows = await fetch_rows(database_path, "SELECT item_id FROM listings")
    match_rows = await fetch_rows(
        database_path, "SELECT rule_id FROM listing_rule_matches ORDER BY rule_id"
    )

    assert listing_rows == [("m1",)]
    assert match_rows == [(1,), (2,)]


async def test_listing_fields_are_stored_in_utc_and_integer_yen(
    repository: SqliteListingRepository, database_path: Path
) -> None:
    listing = build_listing("m1")
    listed_in_japan_time = datetime(2026, 9, 29, 12, 0, tzinfo=JAPAN_STANDARD_TIME)
    listing = Listing(
        item_id=listing.item_id,
        kind=listing.kind,
        title=listing.title,
        price=listing.price,
        url=listing.url,
        image_urls=("https://static.mercdn.net/a.jpg", "https://static.mercdn.net/b.jpg"),
        created_at=listed_in_japan_time,
    )
    seen_in_japan_time = datetime(2026, 9, 29, 13, 0, tzinfo=JAPAN_STANDARD_TIME)

    await repository.remember_listings([listing], RULE_ID, seen_in_japan_time)
    rows = await fetch_rows(
        database_path,
        "SELECT price_jpy, typeof(price_jpy), listed_at, first_seen_at, image_urls, kind "
        "FROM listings",
    )

    assert rows == [
        (
            120000,
            "integer",
            "2026-09-29T03:00:00+00:00",
            "2026-09-29T04:00:00+00:00",
            '["https://static.mercdn.net/a.jpg", "https://static.mercdn.net/b.jpg"]',
            "mercari",
        )
    ]


async def test_remember_with_no_listings_writes_nothing(
    repository: SqliteListingRepository, database_path: Path
) -> None:
    await repository.remember_listings([], RULE_ID, SEEN_AT)

    assert await fetch_rows(database_path, "SELECT item_id FROM listings") == []
    assert await fetch_rows(database_path, "SELECT item_id FROM listing_rule_matches") == []


async def test_marking_notified_keeps_first_time(
    repository: SqliteListingRepository, database_path: Path
) -> None:
    await repository.remember_listings([build_listing("m1")], RULE_ID, SEEN_AT)
    await repository.mark_listing_notified(ItemId("m1"), SEEN_AT)
    await repository.mark_listing_notified(ItemId("m1"), LATER_SEEN_AT)

    rows = await fetch_rows(database_path, "SELECT notified_at FROM listings")

    assert rows == [(SEEN_AT.isoformat(),)]


async def test_marking_unknown_item_raises(repository: SqliteListingRepository) -> None:
    with pytest.raises(UnknownListingError):
        await repository.mark_listing_notified(ItemId("missing"), SEEN_AT)


async def test_naive_seen_at_is_rejected_and_nothing_is_written(
    repository: SqliteListingRepository, database_path: Path
) -> None:
    with pytest.raises(InvalidDomainValueError):
        await repository.remember_listings([build_listing("m1")], RULE_ID, NAIVE_MOMENT)

    assert await fetch_rows(database_path, "SELECT item_id FROM listings") == []


async def test_naive_notified_at_is_rejected_and_nothing_is_written(
    repository: SqliteListingRepository, database_path: Path
) -> None:
    await repository.remember_listings([build_listing("m1")], RULE_ID, SEEN_AT)

    with pytest.raises(InvalidDomainValueError):
        await repository.mark_listing_notified(ItemId("m1"), NAIVE_MOMENT)

    assert await fetch_rows(database_path, "SELECT notified_at FROM listings") == [(None,)]


async def test_known_ids_of_deleted_rule_are_kept(
    repository: SqliteListingRepository, database: SqliteDatabase
) -> None:
    async with database.transaction() as connection:
        await connection.execute(
            "INSERT INTO keyword_rules (name, query, is_enabled, created_at, updated_at) "
            "VALUES ('rule', 'query', 1, ?, ?)",
            (SEEN_AT.isoformat(), SEEN_AT.isoformat()),
        )
    await repository.remember_listings([build_listing("m1")], RULE_ID, SEEN_AT)
    async with database.transaction() as connection:
        await connection.execute("DELETE FROM keyword_rules WHERE rule_id = 1")

    assert await repository.find_known_item_ids([ItemId("m1")]) == frozenset({ItemId("m1")})
