from dataclasses import replace
from datetime import UTC, datetime

import pytest

from mercari_alert_bot.domain.errors import InvalidDomainValueError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule, KeywordRuleId


def build_rule() -> KeywordRule:
    return KeywordRule(
        rule_id=KeywordRuleId(1),
        name="Omega Constellation",
        query="OMEGA Constellation",
        is_enabled=True,
        baseline_established_at=None,
    )


def test_valid_rule_keeps_its_fields() -> None:
    rule = build_rule()

    assert rule.rule_id == 1
    assert rule.name == "Omega Constellation"
    assert rule.query == "OMEGA Constellation"
    assert rule.is_enabled is True
    assert rule.baseline_established_at is None


def test_rule_without_baseline_has_no_baseline() -> None:
    assert build_rule().has_baseline is False


def test_rule_with_baseline_has_baseline() -> None:
    rule = replace(build_rule(), baseline_established_at=datetime(2026, 9, 29, tzinfo=UTC))

    assert rule.has_baseline is True


def test_blank_name_is_rejected() -> None:
    with pytest.raises(InvalidDomainValueError):
        replace(build_rule(), name="  ")


def test_blank_query_is_rejected() -> None:
    with pytest.raises(InvalidDomainValueError):
        replace(build_rule(), query="")


def test_naive_baseline_is_rejected() -> None:
    with pytest.raises(InvalidDomainValueError):
        replace(build_rule(), baseline_established_at=datetime(2026, 9, 29))
