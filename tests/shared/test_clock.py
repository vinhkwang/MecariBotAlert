from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from mercari_alert_bot.shared.clock import Clock, SystemClock
from tests.shared.fakes import FrozenClock


def test_system_clock_returns_timezone_aware_utc() -> None:
    clock: Clock = SystemClock()

    assert clock.now().tzinfo is UTC


def test_frozen_clock_advances_by_elapsed_time() -> None:
    start_time = datetime(2026, 9, 29, 3, 0, tzinfo=UTC)
    clock = FrozenClock(start_time)
    assert clock.now() == start_time

    clock.advance(timedelta(seconds=30))

    assert clock.now() == start_time + timedelta(seconds=30)


def test_frozen_clock_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="UTC datetime"):
        FrozenClock(datetime(2026, 1, 1))


def test_frozen_clock_rejects_non_utc_datetime() -> None:
    with pytest.raises(ValueError, match="UTC datetime"):
        FrozenClock(datetime(2026, 1, 1, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh")))
