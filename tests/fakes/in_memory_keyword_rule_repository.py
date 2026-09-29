from collections.abc import Iterable, Sequence

from mercari_alert_bot.domain.errors import KeywordRuleNotFoundError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule, KeywordRuleId


class InMemoryKeywordRuleRepository:
    def __init__(self, rules: Iterable[KeywordRule] = ()) -> None:
        self._rules_by_id: dict[KeywordRuleId, KeywordRule] = {rule.rule_id: rule for rule in rules}
        self._last_rule_id = max(self._rules_by_id, default=KeywordRuleId(0))

    async def list_rules(self) -> Sequence[KeywordRule]:
        return [self._rules_by_id[rule_id] for rule_id in sorted(self._rules_by_id)]

    async def get_rule(self, rule_id: KeywordRuleId) -> KeywordRule:
        self._require_known(rule_id)
        return self._rules_by_id[rule_id]

    async def add_rule(self, name: str, query: str, *, is_enabled: bool = True) -> KeywordRule:
        self._last_rule_id = KeywordRuleId(self._last_rule_id + 1)
        rule = KeywordRule(
            rule_id=self._last_rule_id,
            name=name,
            query=query,
            is_enabled=is_enabled,
            baseline_established_at=None,
        )
        self._rules_by_id[rule.rule_id] = rule
        return rule

    async def save_rule(self, rule: KeywordRule) -> None:
        self._require_known(rule.rule_id)
        self._rules_by_id[rule.rule_id] = rule

    async def delete_rule(self, rule_id: KeywordRuleId) -> None:
        self._require_known(rule_id)
        del self._rules_by_id[rule_id]

    def _require_known(self, rule_id: KeywordRuleId) -> None:
        if rule_id not in self._rules_by_id:
            raise KeywordRuleNotFoundError(f"unknown rule id {rule_id}")
