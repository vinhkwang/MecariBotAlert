from dataclasses import dataclass, replace
from typing import Final

import structlog

from mercari_alert_bot.domain.models.keyword_rule import KeywordRuleId
from mercari_alert_bot.domain.ports.keyword_rule_document_codec import KeywordRuleDocumentCodec
from mercari_alert_bot.domain.ports.keyword_rule_repository import KeywordRuleRepository
from mercari_alert_bot.domain.ports.notifier import Notifier

TEST_NOTIFICATION_MESSAGE: Final = "Test notification from Mercari Alert Bot. Delivery works."

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True, kw_only=True)
class KeywordRuleImportResult:
    imported_rule_count: int
    skipped_rule_count: int


class OperatorActionService:
    def __init__(
        self,
        keyword_rule_repository: KeywordRuleRepository,
        notifier: Notifier,
        keyword_rule_document_codec: KeywordRuleDocumentCodec,
    ) -> None:
        self._keyword_rule_repository = keyword_rule_repository
        self._notifier = notifier
        self._keyword_rule_document_codec = keyword_rule_document_codec

    async def send_test_notification(self) -> None:
        await self._notifier.send_system_alert(TEST_NOTIFICATION_MESSAGE)
        logger.info("test_notification_sent")

    async def import_keyword_rules(self, document_text: str) -> KeywordRuleImportResult:
        drafts = self._keyword_rule_document_codec.decode_rule_drafts(document_text)
        known_queries = {
            rule.query.strip() for rule in await self._keyword_rule_repository.list_rules()
        }
        imported_rule_count = 0
        for draft in drafts:
            normalized_query = draft.query.strip()
            if normalized_query in known_queries:
                continue
            known_queries.add(normalized_query)
            await self._keyword_rule_repository.add_rule(
                draft.name, draft.query, is_enabled=draft.is_enabled
            )
            imported_rule_count += 1
        result = KeywordRuleImportResult(
            imported_rule_count=imported_rule_count,
            skipped_rule_count=len(drafts) - imported_rule_count,
        )
        logger.info(
            "keyword_rules_imported",
            imported_rule_count=result.imported_rule_count,
            skipped_rule_count=result.skipped_rule_count,
        )
        return result

    async def export_keyword_rules(self) -> str:
        rules = await self._keyword_rule_repository.list_rules()
        return self._keyword_rule_document_codec.encode_rules(rules)

    async def reset_rule_baseline(self, rule_id: KeywordRuleId) -> None:
        rule = await self._keyword_rule_repository.get_rule(rule_id)
        await self._keyword_rule_repository.save_rule(replace(rule, baseline_established_at=None))
        logger.info("rule_baseline_reset", rule_name=rule.name)
