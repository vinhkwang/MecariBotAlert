from dataclasses import replace

import pytest

from mercari_alert_bot.domain.errors import InvalidDomainValueError
from mercari_alert_bot.domain.models.polling_settings import PollingSettings

VALID_SETTINGS = PollingSettings(
    polling_gap_seconds=60,
    is_item_detail_fetch_enabled=True,
    max_images_per_alert=4,
    consecutive_failure_alert_threshold=3,
    system_alert_cooldown_seconds=1800,
)


@pytest.mark.parametrize(
    "overrides",
    [
        {"polling_gap_seconds": 1},
        {"max_images_per_alert": 1},
        {"max_images_per_alert": 10},
        {"consecutive_failure_alert_threshold": 1},
        {"system_alert_cooldown_seconds": 0},
    ],
)
def test_accepts_values_on_every_bound(overrides: dict[str, int]) -> None:
    assert replace(VALID_SETTINGS, **overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"polling_gap_seconds": 0},
        {"max_images_per_alert": 0},
        {"max_images_per_alert": 11},
        {"consecutive_failure_alert_threshold": 0},
        {"system_alert_cooldown_seconds": -1},
    ],
)
def test_rejects_out_of_range_value(overrides: dict[str, int]) -> None:
    with pytest.raises(InvalidDomainValueError):
        replace(VALID_SETTINGS, **overrides)
