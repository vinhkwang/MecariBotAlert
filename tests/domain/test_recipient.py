from dataclasses import replace
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest

from mercari_alert_bot.domain.errors import InvalidDomainValueError
from mercari_alert_bot.domain.models.quiet_hours import QuietHoursWindow
from mercari_alert_bot.domain.models.recipient import (
    Recipient,
    RecipientId,
    TelegramChatId,
    VerificationStatus,
)

OVERNIGHT_WINDOW = QuietHoursWindow(starts_at=time(22, 0), ends_at=time(7, 0))


def make_recipient(
    *,
    display_name: str = "Owner",
    telegram_chat_id: str = "12345",
    verification_status: VerificationStatus = VerificationStatus.VERIFIED,
    is_enabled: bool = True,
    timezone_name: str = "Asia/Ho_Chi_Minh",
    quiet_hours: QuietHoursWindow | None = None,
) -> Recipient:
    return Recipient(
        recipient_id=RecipientId(1),
        display_name=display_name,
        telegram_chat_id=TelegramChatId(telegram_chat_id),
        verification_status=verification_status,
        is_enabled=is_enabled,
        timezone=ZoneInfo(timezone_name),
        quiet_hours=quiet_hours,
    )


def test_valid_recipient_keeps_its_fields() -> None:
    recipient = make_recipient(quiet_hours=OVERNIGHT_WINDOW)

    assert recipient.recipient_id == RecipientId(1)
    assert recipient.display_name == "Owner"
    assert recipient.telegram_chat_id == TelegramChatId("12345")
    assert recipient.verification_status is VerificationStatus.VERIFIED
    assert recipient.is_enabled is True
    assert recipient.timezone == ZoneInfo("Asia/Ho_Chi_Minh")
    assert recipient.quiet_hours == OVERNIGHT_WINDOW


def test_blank_display_name_is_rejected() -> None:
    with pytest.raises(InvalidDomainValueError):
        make_recipient(display_name="   ")


def test_blank_telegram_chat_id_is_rejected() -> None:
    with pytest.raises(InvalidDomainValueError):
        make_recipient(telegram_chat_id="  ")


def test_verification_status_values_are_stable() -> None:
    assert VerificationStatus.PENDING.value == "pending"
    assert VerificationStatus.VERIFIED.value == "verified"


def test_pending_recipient_is_not_verified() -> None:
    assert not make_recipient(verification_status=VerificationStatus.PENDING).is_verified


def test_verified_recipient_is_verified() -> None:
    assert make_recipient(verification_status=VerificationStatus.VERIFIED).is_verified


def test_enabled_verified_recipient_can_receive_listing_alerts() -> None:
    assert make_recipient().can_receive_listing_alerts


def test_disabled_recipient_cannot_receive_listing_alerts() -> None:
    assert not make_recipient(is_enabled=False).can_receive_listing_alerts


def test_pending_recipient_cannot_receive_listing_alerts() -> None:
    recipient = make_recipient(verification_status=VerificationStatus.PENDING)

    assert not recipient.can_receive_listing_alerts


def test_recipient_without_quiet_hours_is_never_quiet() -> None:
    recipient = make_recipient(quiet_hours=None)

    assert not recipient.is_quiet_at(datetime(2026, 1, 15, 18, 0, tzinfo=UTC))


def test_quiet_hours_are_evaluated_in_recipient_timezone() -> None:
    moment = datetime(2026, 1, 15, 14, 30, tzinfo=UTC)
    tokyo_recipient = make_recipient(timezone_name="Asia/Tokyo", quiet_hours=OVERNIGHT_WINDOW)
    ict_recipient = replace(tokyo_recipient, timezone=ZoneInfo("Asia/Ho_Chi_Minh"))

    assert tokyo_recipient.is_quiet_at(moment)
    assert not ict_recipient.is_quiet_at(moment)


def test_quiet_hours_cross_midnight_in_recipient_timezone() -> None:
    recipient = make_recipient(timezone_name="Europe/London", quiet_hours=OVERNIGHT_WINDOW)

    assert recipient.is_quiet_at(datetime(2026, 1, 15, 3, 0, tzinfo=UTC))
    assert not recipient.is_quiet_at(datetime(2026, 1, 15, 12, 0, tzinfo=UTC))


def test_is_quiet_at_rejects_naive_moment() -> None:
    recipient = make_recipient(quiet_hours=OVERNIGHT_WINDOW)

    with pytest.raises(InvalidDomainValueError):
        recipient.is_quiet_at(datetime(2026, 1, 15, 3, 0))
