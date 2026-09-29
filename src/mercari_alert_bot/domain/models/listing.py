from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType

from mercari_alert_bot.domain.errors import InvalidDomainValueError
from mercari_alert_bot.domain.models.money import JpyAmount

ItemId = NewType("ItemId", str)


class ListingKind(StrEnum):
    MERCARI = "mercari"
    SHOPS = "shops"


@dataclass(frozen=True, slots=True, kw_only=True)
class Listing:
    item_id: ItemId
    kind: ListingKind
    title: str
    price: JpyAmount
    url: str
    image_urls: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            raise InvalidDomainValueError("item_id must not be blank")
        if self.created_at.utcoffset() is None:
            raise InvalidDomainValueError("created_at must be timezone-aware")
