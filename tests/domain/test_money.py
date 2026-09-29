import pytest

from mercari_alert_bot.domain.errors import InvalidDomainValueError
from mercari_alert_bot.domain.models.money import JpyAmount


def test_zero_yen_is_allowed() -> None:
    assert JpyAmount(0).yen == 0


def test_negative_yen_is_rejected() -> None:
    with pytest.raises(InvalidDomainValueError):
        JpyAmount(-1)


def test_bool_yen_is_rejected() -> None:
    with pytest.raises(InvalidDomainValueError):
        JpyAmount(True)


def test_float_yen_is_rejected() -> None:
    with pytest.raises(InvalidDomainValueError):
        JpyAmount(1.5)  # type: ignore[arg-type]


def test_invalid_yen_error_is_a_value_error() -> None:
    with pytest.raises(ValueError):
        JpyAmount(-1)
