from collections.abc import Sequence
from pathlib import Path

import yaml

from mercari_alert_bot.domain.errors import InvalidDomainValueError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule
from mercari_alert_bot.domain.ports.keyword_rule_document_codec import KeywordRuleDraft
from mercari_alert_bot.domain.ports.keyword_rule_repository import KeywordRuleRepository


class KeywordSeedFormatError(InvalidDomainValueError):
    pass


class YamlKeywordRuleDocumentCodec:
    def decode_rule_drafts(self, document_text: str) -> Sequence[KeywordRuleDraft]:
        return _parse_seed_entries(document_text)

    def encode_rules(self, rules: Sequence[KeywordRule]) -> str:
        document = {
            "keywords": [
                {"name": rule.name, "query": rule.query, "enabled": rule.is_enabled}
                for rule in rules
            ]
        }
        return yaml.safe_dump(document, allow_unicode=True, sort_keys=False)


async def import_seed_rules_when_empty(repository: KeywordRuleRepository, seed_path: Path) -> int:
    if await repository.list_rules():
        return 0
    seed_text = _read_seed_text(seed_path)
    if seed_text is None:
        return 0
    entries = _parse_seed_entries(seed_text)
    for entry in entries:
        await repository.add_rule(entry.name, entry.query, is_enabled=entry.is_enabled)
    return len(entries)


def _read_seed_text(seed_path: Path) -> str | None:
    if not seed_path.exists():
        return None
    return seed_path.read_text(encoding="utf-8")


def _parse_seed_entries(seed_text: str) -> list[KeywordRuleDraft]:
    try:
        document = yaml.safe_load(seed_text)
    except yaml.YAMLError as error:
        raise KeywordSeedFormatError("seed file is not valid YAML") from error
    if document is None:
        return []
    if not isinstance(document, dict):
        raise KeywordSeedFormatError("seed file must be a mapping")
    raw_entries = document.get("keywords")
    if raw_entries is None:
        return []
    if not isinstance(raw_entries, list):
        raise KeywordSeedFormatError("keywords must be a list")
    return [_parse_seed_entry(index, raw) for index, raw in enumerate(raw_entries)]


def _parse_seed_entry(index: int, raw_entry: object) -> KeywordRuleDraft:
    if not isinstance(raw_entry, dict):
        raise KeywordSeedFormatError(f"keyword entry {index} must be a mapping")
    name = raw_entry.get("name")
    query = raw_entry.get("query")
    is_enabled = raw_entry.get("enabled", True)
    if not isinstance(name, str) or not name.strip():
        raise KeywordSeedFormatError(f"keyword entry {index} needs a non-blank name")
    if not isinstance(query, str) or not query.strip():
        raise KeywordSeedFormatError(f"keyword entry {index} needs a non-blank query")
    if not isinstance(is_enabled, bool):
        raise KeywordSeedFormatError(f"keyword entry {index} enabled must be true or false")
    return KeywordRuleDraft(name=name, query=query, is_enabled=is_enabled)


async def export_keyword_rules_yaml(repository: KeywordRuleRepository) -> str:
    return YamlKeywordRuleDocumentCodec().encode_rules(await repository.list_rules())
