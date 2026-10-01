from dataclasses import replace

from mercari_alert_bot.application.dto.keyword_rule_dto import KeywordRuleDto
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule, KeywordRuleId
from mercari_alert_bot.domain.ports.keyword_rule_repository import KeywordRuleRepository


class KeywordRuleService:
    def __init__(self, keyword_rule_repository: KeywordRuleRepository) -> None:
        self._keyword_rule_repository = keyword_rule_repository

    async def list_rules(self) -> list[KeywordRuleDto]:
        rules = await self._keyword_rule_repository.list_rules()
        return [KeywordRuleDto.from_rule(rule) for rule in rules]

    async def create_rule(self, name: str, query: str, *, is_enabled: bool) -> KeywordRuleDto:
        rule = await self._keyword_rule_repository.add_rule(name, query, is_enabled=is_enabled)
        return KeywordRuleDto.from_rule(rule)

    async def update_rule(
        self,
        rule_id: KeywordRuleId,
        *,
        name: str | None = None,
        query: str | None = None,
        is_enabled: bool | None = None,
    ) -> KeywordRuleDto:
        stored_rule = await self._keyword_rule_repository.get_rule(rule_id)
        updated_rule = replace(
            stored_rule,
            name=stored_rule.name if name is None else name,
            query=stored_rule.query if query is None else query,
            is_enabled=stored_rule.is_enabled if is_enabled is None else is_enabled,
        )
        if updated_rule.query != stored_rule.query:
            updated_rule = replace(updated_rule, baseline_established_at=None)
        return await self._save_rule(updated_rule)

    async def delete_rule(self, rule_id: KeywordRuleId) -> None:
        await self._keyword_rule_repository.delete_rule(rule_id)

    async def reset_rule_baseline(self, rule_id: KeywordRuleId) -> KeywordRuleDto:
        stored_rule = await self._keyword_rule_repository.get_rule(rule_id)
        return await self._save_rule(replace(stored_rule, baseline_established_at=None))

    async def _save_rule(self, rule: KeywordRule) -> KeywordRuleDto:
        await self._keyword_rule_repository.save_rule(rule)
        return KeywordRuleDto.from_rule(rule)
