import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import aiosqlite
import pytest

from mercari_alert_bot.infrastructure.persistence.migrations import (
    MIGRATIONS,
    UnsupportedSchemaVersionError,
    apply_migrations,
    read_schema_version,
)

TIMESTAMP = "2026-09-29T00:00:00+00:00"


@pytest.fixture
async def connection(tmp_path: Path) -> AsyncIterator[aiosqlite.Connection]:
    async with aiosqlite.connect(tmp_path / "test.db") as opened:
        await opened.execute("PRAGMA foreign_keys = ON")
        yield opened


async def list_table_names(connection: aiosqlite.Connection) -> set[str]:
    async with connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'") as cursor:
        return {row[0] for row in await cursor.fetchall()}


async def insert_rule(connection: aiosqlite.Connection, name: str = "rule") -> int:
    cursor = await connection.execute(
        "INSERT INTO keyword_rules (name, query, is_enabled, created_at, updated_at) "
        "VALUES (?, 'query', 1, ?, ?)",
        (name, TIMESTAMP, TIMESTAMP),
    )
    await connection.commit()
    assert cursor.lastrowid is not None
    return cursor.lastrowid


async def insert_listing(
    connection: aiosqlite.Connection,
    item_id: str = "m1",
    kind: str = "mercari",
    price_jpy: int = 1000,
) -> None:
    await connection.execute(
        "INSERT INTO listings "
        "(item_id, kind, title, price_jpy, url, image_urls, listed_at, first_seen_at) "
        "VALUES (?, ?, 'title', ?, 'https://example.test', '[]', ?, ?)",
        (item_id, kind, price_jpy, TIMESTAMP, TIMESTAMP),
    )
    await connection.commit()


async def test_fresh_database_is_migrated_to_latest_version(
    connection: aiosqlite.Connection,
) -> None:
    version = await apply_migrations(connection)

    assert version == len(MIGRATIONS)
    assert await read_schema_version(connection) == len(MIGRATIONS)
    assert {"keyword_rules", "listings", "listing_rule_matches"} <= await list_table_names(
        connection
    )


async def test_applying_migrations_twice_is_a_no_op(connection: aiosqlite.Connection) -> None:
    await apply_migrations(connection)
    await insert_rule(connection)

    version = await apply_migrations(connection)

    assert version == len(MIGRATIONS)
    async with connection.execute("SELECT COUNT(*) FROM keyword_rules") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 1


async def test_only_pending_migrations_run(connection: aiosqlite.Connection) -> None:
    first = "CREATE TABLE first_table (id INTEGER);"
    second = "CREATE TABLE second_table (id INTEGER);"
    await apply_migrations(connection, (first,))

    version = await apply_migrations(connection, (first, second))

    assert version == 2
    assert {"first_table", "second_table"} <= await list_table_names(connection)


async def test_failed_migration_leaves_version_and_schema_unchanged(
    connection: aiosqlite.Connection,
) -> None:
    first = "CREATE TABLE first_table (id INTEGER);"
    broken = "CREATE TABLE half_applied (id INTEGER); CREATE TABLE half_applied (id INTEGER);"
    await apply_migrations(connection, (first,))

    with pytest.raises(sqlite3.OperationalError):
        await apply_migrations(connection, (first, broken))

    assert await read_schema_version(connection) == 1
    assert "half_applied" not in await list_table_names(connection)


async def test_newer_schema_version_is_rejected(connection: aiosqlite.Connection) -> None:
    await connection.execute(f"PRAGMA user_version = {len(MIGRATIONS) + 1}")

    with pytest.raises(UnsupportedSchemaVersionError):
        await apply_migrations(connection)


async def test_rule_ids_are_never_reused_after_delete(connection: aiosqlite.Connection) -> None:
    await apply_migrations(connection)
    first_rule_id = await insert_rule(connection, "first")
    await connection.execute("DELETE FROM keyword_rules WHERE rule_id = ?", (first_rule_id,))
    await connection.commit()

    second_rule_id = await insert_rule(connection, "second")

    assert second_rule_id > first_rule_id


async def test_deleting_rule_keeps_its_listing_matches(connection: aiosqlite.Connection) -> None:
    await apply_migrations(connection)
    rule_id = await insert_rule(connection)
    await insert_listing(connection)
    await connection.execute(
        "INSERT INTO listing_rule_matches (item_id, rule_id, matched_at) VALUES ('m1', ?, ?)",
        (rule_id, TIMESTAMP),
    )
    await connection.commit()

    await connection.execute("DELETE FROM keyword_rules WHERE rule_id = ?", (rule_id,))
    await connection.commit()

    async with connection.execute("SELECT COUNT(*) FROM listing_rule_matches") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 1


async def test_match_requires_existing_listing(connection: aiosqlite.Connection) -> None:
    await apply_migrations(connection)
    rule_id = await insert_rule(connection)

    with pytest.raises(sqlite3.IntegrityError):
        await connection.execute(
            "INSERT INTO listing_rule_matches (item_id, rule_id, matched_at) "
            "VALUES ('unknown', ?, ?)",
            (rule_id, TIMESTAMP),
        )


async def test_duplicate_item_id_is_rejected(connection: aiosqlite.Connection) -> None:
    await apply_migrations(connection)
    await insert_listing(connection, "m1")

    with pytest.raises(sqlite3.IntegrityError):
        await insert_listing(connection, "m1")


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO keyword_rules (name, query, is_enabled, created_at, updated_at) "
        "VALUES ('  ', 'query', 1, 't', 't')",
        "INSERT INTO keyword_rules (name, query, is_enabled, created_at, updated_at) "
        "VALUES ('name', '  ', 1, 't', 't')",
        "INSERT INTO keyword_rules (name, query, is_enabled, created_at, updated_at) "
        "VALUES ('name', 'query', 2, 't', 't')",
        "INSERT INTO listings "
        "(item_id, kind, title, price_jpy, url, image_urls, listed_at, first_seen_at) "
        "VALUES ('m1', 'mercari', 'title', -1, 'u', '[]', 't', 't')",
        "INSERT INTO listings "
        "(item_id, kind, title, price_jpy, url, image_urls, listed_at, first_seen_at) "
        "VALUES ('m1', 'unknown', 'title', 1, 'u', '[]', 't', 't')",
    ],
    ids=["blank-name", "blank-query", "bad-is-enabled", "negative-price", "unknown-kind"],
)
async def test_invalid_values_are_rejected_by_constraints(
    connection: aiosqlite.Connection, statement: str
) -> None:
    await apply_migrations(connection)

    with pytest.raises(sqlite3.IntegrityError):
        await connection.execute(statement)
