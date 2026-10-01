from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from mercari_alert_bot.domain.models.keyword_rule import KeywordRule


@dataclass(frozen=True, slots=True, kw_only=True)
class KeywordRuleDraft:
    name: str
    query: str
    is_enabled: bool


class KeywordRuleDocumentCodec(Protocol):
    def decode_rule_drafts(self, document_text: str) -> Sequence[KeywordRuleDraft]: ...

    def encode_rules(self, rules: Sequence[KeywordRule]) -> str: ...
