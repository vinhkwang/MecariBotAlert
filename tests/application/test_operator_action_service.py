from collections.abc import Sequence

import pytest

from mercari_alert_bot.application.services.operator_action_service import (
    TEST_NOTIFICATION_MESSAGE,
    OperatorActionService,
)
from mercari_alert_bot.domain.errors import (
    InvalidDomainValueError,
    NotificationDeliveryError,
)
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule
from mercari_alert_bot.domain.ports.keyword_rule_document_codec import KeywordRuleDraft
from tests.fakes.in_memory_keyword_rule_repository import InMemoryKeywordRuleRepository
from tests.fakes.recording_notifier import RecordingNotifier

ENCODED_DOCUMENT = "encoded-rules"
MALFORMED_DOCUMENT = "malformed"


class StubKeywordRuleDocumentCodec:
    def __init__(self, drafts: Sequence[KeywordRuleDraft] = ()) -> None:
        self.drafts = drafts
        self.encoded_rules: Sequence[KeywordRule] = ()

    def decode_rule_drafts(self, document_text: str) -> Sequence[KeywordRuleDraft]:
        if document_text == MALFORMED_DOCUMENT:
            raise InvalidDomainValueError("malformed document")
        return self.drafts

    def encode_rules(self, rules: Sequence[KeywordRule]) -> str:
        self.encoded_rules = rules
        return ENCODED_DOCUMENT


def build_draft(name: str, query: str, *, is_enabled: bool = True) -> KeywordRuleDraft:
    return KeywordRuleDraft(name=name, query=query, is_enabled=is_enabled)


def build_service(
    repository: InMemoryKeywordRuleRepository,
    notifier: RecordingNotifier,
    codec: StubKeywordRuleDocumentCodec,
) -> OperatorActionService:
    return OperatorActionService(repository, notifier, codec)


async def test_send_test_notification_sends_one_system_alert() -> None:
    notifier = RecordingNotifier()
    service = build_service(
        InMemoryKeywordRuleRepository(), notifier, StubKeywordRuleDocumentCodec()
    )

    await service.send_test_notification()

    assert notifier.system_alerts == [TEST_NOTIFICATION_MESSAGE]


async def test_send_test_notification_propagates_delivery_failure() -> None:
    notifier = RecordingNotifier()
    notifier.is_failing = True
    service = build_service(
        InMemoryKeywordRuleRepository(), notifier, StubKeywordRuleDocumentCodec()
    )

    with pytest.raises(NotificationDeliveryError):
        await service.send_test_notification()


async def test_import_adds_new_rules_without_baseline() -> None:
    repository = InMemoryKeywordRuleRepository()
    codec = StubKeywordRuleDocumentCodec([build_draft("a", "alpha"), build_draft("b", "beta")])
    service = build_service(repository, RecordingNotifier(), codec)

    result = await service.import_keyword_rules("document")

    assert (result.imported_rule_count, result.skipped_rule_count) == (2, 0)
    assert [rule.has_baseline for rule in await repository.list_rules()] == [False, False]


async def test_import_skips_queries_already_present() -> None:
    repository = InMemoryKeywordRuleRepository()
    await repository.add_rule("existing", "pokemon")
    codec = StubKeywordRuleDocumentCodec([build_draft("again", " pokemon ")])
    service = build_service(repository, RecordingNotifier(), codec)

    result = await service.import_keyword_rules("document")

    assert (result.imported_rule_count, result.skipped_rule_count) == (0, 1)
    assert len(await repository.list_rules()) == 1


async def test_import_skips_duplicate_queries_within_document() -> None:
    repository = InMemoryKeywordRuleRepository()
    codec = StubKeywordRuleDocumentCodec([build_draft("a", "alpha"), build_draft("b", "alpha")])
    service = build_service(repository, RecordingNotifier(), codec)

    result = await service.import_keyword_rules("document")

    assert (result.imported_rule_count, result.skipped_rule_count) == (1, 1)
    assert [rule.name for rule in await repository.list_rules()] == ["a"]


async def test_import_adds_nothing_when_document_is_malformed() -> None:
    repository = InMemoryKeywordRuleRepository()
    await repository.add_rule("existing", "pokemon")
    codec = StubKeywordRuleDocumentCodec([build_draft("a", "alpha")])
    service = build_service(repository, RecordingNotifier(), codec)

    with pytest.raises(InvalidDomainValueError):
        await service.import_keyword_rules(MALFORMED_DOCUMENT)

    assert [rule.name for rule in await repository.list_rules()] == ["existing"]


async def test_export_encodes_every_rule() -> None:
    repository = InMemoryKeywordRuleRepository()
    await repository.add_rule("first", "alpha")
    await repository.add_rule("second", "beta")
    codec = StubKeywordRuleDocumentCodec()
    service = build_service(repository, RecordingNotifier(), codec)

    exported = await service.export_keyword_rules()

    assert exported == ENCODED_DOCUMENT
    assert [rule.name for rule in codec.encoded_rules] == ["first", "second"]
