from typing import Final

import aiosqlite

INITIAL_SCHEMA: Final[str] = """
CREATE TABLE keyword_rules (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL CHECK (trim(name) <> ''),
    query TEXT NOT NULL CHECK (trim(query) <> ''),
    is_enabled INTEGER NOT NULL CHECK (is_enabled IN (0, 1)),
    baseline_established_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE listings (
    item_id TEXT PRIMARY KEY CHECK (trim(item_id) <> ''),
    kind TEXT NOT NULL CHECK (kind IN ('mercari', 'shops')),
    title TEXT NOT NULL,
    price_jpy INTEGER NOT NULL CHECK (price_jpy >= 0),
    url TEXT NOT NULL,
    image_urls TEXT NOT NULL,
    listed_at TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    notified_at TEXT
);

CREATE TABLE listing_rule_matches (
    item_id TEXT NOT NULL REFERENCES listings (item_id),
    rule_id INTEGER NOT NULL,
    matched_at TEXT NOT NULL,
    PRIMARY KEY (item_id, rule_id)
);

CREATE INDEX listing_rule_matches_by_rule ON listing_rule_matches (rule_id, matched_at);
CREATE INDEX listings_by_first_seen ON listings (first_seen_at);
"""

POLLING_SETTINGS_SCHEMA: Final[str] = """
CREATE TABLE polling_settings (
    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
    polling_gap_seconds INTEGER NOT NULL,
    is_item_detail_fetch_enabled INTEGER NOT NULL CHECK (is_item_detail_fetch_enabled IN (0, 1)),
    max_images_per_alert INTEGER NOT NULL,
    consecutive_failure_alert_threshold INTEGER NOT NULL,
    system_alert_cooldown_seconds INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
"""

MIGRATIONS: Final[tuple[str, ...]] = (INITIAL_SCHEMA, POLLING_SETTINGS_SCHEMA)


class UnsupportedSchemaVersionError(RuntimeError):
    pass


async def read_schema_version(connection: aiosqlite.Connection) -> int:
    async with connection.execute("PRAGMA user_version") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    return int(row[0])


async def apply_migrations(
    connection: aiosqlite.Connection,
    migrations: tuple[str, ...] = MIGRATIONS,
) -> int:
    current_version = await read_schema_version(connection)
    if current_version > len(migrations):
        raise UnsupportedSchemaVersionError(
            f"database schema version {current_version} is newer than "
            f"the {len(migrations)} migrations known to this build"
        )
    for target_version in range(current_version + 1, len(migrations) + 1):
        await _run_migration(connection, migrations[target_version - 1], target_version)
    return len(migrations)


async def _run_migration(
    connection: aiosqlite.Connection, migration: str, target_version: int
) -> None:
    script = f"BEGIN;\n{migration}\nPRAGMA user_version = {target_version};\nCOMMIT;"
    try:
        await connection.executescript(script)
    except BaseException:
        if connection.in_transaction:
            await connection.rollback()
        raise
