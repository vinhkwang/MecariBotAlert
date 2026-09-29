import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from mercari_alert_bot.infrastructure.persistence.migrations import apply_migrations

BUSY_TIMEOUT_MILLISECONDS = 5000


class SqliteDatabase:
    def __init__(self, connection: aiosqlite.Connection) -> None:
        self._connection = connection
        self._write_lock = asyncio.Lock()

    @property
    def connection(self) -> aiosqlite.Connection:
        return self._connection

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        async with self._write_lock:
            try:
                yield self._connection
            except BaseException:
                await self._connection.rollback()
                raise
            await self._connection.commit()

    async def close(self) -> None:
        await self._connection.close()


async def open_sqlite_database(database_path: Path) -> SqliteDatabase:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = await aiosqlite.connect(database_path)
    try:
        await connection.execute("PRAGMA journal_mode = WAL")
        await connection.execute("PRAGMA foreign_keys = ON")
        await connection.execute("PRAGMA synchronous = NORMAL")
        await connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MILLISECONDS}")
        await apply_migrations(connection)
    except BaseException:
        await connection.close()
        raise
    return SqliteDatabase(connection)
