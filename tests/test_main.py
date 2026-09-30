import asyncio
import os
import signal
from collections.abc import Callable
from pathlib import Path

import pytest

from mercari_alert_bot.__main__ import run_scanner
from mercari_alert_bot.infrastructure.config.env_settings import EnvSettings

SHUTDOWN_TIMEOUT_SECONDS = 5


def build_idle_settings(tmp_path: Path) -> EnvSettings:
    return EnvSettings(
        _env_file=None,
        telegram_bot_token="test-token",
        telegram_chat_id="test-chat",
        database_path=tmp_path / "bot.sqlite3",
        keyword_seed_path=tmp_path / "missing-keywords.yaml",
        polling_gap_seconds=3600,
    )


async def run_scanner_until_sigterm(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    loop = asyncio.get_running_loop()
    sigterm_handler_installed = asyncio.Event()
    install_signal_handler = loop.add_signal_handler

    def install_and_announce(sig: int, callback: Callable[[], None]) -> None:
        install_signal_handler(sig, callback)
        if sig == signal.SIGTERM:
            sigterm_handler_installed.set()

    monkeypatch.setattr(loop, "add_signal_handler", install_and_announce)
    scanner_task = asyncio.create_task(run_scanner(build_idle_settings(tmp_path)))
    async with asyncio.timeout(SHUTDOWN_TIMEOUT_SECONDS):
        await sigterm_handler_installed.wait()
    os.kill(os.getpid(), signal.SIGTERM)
    async with asyncio.timeout(SHUTDOWN_TIMEOUT_SECONDS):
        await scanner_task


async def test_run_scanner_stops_on_sigterm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await run_scanner_until_sigterm(tmp_path, monkeypatch)


async def test_run_scanner_removes_signal_handlers_on_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    await run_scanner_until_sigterm(tmp_path, monkeypatch)

    assert signal.getsignal(signal.SIGTERM) == signal.SIG_DFL
