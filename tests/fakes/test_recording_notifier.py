from datetime import UTC, datetime

import pytest

from mercari_alert_bot.domain.errors import NotificationDeliveryError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule, KeywordRuleId
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.money import JpyAmount
from mercari_alert_bot.domain.ports.notifier import Notifier
from tests.fakes.recording_notifier import RecordingNotifier

LISTING = Listing(
    item_id=ItemId("m1"),
    kind=ListingKind.MERCARI,
    title="OMEGA Seamaster",
    price=JpyAmount(120000),
    url="https://jp.mercari.com/item/m1",
    image_urls=("https://static.mercdn.net/m1.jpg",),
    created_at=datetime(2026, 9, 29, 3, 0, tzinfo=UTC),
)


def build_rule(rule_id: int) -> KeywordRule:
    return KeywordRule(
        rule_id=KeywordRuleId(rule_id),
        name=f"rule {rule_id}",
        query=f"query {rule_id}",
        is_enabled=True,
        baseline_established_at=None,
    )


async def test_listing_alert_is_recorded_with_all_matched_rules() -> None:
    notifier = RecordingNotifier()
    sender: Notifier = notifier
    rules = [build_rule(1), build_rule(2)]

    await sender.send_listing_alert(LISTING, rules)

    assert notifier.listing_alerts == [(LISTING, tuple(rules))]


async def test_system_alert_is_recorded() -> None:
    notifier = RecordingNotifier()

    await notifier.send_system_alert("all rules returned zero results")

    assert notifier.system_alerts == ["all rules returned zero results"]


async def test_failing_notifier_raises_and_records_nothing() -> None:
    notifier = RecordingNotifier()
    notifier.is_failing = True

    with pytest.raises(NotificationDeliveryError):
        await notifier.send_listing_alert(LISTING, [build_rule(1)])
    with pytest.raises(NotificationDeliveryError):
        await notifier.send_system_alert("down")

    assert notifier.listing_alerts == []
    assert notifier.system_alerts == []
