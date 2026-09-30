from datetime import UTC, datetime, timedelta, timezone

import pytest

from mercari_alert_bot.shared.ict_time import format_ict_timestamp


def test_formats_utc_moment_as_ict() -> None:
    moment = datetime(2026, 9, 30, 10, 5, tzinfo=UTC)

    assert format_ict_timestamp(moment) == "2026-09-30 17:05 ICT"


def test_converts_from_non_utc_offset() -> None:
    japan_moment = datetime(2026, 9, 30, 19, 5, tzinfo=timezone(timedelta(hours=9)))
    utc_moment = datetime(2026, 9, 30, 10, 5, tzinfo=UTC)

    assert format_ict_timestamp(japan_moment) == format_ict_timestamp(utc_moment)


def test_crosses_date_boundary() -> None:
    moment = datetime(2026, 9, 30, 20, 0, tzinfo=UTC)

    assert format_ict_timestamp(moment) == "2026-10-01 03:00 ICT"


def test_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError):
        format_ict_timestamp(datetime(2026, 9, 30, 10, 5))
