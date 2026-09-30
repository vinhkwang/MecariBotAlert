from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from mercari_alert_bot.application.dto.notification_payload import (
    TELEGRAM_CAPTION_MAX_LENGTH,
    NotificationPayload,
    build_notification_payload,
)
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule, KeywordRuleId
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.money import JpyAmount

LISTING_URL = "https://jp.mercari.com/item/m1"

LISTING = Listing(
    item_id=ItemId("m1"),
    kind=ListingKind.MERCARI,
    title="OMEGA Seamaster",
    price=JpyAmount(12345),
    url=LISTING_URL,
    image_urls=("https://static.mercdn.net/m1.jpg",),
    created_at=datetime(2026, 9, 30, 10, 5, tzinfo=UTC),
)


def build_rule(rule_id: int, name: str) -> KeywordRule:
    return KeywordRule(
        rule_id=KeywordRuleId(rule_id),
        name=name,
        query=f"query {rule_id}",
        is_enabled=True,
        baseline_established_at=None,
    )


def test_caption_has_title_price_rules_time_and_url() -> None:
    payload = build_notification_payload(LISTING, [build_rule(1, "omega")])

    assert payload.caption == (
        f"OMEGA Seamaster\n¥12,345\nRules: omega\nListed: 2026-09-30 17:05 ICT\n{LISTING_URL}"
    )


def test_price_uses_thousands_separator() -> None:
    listing = replace(LISTING, price=JpyAmount(1234567))

    payload = build_notification_payload(listing, [build_rule(1, "omega")])

    assert payload.caption.splitlines()[1] == "¥1,234,567"


def test_lists_every_matched_rule_once_in_order() -> None:
    rules = [build_rule(1, "A"), build_rule(2, "B"), build_rule(1, "A"), build_rule(3, "C")]

    payload = build_notification_payload(LISTING, rules)

    assert payload.caption.splitlines()[2] == "Rules: A, B, C"


def test_rules_with_same_name_but_different_ids_are_both_listed() -> None:
    rules = [build_rule(1, "A"), build_rule(2, "A")]

    payload = build_notification_payload(LISTING, rules)

    assert payload.caption.splitlines()[2] == "Rules: A, A"


def test_rejects_empty_matched_rules() -> None:
    with pytest.raises(ValueError):
        build_notification_payload(LISTING, [])


def test_long_title_is_truncated_and_url_kept() -> None:
    listing = replace(LISTING, title="x" * 2000)

    payload = build_notification_payload(listing, [build_rule(1, "omega")])

    lines = payload.caption.splitlines()
    assert len(payload.caption) <= TELEGRAM_CAPTION_MAX_LENGTH
    assert lines[0].endswith("…")
    assert lines[2] == "Rules: omega"
    assert lines[-1] == LISTING_URL
    assert len(payload.caption) == TELEGRAM_CAPTION_MAX_LENGTH


def test_many_rules_are_truncated_after_title() -> None:
    listing = replace(LISTING, title="x" * 2000)
    rules = [build_rule(index, f"rule-{index}-" + "n" * 100) for index in range(1, 30)]

    payload = build_notification_payload(listing, rules)

    lines = payload.caption.splitlines()
    assert len(payload.caption) <= TELEGRAM_CAPTION_MAX_LENGTH
    assert lines[0] == "…"
    assert lines[2].startswith("Rules: rule-1-") and lines[2].endswith("…")
    assert lines[1] == "¥12,345"
    assert lines[3] == "Listed: 2026-09-30 17:05 ICT"
    assert lines[4] == LISTING_URL


def test_caption_at_exact_limit_is_not_truncated() -> None:
    fixed_length = (
        len("¥12,345")
        + len("Rules: omega")
        + len("Listed: 2026-09-30 17:05 ICT")
        + len(LISTING_URL)
        + 4
    )
    listing = replace(LISTING, title="x" * (TELEGRAM_CAPTION_MAX_LENGTH - fixed_length))

    payload = build_notification_payload(listing, [build_rule(1, "omega")])

    assert len(payload.caption) == TELEGRAM_CAPTION_MAX_LENGTH
    assert "…" not in payload.caption


def test_rules_line_is_emptied_when_url_leaves_no_room() -> None:
    listing = replace(LISTING, url="https://jp.mercari.com/item/" + "m" * 1100)

    payload = build_notification_payload(listing, [build_rule(1, "omega")])

    lines = payload.caption.splitlines()
    assert lines[0] == "…"
    assert lines[2] == ""
    assert lines[4] == listing.url


def test_photo_urls_keep_order_and_cap_at_ten() -> None:
    image_urls = tuple(f"https://static.mercdn.net/m1_{index}.jpg" for index in range(12))
    listing = replace(LISTING, image_urls=image_urls)

    payload = build_notification_payload(listing, [build_rule(1, "omega")])

    assert payload.photo_urls == image_urls[:10]


def test_listing_without_images_gives_empty_photo_urls() -> None:
    listing = replace(LISTING, image_urls=())

    payload = build_notification_payload(listing, [build_rule(1, "omega")])

    assert payload.photo_urls == ()


def test_payload_is_immutable() -> None:
    payload = NotificationPayload(caption="text", photo_urls=())

    with pytest.raises(FrozenInstanceError):
        payload.caption = "changed"  # type: ignore[misc]
