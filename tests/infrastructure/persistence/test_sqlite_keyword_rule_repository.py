from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from mercari_alert_bot.domain.errors import InvalidDomainValueError, KeywordRuleNotFoundError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRuleId
from mercari_alert_bot.domain.ports.keyword_rule_repository import KeywordRuleRepository
from mercari_alert_bot.infrastructure.persistence.database import (
    SqliteDatabase,
    open_sqlite_database,
)
from mercari_alert_bot.infrastructure.persistence.sqlite_keyword_rule_repository import (
    SqliteKeywordRuleRepository,
)
from tests.shared.fakes import FrozenClock

START = datetime(2026, 9, 29, 0, 0, tzinfo=UTC)
UNKNOWN_RULE_ID = KeywordRuleId(999)


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(START)


@pytest.fixture
async def database(tmp_path: Path) -> AsyncIterator[SqliteDatabase]:
    opened = await open_sqlite_database(tmp_path / "alerts.db")
    yield opened
    await opened.close()


@pytest.fixture
def repository(database: SqliteDatabase, clock: FrozenClock) -> SqliteKeywordRuleRepository:
    return SqliteKeywordRuleRepository(database, clock)


async def read_timestamps(database: SqliteDatabase, rule_id: KeywordRuleId) -> tuple[str, str]:
    async with database.connection.execute(
        "SELECT created_at, updated_at FROM keyword_rules WHERE rule_id = ?", (rule_id,)
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    return str(row[0]), str(row[1])


async def test_new_database_lists_no_rules(repository: SqliteKeywordRuleRepository) -> None:
    assert await repository.list_rules() == []


async def test_add_rule_returns_rule_without_baseline(
    repository: SqliteKeywordRuleRepository,
) -> None:
    rule = await repository.add_rule("Omega", "OMEGA シーマスター")

    assert rule.rule_id >= 1
    assert rule.name == "Omega"
    assert rule.query == "OMEGA シーマスター"
    assert not rule.has_baseline


async def test_add_rule_defaults_to_enabled(repository: SqliteKeywordRuleRepository) -> None:
    rule = await repository.add_rule("Omega", "OMEGA")

    assert rule.is_enabled
    assert (await repository.get_rule(rule.rule_id)).is_enabled


async def test_add_rule_rejects_blank_name_and_stores_nothing(
    repository: SqliteKeywordRuleRepository,
) -> None:
    with pytest.raises(InvalidDomainValueError):
        await repository.add_rule("  ", "OMEGA")

    assert await repository.list_rules() == []


async def test_add_rule_rejects_blank_query_and_stores_nothing(
    repository: SqliteKeywordRuleRepository,
) -> None:
    with pytest.raises(InvalidDomainValueError):
        await repository.add_rule("Omega", "\n\t")

    assert await repository.list_rules() == []


async def test_list_rules_includes_disabled_rules_in_id_order(
    repository: SqliteKeywordRuleRepository,
) -> None:
    first = await repository.add_rule("first", "one")
    second = await repository.add_rule("second", "two", is_enabled=False)
    third = await repository.add_rule("third", "three")

    assert await repository.list_rules() == [first, second, third]


async def test_get_rule_returns_stored_rule(repository: SqliteKeywordRuleRepository) -> None:
    added = await repository.add_rule("Omega", "OMEGA", is_enabled=False)

    assert await repository.get_rule(added.rule_id) == added


async def test_get_unknown_rule_raises_not_found(repository: SqliteKeywordRuleRepository) -> None:
    with pytest.raises(KeywordRuleNotFoundError):
        await repository.get_rule(UNKNOWN_RULE_ID)


async def test_save_rule_persists_every_field(repository: SqliteKeywordRuleRepository) -> None:
    added = await repository.add_rule("Omega", "OMEGA")
    edited = replace(
        added,
        name="Omega renamed",
        query="OMEGA コンステレーション",
        is_enabled=False,
        baseline_established_at=START,
    )

    await repository.save_rule(edited)

    assert await repository.get_rule(added.rule_id) == edited


async def test_save_rule_round_trips_baseline_as_utc_aware_datetime(
    repository: SqliteKeywordRuleRepository,
) -> None:
    added = await repository.add_rule("Omega", "OMEGA")
    ict = timezone(timedelta(hours=7))
    baseline = datetime(2026, 9, 29, 7, 30, tzinfo=ict)

    await repository.save_rule(replace(added, baseline_established_at=baseline))

    stored = (await repository.get_rule(added.rule_id)).baseline_established_at
    assert stored == baseline
    assert stored is not None
    assert stored.utcoffset() == timedelta(0)


async def test_save_rule_can_clear_baseline(repository: SqliteKeywordRuleRepository) -> None:
    added = await repository.add_rule("Omega", "OMEGA")
    await repository.save_rule(replace(added, baseline_established_at=START))

    await repository.save_rule(replace(added, baseline_established_at=None))

    assert not (await repository.get_rule(added.rule_id)).has_baseline


async def test_save_rule_sets_updated_at_from_clock(
    repository: SqliteKeywordRuleRepository, database: SqliteDatabase, clock: FrozenClock
) -> None:
    added = await repository.add_rule("Omega", "OMEGA")
    clock.advance(timedelta(hours=1))

    await repository.save_rule(replace(added, name="renamed"))

    created_at, updated_at = await read_timestamps(database, added.rule_id)
    assert created_at == START.isoformat()
    assert updated_at == (START + timedelta(hours=1)).isoformat()


async def test_save_unknown_rule_raises_not_found(
    repository: SqliteKeywordRuleRepository,
) -> None:
    added = await repository.add_rule("Omega", "OMEGA")

    with pytest.raises(KeywordRuleNotFoundError):
        await repository.save_rule(replace(added, rule_id=UNKNOWN_RULE_ID))


async def test_delete_rule_removes_it(repository: SqliteKeywordRuleRepository) -> None:
    added = await repository.add_rule("Omega", "OMEGA")

    await repository.delete_rule(added.rule_id)

    assert await repository.list_rules() == []


async def test_delete_unknown_rule_raises_not_found(
    repository: SqliteKeywordRuleRepository,
) -> None:
    with pytest.raises(KeywordRuleNotFoundError):
        await repository.delete_rule(UNKNOWN_RULE_ID)


async def test_delete_rule_keeps_listing_history(
    repository: SqliteKeywordRuleRepository, database: SqliteDatabase
) -> None:
    added = await repository.add_rule("Omega", "OMEGA")
    timestamp = START.isoformat()
    async with database.transaction() as connection:
        await connection.execute(
            "INSERT INTO listings (item_id, kind, title, price_jpy, url, image_urls, "
            "listed_at, first_seen_at) VALUES ('m1', 'mercari', 't', 1000, 'u', '[]', ?, ?)",
            (timestamp, timestamp),
        )
        await connection.execute(
            "INSERT INTO listing_rule_matches (item_id, rule_id, matched_at) VALUES ('m1', ?, ?)",
            (added.rule_id, timestamp),
        )

    await repository.delete_rule(added.rule_id)

    async with database.connection.execute(
        "SELECT COUNT(*) FROM listing_rule_matches WHERE rule_id = ?", (added.rule_id,)
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == 1


async def test_deleted_rule_id_is_never_reused(repository: SqliteKeywordRuleRepository) -> None:
    first = await repository.add_rule("first", "one")
    await repository.delete_rule(first.rule_id)

    second = await repository.add_rule("second", "two")

    assert second.rule_id > first.rule_id


async def test_rules_survive_reopening_database(tmp_path: Path, clock: FrozenClock) -> None:
    database_path = tmp_path / "durable.db"
    first_session = await open_sqlite_database(database_path)
    added = await SqliteKeywordRuleRepository(first_session, clock).add_rule("Omega", "OMEGA")
    with_baseline = replace(added, baseline_established_at=START)
    await SqliteKeywordRuleRepository(first_session, clock).save_rule(with_baseline)
    await first_session.close()

    second_session = await open_sqlite_database(database_path)
    try:
        reloaded = await SqliteKeywordRuleRepository(second_session, clock).list_rules()
    finally:
        await second_session.close()

    assert reloaded == [with_baseline]


def test_satisfies_keyword_rule_repository_port(
    repository: SqliteKeywordRuleRepository,
) -> None:
    port: KeywordRuleRepository = repository
    assert port is repository
