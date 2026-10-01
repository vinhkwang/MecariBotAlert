from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mercari_alert_bot.application.services.keyword_rule_service import KeywordRuleService
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule, KeywordRuleId
from mercari_alert_bot.web.app import create_web_app
from mercari_alert_bot.web.dependencies import provide_keyword_rule_service
from tests.fakes.in_memory_keyword_rule_repository import InMemoryKeywordRuleRepository

SEEDED_AT = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
TELEGRAM_SECRET_MARKERS = ("telegram_bot_token", "telegram_chat_id", "test-token", "test-chat")
UNKNOWN_ID = 99


@asynccontextmanager
async def idle_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield


def build_seeded_rule(rule_id: int, name: str, query: str) -> KeywordRule:
    return KeywordRule(
        rule_id=KeywordRuleId(rule_id),
        name=name,
        query=query,
        is_enabled=True,
        baseline_established_at=SEEDED_AT,
    )


@pytest.fixture
def client() -> Iterator[TestClient]:
    repository = InMemoryKeywordRuleRepository(
        [
            build_seeded_rule(1, "omega", "omega 168.005"),
            build_seeded_rule(2, "seiko", "seiko 6139"),
        ]
    )
    service = KeywordRuleService(repository)
    app = create_web_app(idle_lifespan)
    app.dependency_overrides[provide_keyword_rule_service] = lambda: service
    with TestClient(app) as test_client:
        yield test_client


def test_list_keywords_returns_rules(client: TestClient) -> None:
    response = client.get("/api/keywords")

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 1,
            "name": "omega",
            "query": "omega 168.005",
            "is_enabled": True,
            "has_baseline": True,
            "baseline_established_at": "2026-09-30T10:00:00Z",
        },
        {
            "id": 2,
            "name": "seiko",
            "query": "seiko 6139",
            "is_enabled": True,
            "has_baseline": True,
            "baseline_established_at": "2026-09-30T10:00:00Z",
        },
    ]


def test_create_keyword_returns_201_without_baseline(client: TestClient) -> None:
    response = client.post("/api/keywords", json={"name": "rolex", "query": "rolex 1601"})

    assert response.status_code == 201
    assert response.json() == {
        "id": 3,
        "name": "rolex",
        "query": "rolex 1601",
        "is_enabled": True,
        "has_baseline": False,
        "baseline_established_at": None,
    }
    assert len(client.get("/api/keywords").json()) == 3


def test_create_keyword_strips_whitespace(client: TestClient) -> None:
    response = client.post("/api/keywords", json={"name": "  rolex ", "query": " rolex 1601  "})

    assert (response.json()["name"], response.json()["query"]) == ("rolex", "rolex 1601")


@pytest.mark.parametrize(
    "body",
    [
        {"name": "   ", "query": "rolex"},
        {"name": "rolex", "query": ""},
        {"name": "rolex"},
    ],
)
def test_create_keyword_rejects_blank_name_and_query(
    client: TestClient, body: dict[str, str]
) -> None:
    assert client.post("/api/keywords", json=body).status_code == 422


def test_patch_query_returns_rule_without_baseline(client: TestClient) -> None:
    response = client.patch("/api/keywords/1", json={"query": "omega 166.010"})

    assert response.status_code == 200
    assert response.json()["query"] == "omega 166.010"
    assert response.json()["has_baseline"] is False


def test_patch_is_enabled_keeps_baseline(client: TestClient) -> None:
    response = client.patch("/api/keywords/1", json={"is_enabled": False})

    assert response.status_code == 200
    assert response.json()["is_enabled"] is False
    assert response.json()["has_baseline"] is True


def test_delete_keyword_returns_204_and_rule_is_gone(client: TestClient) -> None:
    response = client.delete("/api/keywords/1")

    assert response.status_code == 204
    assert [rule["id"] for rule in client.get("/api/keywords").json()] == [2]


def test_reset_baseline_returns_rule_without_baseline(client: TestClient) -> None:
    response = client.post("/api/keywords/1/reset-baseline")

    assert response.status_code == 200
    assert response.json()["has_baseline"] is False
    assert response.json()["query"] == "omega 168.005"


def test_unknown_rule_id_returns_404(client: TestClient) -> None:
    assert client.patch(f"/api/keywords/{UNKNOWN_ID}", json={"name": "x"}).status_code == 404
    assert client.delete(f"/api/keywords/{UNKNOWN_ID}").status_code == 404
    assert client.post(f"/api/keywords/{UNKNOWN_ID}/reset-baseline").status_code == 404


def test_keyword_responses_never_contain_telegram_secrets(client: TestClient) -> None:
    bodies = [
        client.get("/api/keywords").text,
        client.post("/api/keywords", json={"name": "rolex", "query": "rolex"}).text,
        client.patch("/api/keywords/1", json={"name": "renamed"}).text,
        client.post("/api/keywords/1/reset-baseline").text,
    ]

    for body in bodies:
        for marker in TELEGRAM_SECRET_MARKERS:
            assert marker not in body


def test_static_index_still_served(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
