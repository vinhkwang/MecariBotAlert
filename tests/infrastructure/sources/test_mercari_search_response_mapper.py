import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from structlog.testing import capture_logs

from mercari_alert_bot.domain.errors import ListingSourceError
from mercari_alert_bot.domain.models.listing import ListingKind
from mercari_alert_bot.domain.models.money import JpyAmount
from mercari_alert_bot.infrastructure.sources.mercari_search_response_mapper import (
    MercariResponseShapeError,
    MercariSearchResponseMapper,
)

FIXTURES_DIRECTORY = Path(__file__).parent / "fixtures"
MERCARI_ITEM_ID = "m22267384686"
SHOPS_ITEM_ID = "2JXPhdcpwLqC5DyeyDpeyy"


def load_fixture(file_name: str) -> Any:
    return json.loads((FIXTURES_DIRECTORY / file_name).read_text())


def build_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "id": "m1",
        "name": "watch",
        "price": "1000",
        "created": "1714467591",
        "itemType": "ITEM_TYPE_MERCARI",
        "thumbnails": ["https://example.test/1.jpg"],
    }
    item.update(overrides)
    return item


@pytest.fixture
def mapper() -> MercariSearchResponseMapper:
    return MercariSearchResponseMapper()


def test_maps_every_item_of_the_real_search_fixture(mapper: MercariSearchResponseMapper) -> None:
    search_response = load_fixture("mercari_search_response.json")

    listings = mapper.map_search_response(search_response)

    assert len(listings) == 6
    assert [listing.item_id for listing in listings] == [
        item["id"] for item in search_response["items"]
    ]


def test_maps_mercari_item_fields(mapper: MercariSearchResponseMapper) -> None:
    listings = mapper.map_search_response(load_fixture("mercari_search_response.json"))

    listing = next(listing for listing in listings if listing.item_id == MERCARI_ITEM_ID)

    assert listing.title == "OMEGA オメガ 168.0055 コンステレーション 時計 自動巻き"
    assert listing.price == JpyAmount(100000)
    assert listing.created_at == datetime(2024, 4, 30, 8, 59, 51, tzinfo=UTC)
    assert listing.created_at.utcoffset() is not None
    assert listing.kind == ListingKind.MERCARI
    assert listing.url == f"https://jp.mercari.com/item/{MERCARI_ITEM_ID}"
    assert listing.image_urls == (
        "https://static.mercdn.net/thumb/item/webp/m22267384686_1.jpg?1714467591",
    )


def test_maps_shops_item_to_shops_product_url(mapper: MercariSearchResponseMapper) -> None:
    listings = mapper.map_search_response(load_fixture("mercari_search_response.json"))

    listing = next(listing for listing in listings if listing.item_id == SHOPS_ITEM_ID)

    assert listing.kind == ListingKind.SHOPS
    assert listing.url == f"https://jp.mercari.com/shops/product/{SHOPS_ITEM_ID}"


@pytest.mark.parametrize(
    ("price", "created"),
    [("100000", "1714467591"), (100000, 1714467591)],
)
def test_accepts_numeric_price_and_created_as_int_or_string(
    mapper: MercariSearchResponseMapper, price: object, created: object
) -> None:
    [listing] = mapper.map_search_response({"items": [build_item(price=price, created=created)]})

    assert listing.price == JpyAmount(100000)
    assert listing.created_at == datetime(2024, 4, 30, 8, 59, 51, tzinfo=UTC)


def test_unknown_item_type_falls_back_to_mercari_item_url(
    mapper: MercariSearchResponseMapper,
) -> None:
    [listing] = mapper.map_search_response(
        {"items": [build_item(itemType="ITEM_TYPE_SOMETHING_NEW")]}
    )

    assert listing.kind == ListingKind.MERCARI
    assert listing.url == "https://jp.mercari.com/item/m1"


def test_empty_items_list_returns_no_listings(mapper: MercariSearchResponseMapper) -> None:
    assert mapper.map_search_response({"items": []}) == []


@pytest.mark.parametrize("response_body", [{}, [], {"items": None}, "<html>"])
def test_missing_items_key_raises_shape_error(
    mapper: MercariSearchResponseMapper, response_body: object
) -> None:
    with pytest.raises(MercariResponseShapeError):
        mapper.map_search_response(response_body)


@pytest.mark.parametrize(
    "malformed_item",
    [
        {key: value for key, value in build_item(id="bad").items() if key != "name"},
        build_item(id="bad", price="abc"),
        build_item(id="bad", price="-1"),
        build_item(id="  "),
    ],
)
def test_malformed_item_is_skipped_and_others_kept(
    mapper: MercariSearchResponseMapper, malformed_item: dict[str, object]
) -> None:
    good_item = build_item(id="m-good")

    with capture_logs() as captured_logs:
        listings = mapper.map_search_response({"items": [malformed_item, good_item]})

    assert [listing.item_id for listing in listings] == ["m-good"]
    skipped_events = [log for log in captured_logs if log["event"] == "mercari_item_skipped"]
    assert len(skipped_events) == 1
    assert skipped_events[0]["item_id"] == malformed_item["id"]
    assert skipped_events[0]["error_type"]


def test_page_with_only_malformed_items_raises_shape_error(
    mapper: MercariSearchResponseMapper,
) -> None:
    with pytest.raises(MercariResponseShapeError):
        mapper.map_search_response({"items": [build_item(price="abc"), "not-an-item"]})


def test_shape_error_is_a_listing_source_error() -> None:
    assert issubclass(MercariResponseShapeError, ListingSourceError)


def test_detail_photo_urls_are_distinct_in_first_seen_order(
    mapper: MercariSearchResponseMapper,
) -> None:
    detail_response = load_fixture("mercari_item_detail_response.json")

    photo_urls = mapper.map_item_detail_photo_urls(detail_response)

    assert len(detail_response["data"]["photos"]) == 5
    assert photo_urls == tuple(dict.fromkeys(detail_response["data"]["photos"]))
    assert len(photo_urls) == 4


@pytest.mark.parametrize("response_body", [{}, {"data": {}}, {"data": {"photos": "x"}}])
def test_detail_without_photos_raises_shape_error(
    mapper: MercariSearchResponseMapper, response_body: object
) -> None:
    with pytest.raises(MercariResponseShapeError):
        mapper.map_item_detail_photo_urls(response_body)


def test_extra_upstream_fields_are_ignored(mapper: MercariSearchResponseMapper) -> None:
    [listing] = mapper.map_search_response(
        {"items": [build_item(sellerId="1", futureField={"a": 1})]}
    )

    assert listing.item_id == "m1"
