from pathlib import Path

import pytest
from pydantic import ValidationError

from mercari_alert_bot.infrastructure.config.env_settings import EnvSettings

ENV_EXAMPLE_PATH = Path(__file__).resolve().parents[3] / ".env.example"

BOT_TOKEN = "123456:secret-bot-token"
CHAT_ID = "-1009876543210"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for field_name in EnvSettings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)


@pytest.fixture
def telegram_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", BOT_TOKEN)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT_ID)


def build_settings() -> EnvSettings:
    return EnvSettings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.usefixtures("telegram_credentials")
def test_loads_telegram_credentials_from_environment() -> None:
    settings = build_settings()

    assert settings.telegram_bot_token.get_secret_value() == BOT_TOKEN
    assert settings.telegram_chat_id.get_secret_value() == CHAT_ID


def test_missing_telegram_bot_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT_ID)

    with pytest.raises(ValidationError):
        build_settings()


def test_missing_telegram_chat_id_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", BOT_TOKEN)

    with pytest.raises(ValidationError):
        build_settings()


def test_empty_telegram_bot_token_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT_ID)

    with pytest.raises(ValidationError):
        build_settings()


@pytest.mark.usefixtures("telegram_credentials")
def test_defaults_apply_when_optional_variables_absent() -> None:
    settings = build_settings()

    assert settings.web_host == "127.0.0.1"
    assert settings.web_port == 8080
    assert settings.polling_gap_seconds == 60
    assert settings.keyword_rule_source == "sqlite"
    assert settings.is_item_detail_fetch_enabled is True
    assert settings.max_images_per_alert == 4


@pytest.mark.usefixtures("telegram_credentials")
def test_optional_variables_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_PORT", "9090")
    monkeypatch.setenv("POLLING_GAP_SECONDS", "18")
    monkeypatch.setenv("KEYWORD_RULE_SOURCE", "yaml")
    monkeypatch.setenv("IS_ITEM_DETAIL_FETCH_ENABLED", "false")
    monkeypatch.setenv("DATABASE_PATH", "var/state.sqlite3")

    settings = build_settings()

    assert settings.web_port == 9090
    assert settings.polling_gap_seconds == 18
    assert settings.keyword_rule_source == "yaml"
    assert settings.is_item_detail_fetch_enabled is False
    assert settings.database_path == Path("var/state.sqlite3")


@pytest.mark.usefixtures("telegram_credentials")
@pytest.mark.parametrize(
    ("variable_name", "invalid_value"),
    [
        ("WEB_PORT", "0"),
        ("POLLING_GAP_SECONDS", "0"),
        ("MAX_IMAGES_PER_ALERT", "11"),
        ("KEYWORD_RULE_SOURCE", "postgres"),
        ("LOG_LEVEL", "TRACE"),
        ("SEARCH_PAGE_SIZE", "121"),
        ("CONSECUTIVE_FAILURE_ALERT_THRESHOLD", "0"),
        ("SYSTEM_ALERT_COOLDOWN_SECONDS", "-1"),
    ],
)
def test_out_of_range_values_are_rejected(
    monkeypatch: pytest.MonkeyPatch, variable_name: str, invalid_value: str
) -> None:
    monkeypatch.setenv(variable_name, invalid_value)

    with pytest.raises(ValidationError):
        build_settings()


@pytest.mark.usefixtures("telegram_credentials")
def test_secrets_never_appear_in_repr_str_or_dump() -> None:
    settings = build_settings()

    rendered_forms = [repr(settings), str(settings), settings.model_dump_json()]

    for rendered in rendered_forms:
        assert BOT_TOKEN not in rendered
        assert CHAT_ID not in rendered


@pytest.mark.usefixtures("telegram_credentials")
def test_settings_are_immutable() -> None:
    settings = build_settings()

    with pytest.raises(ValidationError):
        settings.web_port = 9999


def read_env_example_assignments() -> dict[str, str]:
    assignments: dict[str, str] = {}
    for line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            name, _, value = line.partition("=")
            assignments[name.strip()] = value.strip()
    return assignments


def test_env_example_lists_every_setting() -> None:
    assignments = read_env_example_assignments()

    assert set(assignments) == {name.upper() for name in EnvSettings.model_fields}
    assert all(value == "" for value in assignments.values())


@pytest.mark.usefixtures("telegram_credentials")
def test_empty_optional_variables_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ["WEB_HOST", "WEB_PORT", "DATABASE_PATH", "POLLING_GAP_SECONDS"]:
        monkeypatch.setenv(name, "")

    settings = build_settings()

    assert settings.web_host == "127.0.0.1"
    assert settings.web_port == 8080
    assert settings.database_path == Path("data/mercari_alert_bot.sqlite3")
    assert settings.polling_gap_seconds == 60
