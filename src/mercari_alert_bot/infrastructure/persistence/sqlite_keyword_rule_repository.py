import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime

import aiosqlite

from mercari_alert_bot.domain.errors import InvalidDomainValueError, KeywordRuleNotFoundError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule, KeywordRuleId
from mercari_alert_bot.infrastructure.persistence.database import SqliteDatabase
from mercari_alert_bot.shared.clock import Clock

SELECT_RULES = "SELECT rule_id, name, query, is_enabled, baseline_established_at FROM keyword_rules"


class SqliteKeywordRuleRepository:
    def __init__(self, database: SqliteDatabase, clock: Clock) -> None:
        self._database = database
        self._clock = clock

    async def list_rules(self) -> Sequence[KeywordRule]:
        async with self._database.connection.execute(f"{SELECT_RULES} ORDER BY rule_id") as cursor:
            rows = await cursor.fetchall()
        return [_map_row_to_rule(row) for row in rows]

    async def get_rule(self, rule_id: KeywordRuleId) -> KeywordRule:
        async with self._database.connection.execute(
            f"{SELECT_RULES} WHERE rule_id = ?", (rule_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise _unknown_rule(rule_id)
        return _map_row_to_rule(row)

    async def add_rule(self, name: str, query: str, *, is_enabled: bool = True) -> KeywordRule:
        timestamp = self._clock.now().isoformat()
        async with self._database.transaction() as connection:
            try:
                cursor = await connection.execute(
                    "INSERT INTO keyword_rules "
                    "(name, query, is_enabled, baseline_established_at, created_at, updated_at) "
                    "VALUES (?, ?, ?, NULL, ?, ?)",
                    (name, query, int(is_enabled), timestamp, timestamp),
                )
            except sqlite3.IntegrityError as error:
                raise InvalidDomainValueError("name and query must not be blank") from error
            assert cursor.lastrowid is not None
            return KeywordRule(
                rule_id=KeywordRuleId(cursor.lastrowid),
                name=name,
                query=query,
                is_enabled=is_enabled,
                baseline_established_at=None,
            )

    async def save_rule(self, rule: KeywordRule) -> None:
        baseline = rule.baseline_established_at
        async with self._database.transaction() as connection:
            try:
                cursor = await connection.execute(
                    "UPDATE keyword_rules SET name = ?, query = ?, is_enabled = ?, "
                    "baseline_established_at = ?, updated_at = ? WHERE rule_id = ?",
                    (
                        rule.name,
                        rule.query,
                        int(rule.is_enabled),
                        None if baseline is None else baseline.astimezone(UTC).isoformat(),
                        self._clock.now().isoformat(),
                        rule.rule_id,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise InvalidDomainValueError("name and query must not be blank") from error
            if cursor.rowcount == 0:
                raise _unknown_rule(rule.rule_id)

    async def delete_rule(self, rule_id: KeywordRuleId) -> None:
        async with self._database.transaction() as connection:
            cursor = await connection.execute(
                "DELETE FROM keyword_rules WHERE rule_id = ?", (rule_id,)
            )
            if cursor.rowcount == 0:
                raise _unknown_rule(rule_id)


def _unknown_rule(rule_id: KeywordRuleId) -> KeywordRuleNotFoundError:
    return KeywordRuleNotFoundError(f"unknown rule id {rule_id}")


def _map_row_to_rule(row: aiosqlite.Row | tuple[object, ...]) -> KeywordRule:
    rule_id, name, query, is_enabled, baseline = row
    return KeywordRule(
        rule_id=KeywordRuleId(int(str(rule_id))),
        name=str(name),
        query=str(query),
        is_enabled=bool(is_enabled),
        baseline_established_at=None if baseline is None else datetime.fromisoformat(str(baseline)),
    )
