from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, StringConstraints

from mercari_alert_bot.application.dto.keyword_rule_dto import KeywordRuleDto

RuleText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class KeywordRuleCreateRequest(BaseModel):
    name: RuleText
    query: RuleText
    is_enabled: bool = True


class KeywordRuleUpdateRequest(BaseModel):
    name: RuleText | None = None
    query: RuleText | None = None
    is_enabled: bool | None = None


class KeywordRuleResponse(BaseModel):
    id: int
    name: str
    query: str
    is_enabled: bool
    has_baseline: bool
    baseline_established_at: datetime | None

    @classmethod
    def from_dto(cls, rule: KeywordRuleDto) -> Self:
        return cls(
            id=rule.rule_id,
            name=rule.name,
            query=rule.query,
            is_enabled=rule.is_enabled,
            has_baseline=rule.baseline_established_at is not None,
            baseline_established_at=rule.baseline_established_at,
        )
