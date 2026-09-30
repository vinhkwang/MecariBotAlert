from datetime import UTC, datetime
from typing import Final

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mercari_alert_bot.domain.errors import ListingSourceError
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.money import JpyAmount

MERCARI_ITEM_PAGE_URL_TEMPLATE: Final = "https://jp.mercari.com/item/{item_id}"
SHOPS_PRODUCT_PAGE_URL_TEMPLATE: Final = "https://jp.mercari.com/shops/product/{item_id}"
SHOPS_ITEM_TYPE: Final = "ITEM_TYPE_BEYOND"

logger = structlog.get_logger()


class MercariResponseShapeError(ListingSourceError):
    pass


class _UpstreamItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    price: int
    created: int
    item_type: str = Field(alias="itemType")
    thumbnails: list[str]


class _UpstreamItemDetailData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    photos: list[str]


class _UpstreamItemDetail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: _UpstreamItemDetailData


class MercariSearchResponseMapper:
    def map_search_response(self, response_body: object) -> list[Listing]:
        raw_items = self._extract_raw_items(response_body)
        listings = [
            listing
            for listing in (self._map_item_or_skip(raw_item) for raw_item in raw_items)
            if listing is not None
        ]
        if raw_items and not listings:
            raise MercariResponseShapeError("every item on a non-empty page was malformed")
        return listings

    def map_item_detail_photo_urls(self, response_body: object) -> tuple[str, ...]:
        try:
            detail = _UpstreamItemDetail.model_validate(response_body)
        except ValidationError as error:
            raise MercariResponseShapeError("item detail response has no photos list") from error
        return tuple(dict.fromkeys(detail.data.photos))

    def _extract_raw_items(self, response_body: object) -> list[object]:
        raw_items = response_body.get("items") if isinstance(response_body, dict) else None
        if not isinstance(raw_items, list):
            raise MercariResponseShapeError("search response has no items list")
        return raw_items

    def _map_item_or_skip(self, raw_item: object) -> Listing | None:
        try:
            return self._map_item(_UpstreamItem.model_validate(raw_item))
        except (ValueError, OverflowError, OSError) as error:
            logger.warning(
                "mercari_item_skipped",
                item_id=raw_item.get("id") if isinstance(raw_item, dict) else None,
                error_type=type(error).__name__,
            )
            return None

    def _map_item(self, item: _UpstreamItem) -> Listing:
        is_shops = item.item_type == SHOPS_ITEM_TYPE
        url_template = (
            SHOPS_PRODUCT_PAGE_URL_TEMPLATE if is_shops else MERCARI_ITEM_PAGE_URL_TEMPLATE
        )
        return Listing(
            item_id=ItemId(item.id),
            kind=ListingKind.SHOPS if is_shops else ListingKind.MERCARI,
            title=item.name,
            price=JpyAmount(item.price),
            url=url_template.format(item_id=item.id),
            image_urls=tuple(item.thumbnails),
            created_at=datetime.fromtimestamp(item.created, tz=UTC),
        )
