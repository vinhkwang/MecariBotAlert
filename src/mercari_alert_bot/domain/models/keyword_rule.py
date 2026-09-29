from dataclasses import dataclass
from datetime import datetime
from typing import NewType

from mercari_alert_bot.domain.errors import InvalidDomainValueError

KeywordRuleId = NewType("KeywordRuleId", int)


@dataclass(frozen=True, slots=True, kw_only=True)
class KeywordRule:
    rule_id: KeywordRuleId
    name: str
    query: str
    is_enabled: bool
    baseline_established_at: datetime | None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvalidDomainValueError("name must not be blank")
        if not self.query.strip():
            raise InvalidDomainValueError("query must not be blank")
        if self.baseline_established_at is not None and (
            self.baseline_established_at.utcoffset() is None
        ):
            raise InvalidDomainValueError("baseline_established_at must be timezone-aware")

    @property
    def has_baseline(self) -> bool:
        return self.baseline_established_at is not None
