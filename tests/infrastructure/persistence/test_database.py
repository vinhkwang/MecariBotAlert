import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest

from mercari_alert_bot.infrastructure.persistence.database import (
    SqliteDatabase,
    open_sqlite_database,
)
from mercari_alert_bot.infrastructure.persistence.migrations import (
    MIGRATIONS,
    read_schema_version,
)

TIMESTAMP = "2026-09-29T00:00:00+00:00"
INSERT_RULE = (
    "INSERT INTO keyword_rules (name, query, is_enabled, created_at, updated_at) "
    "VALUES ('rule', 'query', 1, ?, ?)"
)


@pytest.fixture
async def database(tmp_path: Path) -> AsyncIterator[SqliteDatabase]:
    opened = await open_sqlite_database(tmp_path / "alerts.db")
    yield opened
    await opened.close()


async def count_rules(database_path: Path) -> int:
    async with (
        aiosqlite.connect(database_path) as independent_connection,
        independent_connection.execute("SELECT COUNT(*) FROM keyword_rules") as cursor,
    ):
        row = await cursor.fetchone()
    assert row is not None
    return int(row[0])


async def read_pragma(connection: aiosqlite.Connection, name: str) -> object:
    async with connection.execute(f"PRAGMA {name}") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    return row[0]


async def test_open_creates_missing_parent_directory(tmp_path: Path) -> None:
    database_path = tmp_path / "nested" / "deeper" / "alerts.db"

    database = await open_sqlite_database(database_path)
    await database.close()

    assert database_path.exists()


async def test_open_enables_wal_journal_mode(database: SqliteDatabase) -> None:
    assert await read_pragma(database.connection, "journal_mode") == "wal"


async def test_open_enables_foreign_keys(database: SqliteDatabase) -> None:
    assert await read_pragma(database.connection, "foreign_keys") == 1


async def test_data_survives_close_and_reopen(tmp_path: Path) -> None:
    database_path = tmp_path / "alerts.db"
    database = await open_sqlite_database(database_path)
    async with database.transaction() as connection:
        await connection.execute(INSERT_RULE, (TIMESTAMP, TIMESTAMP))
    await database.close()

    reopened = await open_sqlite_database(database_path)

    assert await count_rules(database_path) == 1
    assert await read_schema_version(reopened.connection) == len(MIGRATIONS)
    await reopened.close()


async def test_transaction_commits_on_success(database: SqliteDatabase, tmp_path: Path) -> None:
    database_path = tmp_path / "alerts.db"

    async with database.transaction() as connection:
        await connection.execute(INSERT_RULE, (TIMESTAMP, TIMESTAMP))

    assert await count_rules(database_path) == 1


async def test_transaction_rolls_back_on_error(database: SqliteDatabase, tmp_path: Path) -> None:
    database_path = tmp_path / "alerts.db"

    with pytest.raises(RuntimeError):
        async with database.transaction() as connection:
            await connection.execute(INSERT_RULE, (TIMESTAMP, TIMESTAMP))
            raise RuntimeError("boom")

    assert await count_rules(database_path) == 0


async def test_transactions_are_serialized(database: SqliteDatabase) -> None:
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    events: list[str] = []

    async def hold_transaction() -> None:
        async with database.transaction():
            events.append("first-entered")
            first_entered.set()
            await release_first.wait()
            events.append("first-exiting")

    async def wait_for_transaction() -> None:
        await first_entered.wait()
        async with database.transaction():
            events.append("second-entered")

    first = asyncio.create_task(hold_transaction())
    second = asyncio.create_task(wait_for_transaction())
    await first_entered.wait()
    await asyncio.sleep(0.05)
    assert events == ["first-entered"]

    release_first.set()
    await asyncio.gather(first, second)

    assert events == ["first-entered", "first-exiting", "second-entered"]
