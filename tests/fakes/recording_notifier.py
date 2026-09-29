from collections.abc import Sequence

from mercari_alert_bot.domain.errors import NotificationDeliveryError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRule
from mercari_alert_bot.domain.models.listing import Listing


class RecordingNotifier:
    def __init__(self) -> None:
        self.listing_alerts: list[tuple[Listing, tuple[KeywordRule, ...]]] = []
        self.system_alerts: list[str] = []
        self.is_failing = False

    async def send_listing_alert(
        self,
        listing: Listing,
        matched_rules: Sequence[KeywordRule],
    ) -> None:
        self._raise_if_failing()
        self.listing_alerts.append((listing, tuple(matched_rules)))

    async def send_system_alert(self, message: str) -> None:
        self._raise_if_failing()
        self.system_alerts.append(message)

    def _raise_if_failing(self) -> None:
        if self.is_failing:
            raise NotificationDeliveryError("notifier is failing")
