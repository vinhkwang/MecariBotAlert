from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from mercari_alert_bot.domain.models.keyword_rule import KeywordRule, KeywordRuleId
from mercari_alert_bot.domain.models.listing import Listing
from mercari_alert_bot.shared.ict_time import format_ict_timestamp

TELEGRAM_CAPTION_MAX_LENGTH: Final = 1024
TELEGRAM_MEDIA_GROUP_MAX_PHOTOS: Final = 10
_TRUNCATION_MARKER: Final = "…"
_RULES_LINE_PREFIX: Final = "Rules: "
_RULE_NAME_SEPARATOR: Final = ", "
_CAPTION_LINE_COUNT: Final = 5


@dataclass(frozen=True, slots=True, kw_only=True)
class NotificationPayload:
    caption: str
    photo_urls: tuple[str, ...]


def build_notification_payload(
    listing: Listing,
    matched_rules: Sequence[KeywordRule],
) -> NotificationPayload:
    if not matched_rules:
        raise ValueError("matched_rules must not be empty")
    return NotificationPayload(
        caption=_build_caption(listing, matched_rules),
        photo_urls=listing.image_urls[:TELEGRAM_MEDIA_GROUP_MAX_PHOTOS],
    )


def _build_caption(listing: Listing, matched_rules: Sequence[KeywordRule]) -> str:
    price_line = f"¥{listing.price.yen:,}"
    time_line = f"Listed: {format_ict_timestamp(listing.created_at)}"
    rules_line = _RULES_LINE_PREFIX + _RULE_NAME_SEPARATOR.join(
        _list_distinct_rule_names(matched_rules)
    )
    protected_length = len(price_line) + len(time_line) + len(listing.url)
    separator_length = _CAPTION_LINE_COUNT - 1
    flexible_budget = TELEGRAM_CAPTION_MAX_LENGTH - protected_length - separator_length

    title_budget = max(flexible_budget - len(rules_line), 1)
    title_line = _truncate_with_marker(listing.title, title_budget)
    rules_budget = flexible_budget - len(title_line)
    rules_line = _truncate_with_marker(rules_line, rules_budget)

    return "\n".join([title_line, price_line, rules_line, time_line, listing.url])


def _list_distinct_rule_names(matched_rules: Sequence[KeywordRule]) -> list[str]:
    names_by_rule_id: dict[KeywordRuleId, str] = {}
    for rule in matched_rules:
        names_by_rule_id.setdefault(rule.rule_id, rule.name)
    return list(names_by_rule_id.values())


def _truncate_with_marker(text: str, max_length: int) -> str:
    if max_length <= 0:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + _TRUNCATION_MARKER
