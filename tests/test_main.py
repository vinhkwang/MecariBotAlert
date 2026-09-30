from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI

from mercari_alert_bot import __main__ as entrypoint


def test_main_serves_web_app_on_configured_host_and_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "test-chat")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "bot.sqlite3"))
    served: list[tuple[Any, dict[str, Any]]] = []

    def record_run(app: Any, **kwargs: Any) -> None:
        served.append((app, kwargs))

    monkeypatch.setattr(entrypoint.uvicorn, "run", record_run)

    entrypoint.main()

    [(app, kwargs)] = served
    assert isinstance(app, FastAPI)
    assert kwargs == {"host": "127.0.0.1", "port": 8080, "log_config": None}
