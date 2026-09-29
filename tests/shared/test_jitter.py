import random

import pytest

from mercari_alert_bot.shared.jitter import apply_jitter


def test_zero_ratio_returns_base_delay() -> None:
    assert apply_jitter(12.0, 0.0, random.Random(1)) == 12.0


def test_result_stays_within_jitter_bounds() -> None:
    rng = random.Random(7)

    delays = [apply_jitter(12.0, 0.25, rng) for _ in range(1_000)]

    assert all(9.0 <= delay <= 15.0 for delay in delays)


def test_same_seed_gives_same_delay() -> None:
    first_delay = apply_jitter(12.0, 0.25, random.Random(42))
    second_delay = apply_jitter(12.0, 0.25, random.Random(42))

    assert first_delay == second_delay


def test_negative_base_delay_is_rejected() -> None:
    with pytest.raises(ValueError, match="base_delay_seconds"):
        apply_jitter(-1.0, 0.25, random.Random(1))


@pytest.mark.parametrize("jitter_ratio", [-0.1, 1.1])
def test_ratio_outside_unit_interval_is_rejected(jitter_ratio: float) -> None:
    with pytest.raises(ValueError, match="jitter_ratio"):
        apply_jitter(12.0, jitter_ratio, random.Random(1))
