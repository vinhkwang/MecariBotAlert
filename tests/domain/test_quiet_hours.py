from datetime import UTC, time

import pytest

from mercari_alert_bot.domain.errors import InvalidDomainValueError
from mercari_alert_bot.domain.models.quiet_hours import QuietHoursWindow

DAYTIME_WINDOW = QuietHoursWindow(starts_at=time(12, 0), ends_at=time(14, 0))
OVERNIGHT_WINDOW = QuietHoursWindow(starts_at=time(22, 0), ends_at=time(7, 0))


def test_same_day_window_contains_time_inside() -> None:
    assert DAYTIME_WINDOW.contains(time(13, 0))


def test_same_day_window_includes_start() -> None:
    assert DAYTIME_WINDOW.contains(time(12, 0))


def test_same_day_window_excludes_end() -> None:
    assert not DAYTIME_WINDOW.contains(time(14, 0))


def test_same_day_window_excludes_time_before_start() -> None:
    assert not DAYTIME_WINDOW.contains(time(11, 59))


def test_same_day_window_does_not_cross_midnight() -> None:
    assert DAYTIME_WINDOW.crosses_midnight is False


def test_crossing_window_crosses_midnight() -> None:
    assert OVERNIGHT_WINDOW.crosses_midnight is True


def test_crossing_window_contains_late_evening() -> None:
    assert OVERNIGHT_WINDOW.contains(time(23, 30))


def test_crossing_window_contains_exact_midnight() -> None:
    assert OVERNIGHT_WINDOW.contains(time(0, 0))


def test_crossing_window_contains_early_morning() -> None:
    assert OVERNIGHT_WINDOW.contains(time(6, 59))


def test_crossing_window_includes_start() -> None:
    assert OVERNIGHT_WINDOW.contains(time(22, 0))


def test_crossing_window_excludes_end() -> None:
    assert not OVERNIGHT_WINDOW.contains(time(7, 0))


def test_crossing_window_excludes_midday() -> None:
    assert not OVERNIGHT_WINDOW.contains(time(12, 0))


def test_crossing_window_excludes_just_before_start() -> None:
    assert not OVERNIGHT_WINDOW.contains(time(21, 59))


def test_window_ending_at_midnight_contains_last_minute() -> None:
    window = QuietHoursWindow(starts_at=time(22, 0), ends_at=time(0, 0))

    assert window.contains(time(23, 59))
    assert not window.contains(time(0, 0))


def test_equal_start_and_end_is_rejected() -> None:
    with pytest.raises(InvalidDomainValueError):
        QuietHoursWindow(starts_at=time(8, 0), ends_at=time(8, 0))


def test_aware_start_is_rejected() -> None:
    with pytest.raises(InvalidDomainValueError):
        QuietHoursWindow(starts_at=time(8, 0, tzinfo=UTC), ends_at=time(9, 0))


def test_aware_end_is_rejected() -> None:
    with pytest.raises(InvalidDomainValueError):
        QuietHoursWindow(starts_at=time(8, 0), ends_at=time(9, 0, tzinfo=UTC))


def test_contains_rejects_aware_time() -> None:
    with pytest.raises(InvalidDomainValueError):
        DAYTIME_WINDOW.contains(time(13, 0, tzinfo=UTC))
