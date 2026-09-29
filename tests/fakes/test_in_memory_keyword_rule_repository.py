from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from mercari_alert_bot.domain.errors import KeywordRuleNotFoundError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule, KeywordRuleId
from mercari_alert_bot.domain.ports.keyword_rule_repository import KeywordRuleRepository
from tests.fakes.in_memory_keyword_rule_repository import InMemoryKeywordRuleRepository


def build_rule(rule_id: int, *, is_enabled: bool = True) -> KeywordRule:
    return KeywordRule(
        rule_id=KeywordRuleId(rule_id),
        name=f"rule {rule_id}",
        query=f"query {rule_id}",
        is_enabled=is_enabled,
        baseline_established_at=None,
    )


async def test_added_rule_has_no_baseline() -> None:
    repository: KeywordRuleRepository = InMemoryKeywordRuleRepository()

    rule = await repository.add_rule("Omega", "OMEGA")

    assert rule.baseline_established_at is None
    assert rule.is_enabled


async def test_added_rules_get_increasing_ids_after_seeded_rules() -> None:
    repository = InMemoryKeywordRuleRepository([build_rule(7)])

    first = await repository.add_rule("Omega", "OMEGA")
    second = await repository.add_rule("Seiko", "SEIKO", is_enabled=False)

    assert (first.rule_id, second.rule_id) == (8, 9)
    assert not second.is_enabled


async def test_list_rules_includes_disabled_rules_in_id_order() -> None:
    repository = InMemoryKeywordRuleRepository(
        [build_rule(3), build_rule(1, is_enabled=False), build_rule(2)]
    )

    rules = await repository.list_rules()

    assert [rule.rule_id for rule in rules] == [1, 2, 3]


async def test_saved_rule_replaces_stored_rule() -> None:
    repository = InMemoryKeywordRuleRepository([build_rule(1)])
    seeded = replace(build_rule(1), baseline_established_at=datetime(2026, 9, 29, tzinfo=UTC))

    await repository.save_rule(seeded)

    assert await repository.get_rule(KeywordRuleId(1)) == seeded


@pytest.mark.parametrize(
    "operation",
    [
        lambda repository: repository.get_rule(KeywordRuleId(99)),
        lambda repository: repository.save_rule(build_rule(99)),
        lambda repository: repository.delete_rule(KeywordRuleId(99)),
    ],
    ids=["get_rule", "save_rule", "delete_rule"],
)
async def test_unknown_rule_id_raises_not_found(
    operation: Callable[[KeywordRuleRepository], Awaitable[object]],
) -> None:
    repository = InMemoryKeywordRuleRepository()

    with pytest.raises(KeywordRuleNotFoundError):
        await operation(repository)


async def test_deleted_rule_is_gone() -> None:
    repository = InMemoryKeywordRuleRepository([build_rule(1)])

    await repository.delete_rule(KeywordRuleId(1))

    with pytest.raises(KeywordRuleNotFoundError):
        await repository.get_rule(KeywordRuleId(1))
