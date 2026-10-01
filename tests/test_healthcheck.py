from email.message import Message
from types import TracebackType
from typing import Self
from urllib.error import HTTPError, URLError

import pytest

from mercari_alert_bot import healthcheck
from mercari_alert_bot.healthcheck import build_health_url, is_service_healthy, main

HEALTH_URL = "http://127.0.0.1:8080/healthz"


class FakeResponse:
    def __init__(self, status: int) -> None:
        self.status = status

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None


def stub_urlopen_response(monkeypatch: pytest.MonkeyPatch, status: int) -> list[float]:
    received_timeouts: list[float] = []

    def fake_urlopen(_url: str, timeout: float) -> FakeResponse:
        received_timeouts.append(timeout)
        return FakeResponse(status)

    monkeypatch.setattr(healthcheck, "urlopen", fake_urlopen)
    return received_timeouts


def stub_urlopen_failure(monkeypatch: pytest.MonkeyPatch, failure: BaseException) -> None:
    def failing_urlopen(_url: str, **_options: float) -> FakeResponse:
        raise failure

    monkeypatch.setattr(healthcheck, "urlopen", failing_urlopen)


def test_health_url_uses_web_port_from_environment() -> None:
    assert build_health_url({"WEB_PORT": "9090"}) == "http://127.0.0.1:9090/healthz"


def test_health_url_defaults_to_port_8080() -> None:
    assert build_health_url({}) == HEALTH_URL


def test_health_url_treats_empty_web_port_as_default() -> None:
    assert build_health_url({"WEB_PORT": ""}) == HEALTH_URL


def test_health_url_ignores_web_host() -> None:
    assert build_health_url({"WEB_HOST": "0.0.0.0"}) == HEALTH_URL


def test_service_is_healthy_on_status_200(monkeypatch: pytest.MonkeyPatch) -> None:
    received_timeouts = stub_urlopen_response(monkeypatch, 200)

    assert is_service_healthy(HEALTH_URL, timeout_seconds=2.5) is True
    assert received_timeouts == [2.5]


def test_service_is_unhealthy_on_non_200_success(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_urlopen_response(monkeypatch, 204)

    assert is_service_healthy(HEALTH_URL) is False


def test_service_is_unhealthy_on_connection_error(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_urlopen_failure(monkeypatch, URLError("connection refused"))

    assert is_service_healthy(HEALTH_URL) is False


def test_service_is_unhealthy_on_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_urlopen_failure(monkeypatch, HTTPError(HEALTH_URL, 503, "unavailable", Message(), None))

    assert is_service_healthy(HEALTH_URL) is False


def test_service_is_unhealthy_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_urlopen_failure(monkeypatch, TimeoutError())

    assert is_service_healthy(HEALTH_URL) is False


def test_main_exits_zero_when_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_urlopen_response(monkeypatch, 200)

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 0


def test_main_exits_one_when_unhealthy(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_urlopen_failure(monkeypatch, URLError("connection refused"))

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
