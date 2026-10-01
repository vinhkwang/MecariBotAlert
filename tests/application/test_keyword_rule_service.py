from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import pytest

from mercari_alert_bot.application.dto.keyword_rule_dto import KeywordRuleDto
from mercari_alert_bot.application.services.keyword_rule_service import KeywordRuleService
from mercari_alert_bot.domain.errors import KeywordRuleNotFoundError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule, KeywordRuleId
from tests.fakes.in_memory_keyword_rule_repository import InMemoryKeywordRuleRepository

SEEDED_AT = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
OMEGA_ID = KeywordRuleId(1)
UNKNOWN_ID = KeywordRuleId(99)


def build_seeded_rule(rule_id: int, name: str, query: str) -> KeywordRule:
    return KeywordRule(
        rule_id=KeywordRuleId(rule_id),
        name=name,
        query=query,
        is_enabled=True,
        baseline_established_at=SEEDED_AT,
    )


def build_service() -> tuple[KeywordRuleService, InMemoryKeywordRuleRepository]:
    repository = InMemoryKeywordRuleRepository(
        [
            build_seeded_rule(1, "omega", "omega 168.005"),
            build_seeded_rule(2, "seiko", "seiko 6139"),
        ]
    )
    return KeywordRuleService(repository), repository


async def test_created_rule_has_no_baseline() -> None:
    service, repository = build_service()

    created = await service.create_rule("rolex", "rolex 1601", is_enabled=True)

    stored = await repository.get_rule(created.rule_id)
    assert created.baseline_established_at is None
    assert not stored.has_baseline
    assert (stored.name, stored.query, stored.is_enabled) == ("rolex", "rolex 1601", True)


async def test_list_rules_returns_dtos_in_id_order() -> None:
    service, _ = build_service()

    rules = await service.list_rules()

    assert rules == [
        KeywordRuleDto(
            rule_id=KeywordRuleId(1),
            name="omega",
            query="omega 168.005",
            is_enabled=True,
            baseline_established_at=SEEDED_AT,
        ),
        KeywordRuleDto(
            rule_id=KeywordRuleId(2),
            name="seiko",
            query="seiko 6139",
            is_enabled=True,
            baseline_established_at=SEEDED_AT,
        ),
    ]


async def test_query_change_clears_baseline() -> None:
    service, repository = build_service()

    updated = await service.update_rule(OMEGA_ID, query="omega 166.010")

    stored = await repository.get_rule(OMEGA_ID)
    assert updated.baseline_established_at is None
    assert stored.query == "omega 166.010"
    assert not stored.has_baseline


async def test_name_change_keeps_baseline() -> None:
    service, repository = build_service()

    updated = await service.update_rule(OMEGA_ID, name="omega seamaster")

    stored = await repository.get_rule(OMEGA_ID)
    assert updated.name == "omega seamaster"
    assert stored.baseline_established_at == SEEDED_AT


async def test_same_query_resubmitted_keeps_baseline() -> None:
    service, repository = build_service()

    await service.update_rule(OMEGA_ID, name="omega", query="omega 168.005")

    assert (await repository.get_rule(OMEGA_ID)).baseline_established_at == SEEDED_AT


async def test_disable_and_enable_keep_baseline() -> None:
    service, repository = build_service()

    disabled = await service.update_rule(OMEGA_ID, is_enabled=False)
    disabled_stored = await repository.get_rule(OMEGA_ID)
    enabled = await service.update_rule(OMEGA_ID, is_enabled=True)

    assert not disabled.is_enabled
    assert disabled_stored.baseline_established_at == SEEDED_AT
    assert enabled.is_enabled
    assert enabled.baseline_established_at == SEEDED_AT


async def test_reset_baseline_clears_baseline_and_keeps_other_fields() -> None:
    service, repository = build_service()

    reset = await service.reset_rule_baseline(OMEGA_ID)

    stored = await repository.get_rule(OMEGA_ID)
    assert reset.baseline_established_at is None
    assert (stored.name, stored.query, stored.is_enabled) == ("omega", "omega 168.005", True)
    assert not stored.has_baseline


async def test_delete_removes_rule() -> None:
    service, _ = build_service()

    await service.delete_rule(OMEGA_ID)

    assert [rule.name for rule in await service.list_rules()] == ["seiko"]


@pytest.mark.parametrize(
    "operation",
    [
        lambda service: service.update_rule(UNKNOWN_ID, name="ghost"),
        lambda service: service.delete_rule(UNKNOWN_ID),
        lambda service: service.reset_rule_baseline(UNKNOWN_ID),
    ],
    ids=["update", "delete", "reset"],
)
async def test_unknown_rule_raises_not_found(
    operation: Callable[[KeywordRuleService], Awaitable[object]],
) -> None:
    service, _ = build_service()

    with pytest.raises(KeywordRuleNotFoundError):
        await operation(service)
