from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mercari_alert_bot.application.services.operator_action_service import (
    TEST_NOTIFICATION_MESSAGE,
    OperatorActionService,
)
from mercari_alert_bot.domain.errors import InvalidDomainValueError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule
from mercari_alert_bot.domain.ports.keyword_rule_document_codec import KeywordRuleDraft
from mercari_alert_bot.web.app import create_web_app
from mercari_alert_bot.web.routers.actions import get_operator_action_service
from mercari_alert_bot.web.schemas.actions import KEYWORD_DOCUMENT_MAX_LENGTH
from tests.fakes.in_memory_keyword_rule_repository import InMemoryKeywordRuleRepository
from tests.fakes.recording_notifier import RecordingNotifier

MALFORMED_DOCUMENT = "malformed"
EXPORTED_DOCUMENT = "exported-rules"
NOTIFIER_ERROR_TEXT = "notifier is failing"


class StubKeywordRuleDocumentCodec:
    def decode_rule_drafts(self, document_text: str) -> Sequence[KeywordRuleDraft]:
        if document_text == MALFORMED_DOCUMENT:
            raise InvalidDomainValueError("malformed document")
        return [KeywordRuleDraft(name="imported", query=document_text, is_enabled=True)]

    def encode_rules(self, rules: Sequence[KeywordRule]) -> str:
        return f"{EXPORTED_DOCUMENT}:{len(rules)}"


@asynccontextmanager
async def idle_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield


class ActionsHarness:
    def __init__(self) -> None:
        self.repository = InMemoryKeywordRuleRepository()
        self.notifier = RecordingNotifier()
        self.app = create_web_app(idle_lifespan)
        service = OperatorActionService(
            self.repository, self.notifier, StubKeywordRuleDocumentCodec()
        )
        self.app.dependency_overrides[get_operator_action_service] = lambda: service


@pytest.fixture
def harness() -> ActionsHarness:
    return ActionsHarness()


@pytest.fixture
def client(harness: ActionsHarness) -> Iterator[TestClient]:
    with TestClient(harness.app) as test_client:
        yield test_client


def test_test_notification_returns_204_and_sends_alert(
    client: TestClient, harness: ActionsHarness
) -> None:
    response = client.post("/api/actions/test-notification")

    assert response.status_code == 204
    assert harness.notifier.system_alerts == [TEST_NOTIFICATION_MESSAGE]


def test_test_notification_returns_502_when_delivery_fails(
    client: TestClient, harness: ActionsHarness
) -> None:
    harness.notifier.is_failing = True

    response = client.post("/api/actions/test-notification")

    assert response.status_code == 502
    assert NOTIFIER_ERROR_TEXT not in response.text


def test_import_yaml_returns_counts(client: TestClient) -> None:
    response = client.post("/api/actions/import-yaml", json={"document_text": "alpha"})

    assert response.status_code == 200
    assert response.json() == {"imported_rule_count": 1, "skipped_rule_count": 0}


def test_import_yaml_returns_422_for_malformed_document(client: TestClient) -> None:
    response = client.post("/api/actions/import-yaml", json={"document_text": MALFORMED_DOCUMENT})

    assert response.status_code == 422


def test_import_yaml_returns_422_for_oversized_document(client: TestClient) -> None:
    oversized_text = "x" * (KEYWORD_DOCUMENT_MAX_LENGTH + 1)

    response = client.post("/api/actions/import-yaml", json={"document_text": oversized_text})

    assert response.status_code == 422


def test_export_yaml_returns_attachment(client: TestClient) -> None:
    response = client.get("/api/actions/export-yaml")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/yaml")
    assert response.headers["content-disposition"] == 'attachment; filename="keywords.yaml"'
    assert response.text == f"{EXPORTED_DOCUMENT}:0"


async def test_reset_baseline_returns_204_and_clears_baseline(
    client: TestClient, harness: ActionsHarness
) -> None:
    rule = await harness.repository.add_rule("first", "alpha")
    await harness.repository.save_rule(
        KeywordRule(
            rule_id=rule.rule_id,
            name=rule.name,
            query=rule.query,
            is_enabled=rule.is_enabled,
            baseline_established_at=datetime(2026, 9, 30, tzinfo=UTC),
        )
    )

    response = client.post(f"/api/keywords/{rule.rule_id}/reset-baseline")

    assert response.status_code == 204
    assert (await harness.repository.get_rule(rule.rule_id)).baseline_established_at is None


def test_reset_baseline_returns_404_for_unknown_rule(client: TestClient) -> None:
    response = client.post("/api/keywords/99/reset-baseline")

    assert response.status_code == 404


def test_unwired_service_dependency_fails_loudly() -> None:
    with (
        TestClient(create_web_app(idle_lifespan)) as unwired_client,
        pytest.raises(RuntimeError),
    ):
        unwired_client.post("/api/actions/test-notification")
