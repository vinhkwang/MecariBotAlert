from dataclasses import dataclass
from datetime import datetime
from typing import Self

from mercari_alert_bot.domain.models.keyword_rule import KeywordRule, KeywordRuleId


@dataclass(frozen=True, slots=True, kw_only=True)
class KeywordRuleDto:
    rule_id: KeywordRuleId
    name: str
    query: str
    is_enabled: bool
    baseline_established_at: datetime | None

    @classmethod
    def from_rule(cls, rule: KeywordRule) -> Self:
        return cls(
            rule_id=rule.rule_id,
            name=rule.name,
            query=rule.query,
            is_enabled=rule.is_enabled,
            baseline_established_at=rule.baseline_established_at,
        )
