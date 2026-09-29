from pathlib import Path

import pytest
import yaml

from mercari_alert_bot.domain.models.keyword_rule import KeywordRule, KeywordRuleId
from mercari_alert_bot.infrastructure.persistence.keyword_rule_yaml import (
    KeywordSeedFormatError,
    export_keyword_rules_yaml,
    import_seed_rules_when_empty,
)
from tests.fakes.in_memory_keyword_rule_repository import InMemoryKeywordRuleRepository


def write_seed(tmp_path: Path, text: str) -> Path:
    seed_path = tmp_path / "keywords.yaml"
    seed_path.write_text(text, encoding="utf-8")
    return seed_path


async def read_triples(repository: InMemoryKeywordRuleRepository) -> list[tuple[str, str, bool]]:
    return [(rule.name, rule.query, rule.is_enabled) for rule in await repository.list_rules()]


async def test_import_adds_seed_rules_in_file_order(tmp_path: Path) -> None:
    seed_path = write_seed(
        tmp_path,
        "keywords:\n"
        "  - {name: first, query: alpha, enabled: true}\n"
        "  - {name: second, query: beta, enabled: false}\n",
    )
    repository = InMemoryKeywordRuleRepository()

    imported_count = await import_seed_rules_when_empty(repository, seed_path)

    assert imported_count == 2
    assert await read_triples(repository) == [
        ("first", "alpha", True),
        ("second", "beta", False),
    ]


async def test_import_defaults_missing_enabled_to_true(tmp_path: Path) -> None:
    seed_path = write_seed(tmp_path, "keywords:\n  - {name: first, query: alpha}\n")
    repository = InMemoryKeywordRuleRepository()

    await import_seed_rules_when_empty(repository, seed_path)

    assert await read_triples(repository) == [("first", "alpha", True)]


async def test_import_skips_when_repository_has_rules(tmp_path: Path) -> None:
    seed_path = write_seed(tmp_path, "keywords:\n  - {name: seeded, query: gamma}\n")
    existing_rule = KeywordRule(
        rule_id=KeywordRuleId(1),
        name="existing",
        query="delta",
        is_enabled=True,
        baseline_established_at=None,
    )
    repository = InMemoryKeywordRuleRepository([existing_rule])

    imported_count = await import_seed_rules_when_empty(repository, seed_path)

    assert imported_count == 0
    assert list(await repository.list_rules()) == [existing_rule]


async def test_import_returns_zero_when_seed_file_missing(tmp_path: Path) -> None:
    repository = InMemoryKeywordRuleRepository()

    imported_count = await import_seed_rules_when_empty(repository, tmp_path / "absent.yaml")

    assert imported_count == 0
    assert await repository.list_rules() == []


async def test_import_of_shipped_empty_seed_adds_nothing(tmp_path: Path) -> None:
    seed_path = write_seed(
        tmp_path,
        "polling:\n  page_size: 30\nhealth:\n  alert_cooldown_minutes: 30\nkeywords: []\n",
    )
    repository = InMemoryKeywordRuleRepository()

    assert await import_seed_rules_when_empty(repository, seed_path) == 0
    assert await repository.list_rules() == []


async def test_import_treats_missing_keywords_key_as_empty(tmp_path: Path) -> None:
    seed_path = write_seed(tmp_path, "polling:\n  page_size: 30\n")
    repository = InMemoryKeywordRuleRepository()

    assert await import_seed_rules_when_empty(repository, seed_path) == 0
    assert await repository.list_rules() == []


async def test_import_keeps_unicode_queries(tmp_path: Path) -> None:
    seed_path = write_seed(tmp_path, "keywords:\n  - {name: カメラ, query: フィルムカメラ}\n")
    repository = InMemoryKeywordRuleRepository()

    await import_seed_rules_when_empty(repository, seed_path)

    assert await read_triples(repository) == [("カメラ", "フィルムカメラ", True)]


@pytest.mark.parametrize(
    "seed_text",
    [
        "- name: first\n",
        "keywords: not-a-list\n",
        "keywords:\n  - just-a-string\n",
        "keywords:\n  - {query: alpha}\n",
        "keywords:\n  - {name: first, query: '  '}\n",
        "keywords:\n  - {name: first, query: alpha, enabled: 'yes'}\n",
        "keywords: [unclosed\n",
    ],
)
async def test_import_rejects_malformed_seed_without_importing(
    tmp_path: Path, seed_text: str
) -> None:
    seed_path = write_seed(tmp_path, seed_text)
    repository = InMemoryKeywordRuleRepository()

    with pytest.raises(KeywordSeedFormatError):
        await import_seed_rules_when_empty(repository, seed_path)

    assert await repository.list_rules() == []


async def test_import_validates_whole_file_before_adding_any_rule(tmp_path: Path) -> None:
    seed_path = write_seed(
        tmp_path, "keywords:\n  - {name: valid, query: alpha}\n  - {name: broken}\n"
    )
    repository = InMemoryKeywordRuleRepository()

    with pytest.raises(KeywordSeedFormatError):
        await import_seed_rules_when_empty(repository, seed_path)

    assert await repository.list_rules() == []


async def add_sample_rules(repository: InMemoryKeywordRuleRepository) -> None:
    await repository.add_rule("first", "alpha")
    await repository.add_rule("second", "beta", is_enabled=False)


async def test_export_writes_every_rule_in_order() -> None:
    repository = InMemoryKeywordRuleRepository()
    await add_sample_rules(repository)

    exported = yaml.safe_load(await export_keyword_rules_yaml(repository))

    assert exported == {
        "keywords": [
            {"name": "first", "query": "alpha", "enabled": True},
            {"name": "second", "query": "beta", "enabled": False},
        ]
    }


async def test_export_of_empty_repository_is_empty_keyword_list() -> None:
    exported = yaml.safe_load(await export_keyword_rules_yaml(InMemoryKeywordRuleRepository()))

    assert exported == {"keywords": []}


async def test_export_keeps_japanese_text_unescaped() -> None:
    repository = InMemoryKeywordRuleRepository()
    await repository.add_rule("カメラ", "フィルムカメラ")

    exported_text = await export_keyword_rules_yaml(repository)

    assert "フィルムカメラ" in exported_text


async def test_export_then_import_round_trips(tmp_path: Path) -> None:
    source_repository = InMemoryKeywordRuleRepository()
    await add_sample_rules(source_repository)
    await source_repository.add_rule("カメラ", "フィルムカメラ")
    seed_path = write_seed(tmp_path, await export_keyword_rules_yaml(source_repository))
    target_repository = InMemoryKeywordRuleRepository()

    await import_seed_rules_when_empty(target_repository, seed_path)

    assert await read_triples(target_repository) == await read_triples(source_repository)
