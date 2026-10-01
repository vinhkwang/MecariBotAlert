from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mercari_alert_bot.domain.models.polling_settings import PollingSettings
from mercari_alert_bot.infrastructure.persistence.database import (
    SqliteDatabase,
    open_sqlite_database,
)
from mercari_alert_bot.infrastructure.persistence.sqlite_polling_settings_repository import (
    SqlitePollingSettingsRepository,
)
from tests.shared.fakes import FrozenClock

START = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
POLLING_SETTINGS = PollingSettings(
    polling_gap_seconds=45,
    is_item_detail_fetch_enabled=False,
    max_images_per_alert=2,
    consecutive_failure_alert_threshold=5,
    system_alert_cooldown_seconds=600,
)


@pytest.fixture
async def database(tmp_path: Path) -> AsyncIterator[SqliteDatabase]:
    opened = await open_sqlite_database(tmp_path / "alerts.db")
    yield opened
    await opened.close()


@pytest.fixture
def repository(database: SqliteDatabase) -> SqlitePollingSettingsRepository:
    return SqlitePollingSettingsRepository(database, FrozenClock(START))


async def test_load_returns_none_on_fresh_database(
    repository: SqlitePollingSettingsRepository,
) -> None:
    assert await repository.load_polling_settings() is None


async def test_saved_settings_survive_reopen(tmp_path: Path) -> None:
    database_path = tmp_path / "durable.db"
    first_database = await open_sqlite_database(database_path)
    try:
        await SqlitePollingSettingsRepository(
            first_database, FrozenClock(START)
        ).save_polling_settings(POLLING_SETTINGS)
    finally:
        await first_database.close()

    reopened_database = await open_sqlite_database(database_path)
    try:
        reopened_repository = SqlitePollingSettingsRepository(reopened_database, FrozenClock(START))
        assert await reopened_repository.load_polling_settings() == POLLING_SETTINGS
    finally:
        await reopened_database.close()


async def test_second_save_overwrites_single_row(
    database: SqliteDatabase, repository: SqlitePollingSettingsRepository
) -> None:
    latest_settings = replace(POLLING_SETTINGS, polling_gap_seconds=7)

    await repository.save_polling_settings(POLLING_SETTINGS)
    await repository.save_polling_settings(latest_settings)

    async with database.connection.execute("SELECT COUNT(*) FROM polling_settings") as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 1
    assert await repository.load_polling_settings() == latest_settings
