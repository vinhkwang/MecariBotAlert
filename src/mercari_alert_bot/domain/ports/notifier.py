from collections.abc import Sequence
from typing import Protocol

from mercari_alert_bot.domain.models.keyword_rule import KeywordRule
from mercari_alert_bot.domain.models.listing import Listing


class Notifier(Protocol):
    async def send_listing_alert(
        self,
        listing: Listing,
        matched_rules: Sequence[KeywordRule],
    ) -> None: ...

    async def send_system_alert(self, message: str) -> None: ...
