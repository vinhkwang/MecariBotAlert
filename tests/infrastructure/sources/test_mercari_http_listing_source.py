import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from itertools import count
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
import pytest_asyncio
import respx
from structlog.testing import capture_logs

from mercari_alert_bot.domain.errors import ListingSourceError
from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.money import JpyAmount
from mercari_alert_bot.domain.ports.listing_source import ListingSource
from mercari_alert_bot.infrastructure.sources.dpop_proof_factory import DpopProofFactory
from mercari_alert_bot.infrastructure.sources.mercari_http_listing_source import (
    BROWSER_USER_AGENT,
    MERCARI_ITEM_DETAIL_URL,
    MERCARI_SEARCH_URL,
    MercariHttpListingSource,
    MercariHttpStatusError,
    MercariNonJsonResponseError,
    MercariTransportError,
)
from mercari_alert_bot.infrastructure.sources.mercari_search_response_mapper import (
    MercariResponseShapeError,
    MercariSearchResponseMapper,
)
from tests.shared.fakes import FrozenClock

FIXTURES_DIRECTORY = Path(__file__).parent / "fixtures"
FROZEN_TIME = datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)
FIXED_SEARCH_SESSION_ID = "fixed-session-id"
MERCARI_ITEM_ID = "m22267384686"
SHOPS_ITEM_ID = "2JXPhdcpwLqC5DyeyDpeyy"
THUMBNAIL_URL = "https://static.mercdn.net/thumb/photos/thumbnail.jpg"
HTML_MARKER = "captcha-body-marker"
JSON_HEADERS = {"content-type": "application/json"}


def load_fixture(file_name: str) -> Any:
    return json.loads((FIXTURES_DIRECTORY / file_name).read_text())


def build_listing(item_id: str, kind: ListingKind) -> Listing:
    return Listing(
        item_id=ItemId(item_id),
        kind=kind,
        title="title",
        price=JpyAmount(1000),
        url=f"https://jp.mercari.com/item/{item_id}",
        image_urls=(THUMBNAIL_URL,),
        created_at=FROZEN_TIME,
    )


def build_source(
    http_client: httpx.AsyncClient,
    dpop_proof_factory: DpopProofFactory,
    **overrides: Any,
) -> MercariHttpListingSource:
    return MercariHttpListingSource(
        http_client,
        dpop_proof_factory,
        MercariSearchResponseMapper(),
        generate_search_session_id=lambda: FIXED_SEARCH_SESSION_ID,
        **overrides,
    )


def read_proof_claims(proof: str) -> dict[str, Any]:
    return dict(jwt.decode(proof, options={"verify_signature": False}))


@pytest.fixture
def dpop_proof_factory() -> DpopProofFactory:
    unique_ids = count()
    return DpopProofFactory(
        FrozenClock(FROZEN_TIME),
        generate_unique_id=lambda: f"unique-{next(unique_ids)}",
    )


@pytest_asyncio.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def source(
    http_client: httpx.AsyncClient, dpop_proof_factory: DpopProofFactory
) -> MercariHttpListingSource:
    return build_source(http_client, dpop_proof_factory)


@pytest.mark.asyncio
async def test_search_posts_expected_body_to_search_url(
    source: MercariHttpListingSource,
) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.post(MERCARI_SEARCH_URL).respond(
            200, json=load_fixture("mercari_search_response.json")
        )
        await source.fetch_latest_listings("OMEGA 168.005")

    body = json.loads(route.calls.last.request.content)
    assert body["pageSize"] == 30
    assert body["searchSessionId"] == FIXED_SEARCH_SESSION_ID
    assert body["searchCondition"] == {
        "keyword": "OMEGA 168.005",
        "excludeKeyword": "",
        "sort": "SORT_CREATED_TIME",
        "order": "ORDER_DESC",
        "status": ["STATUS_ON_SALE"],
    }
    assert body["defaultDatasets"] == ["DATASET_TYPE_MERCARI", "DATASET_TYPE_BEYOND"]
    assert body["withShopname"] is False


@pytest.mark.asyncio
async def test_search_sends_browser_shaped_headers(source: MercariHttpListingSource) -> None:
    with respx.mock() as router:
        route = router.post(MERCARI_SEARCH_URL).respond(
            200, json=load_fixture("mercari_search_response.json")
        )
        await source.fetch_latest_listings("OMEGA")

    headers = route.calls.last.request.headers
    assert headers["X-Platform"] == "web"
    assert headers["User-Agent"] == BROWSER_USER_AGENT
    assert headers["Accept"] == "application/json"
    assert headers["DPoP"]


@pytest.mark.asyncio
async def test_search_dpop_proof_binds_post_and_search_url(
    source: MercariHttpListingSource,
) -> None:
    with respx.mock() as router:
        route = router.post(MERCARI_SEARCH_URL).respond(
            200, json=load_fixture("mercari_search_response.json")
        )
        await source.fetch_latest_listings("OMEGA")

    claims = read_proof_claims(route.calls.last.request.headers["DPoP"])
    assert claims["htm"] == "POST"
    assert claims["htu"] == MERCARI_SEARCH_URL


@pytest.mark.asyncio
async def test_search_maps_fixture_into_listings(source: MercariHttpListingSource) -> None:
    fixture = load_fixture("mercari_search_response.json")

    with respx.mock() as router:
        router.post(MERCARI_SEARCH_URL).respond(200, json=fixture)
        listings = await source.fetch_latest_listings("OMEGA")

    assert [listing.item_id for listing in listings] == [item["id"] for item in fixture["items"]]
    assert len(listings) == 6


@pytest.mark.asyncio
async def test_search_uses_configured_page_size(
    http_client: httpx.AsyncClient, dpop_proof_factory: DpopProofFactory
) -> None:
    source = build_source(http_client, dpop_proof_factory, search_page_size=50)

    with respx.mock() as router:
        route = router.post(MERCARI_SEARCH_URL).respond(
            200, json=load_fixture("mercari_search_response.json")
        )
        await source.fetch_latest_listings("OMEGA")

    assert json.loads(route.calls.last.request.content)["pageSize"] == 50


@pytest.mark.parametrize("invalid_page_size", [0, 121])
@pytest.mark.asyncio
async def test_invalid_page_size_is_rejected(
    http_client: httpx.AsyncClient,
    dpop_proof_factory: DpopProofFactory,
    invalid_page_size: int,
) -> None:
    with pytest.raises(ValueError, match="search_page_size"):
        build_source(http_client, dpop_proof_factory, search_page_size=invalid_page_size)


@pytest.mark.asyncio
async def test_each_search_gets_a_fresh_dpop_proof(source: MercariHttpListingSource) -> None:
    with respx.mock() as router:
        route = router.post(MERCARI_SEARCH_URL).respond(
            200, json=load_fixture("mercari_search_response.json")
        )
        await source.fetch_latest_listings("OMEGA")
        await source.fetch_latest_listings("OMEGA")

    proof_identifiers = {
        read_proof_claims(call.request.headers["DPoP"])["jti"] for call in route.calls
    }
    assert len(proof_identifiers) == 2


@pytest.mark.asyncio
async def test_mercari_item_images_come_from_detail_endpoint(
    source: MercariHttpListingSource,
) -> None:
    fixture = load_fixture("mercari_item_detail_response.json")

    with respx.mock() as router:
        route = router.get(MERCARI_ITEM_DETAIL_URL, params={"id": MERCARI_ITEM_ID}).respond(
            200, json=fixture
        )
        image_urls = await source.fetch_listing_image_urls(
            build_listing(MERCARI_ITEM_ID, ListingKind.MERCARI)
        )

    assert image_urls == tuple(dict.fromkeys(fixture["data"]["photos"]))
    claims = read_proof_claims(route.calls.last.request.headers["DPoP"])
    assert claims["htm"] == "GET"
    assert claims["htu"] == MERCARI_ITEM_DETAIL_URL


@pytest.mark.asyncio
async def test_shops_item_images_use_search_thumbnail_without_request(
    source: MercariHttpListingSource,
) -> None:
    with respx.mock(assert_all_called=False) as router:
        detail_route = router.get(MERCARI_ITEM_DETAIL_URL).respond(200, json={})
        image_urls = await source.fetch_listing_image_urls(
            build_listing(SHOPS_ITEM_ID, ListingKind.SHOPS)
        )

    assert image_urls == (THUMBNAIL_URL,)
    assert not detail_route.called


@pytest.mark.asyncio
async def test_mercari_item_with_empty_detail_photos_falls_back_to_thumbnail(
    source: MercariHttpListingSource,
) -> None:
    with respx.mock() as router:
        router.get(MERCARI_ITEM_DETAIL_URL).respond(200, json={"data": {"photos": []}})
        image_urls = await source.fetch_listing_image_urls(
            build_listing(MERCARI_ITEM_ID, ListingKind.MERCARI)
        )

    assert image_urls == (THUMBNAIL_URL,)


async def run_operation(source: MercariHttpListingSource, operation: str) -> object:
    if operation == "search":
        return await source.fetch_latest_listings("OMEGA")
    return await source.fetch_listing_image_urls(
        build_listing(MERCARI_ITEM_ID, ListingKind.MERCARI)
    )


def mock_operation_route(router: respx.MockRouter, operation: str) -> respx.Route:
    if operation == "search":
        return router.post(MERCARI_SEARCH_URL)
    return router.get(MERCARI_ITEM_DETAIL_URL)


OPERATIONS = ["search", "item_detail"]


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("status_code", [403, 429, 500, 503])
@pytest.mark.asyncio
async def test_non_ok_status_raises_http_status_error(
    source: MercariHttpListingSource, operation: str, status_code: int
) -> None:
    with respx.mock() as router:
        mock_operation_route(router, operation).respond(status_code)
        with pytest.raises(MercariHttpStatusError) as raised:
            await run_operation(source, operation)

    assert raised.value.status_code == status_code
    assert raised.value.operation == operation


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize(
    "transport_error",
    [
        httpx.ConnectTimeout("t"),
        httpx.ReadTimeout("t"),
        httpx.ConnectError("t"),
        httpx.DecodingError("t"),
    ],
    ids=lambda error: type(error).__name__,
)
@pytest.mark.asyncio
async def test_transport_failure_raises_transport_error(
    source: MercariHttpListingSource, operation: str, transport_error: httpx.RequestError
) -> None:
    with respx.mock() as router:
        mock_operation_route(router, operation).mock(side_effect=transport_error)
        with pytest.raises(MercariTransportError) as raised:
            await run_operation(source, operation)

    assert raised.value.failure_kind == type(transport_error).__name__
    assert raised.value.operation == operation


@pytest.mark.asyncio
async def test_html_page_raises_non_json_error_flagged_as_html(
    source: MercariHttpListingSource,
) -> None:
    with respx.mock() as router:
        router.post(MERCARI_SEARCH_URL).respond(
            200,
            headers={"content-type": "text/html"},
            text=f"<html>{HTML_MARKER}</html>",
        )
        with pytest.raises(MercariNonJsonResponseError) as raised:
            await source.fetch_latest_listings("OMEGA")

    assert raised.value.is_html_page is True


@pytest.mark.asyncio
async def test_undecodable_json_raises_non_json_error(
    source: MercariHttpListingSource,
) -> None:
    with respx.mock() as router:
        router.post(MERCARI_SEARCH_URL).respond(200, headers=JSON_HEADERS, text="{not json")
        with pytest.raises(MercariNonJsonResponseError) as raised:
            await source.fetch_latest_listings("OMEGA")

    assert raised.value.is_html_page is False


@pytest.mark.asyncio
async def test_shape_error_from_mapper_propagates(source: MercariHttpListingSource) -> None:
    with respx.mock() as router:
        router.post(MERCARI_SEARCH_URL).respond(200, json={})
        with pytest.raises(MercariResponseShapeError):
            await source.fetch_latest_listings("OMEGA")


@pytest.mark.parametrize(
    "error",
    [
        MercariHttpStatusError("search", 403),
        MercariTransportError("search", "ConnectError"),
        MercariNonJsonResponseError("search", is_html_page=True),
    ],
    ids=lambda error: type(error).__name__,
)
def test_every_raised_error_is_a_listing_source_error(error: Exception) -> None:
    assert isinstance(error, ListingSourceError)


@pytest.mark.asyncio
async def test_each_request_logs_status_and_duration(source: MercariHttpListingSource) -> None:
    with respx.mock() as router:
        router.post(MERCARI_SEARCH_URL).respond(
            200, json=load_fixture("mercari_search_response.json")
        )
        with capture_logs() as captured_logs:
            await source.fetch_latest_listings("OMEGA")

    request_events = [log for log in captured_logs if log["event"] == "mercari_request"]
    assert len(request_events) == 1
    assert request_events[0]["operation"] == "search"
    assert request_events[0]["status_code"] == 200
    assert request_events[0]["duration_ms"] >= 0


@pytest.mark.asyncio
async def test_logs_and_errors_never_contain_response_body_or_dpop_proof(
    source: MercariHttpListingSource,
) -> None:
    with respx.mock() as router:
        route = router.post(MERCARI_SEARCH_URL).respond(
            200,
            headers={"content-type": "text/html"},
            text=f"<html>{HTML_MARKER}</html>",
        )
        with capture_logs() as captured_logs, pytest.raises(MercariNonJsonResponseError) as raised:
            await source.fetch_latest_listings("OMEGA")

    proof = route.calls.last.request.headers["DPoP"]
    rendered_output = f"{captured_logs} {raised.value}"
    assert HTML_MARKER not in rendered_output
    assert proof not in rendered_output


@pytest.mark.asyncio
async def test_source_satisfies_listing_source_port(
    source: MercariHttpListingSource,
) -> None:
    port: ListingSource = source

    with respx.mock() as router:
        router.post(MERCARI_SEARCH_URL).respond(
            200, json=load_fixture("mercari_search_response.json")
        )
        router.get(MERCARI_ITEM_DETAIL_URL).respond(
            200, json=load_fixture("mercari_item_detail_response.json")
        )
        listings = await port.fetch_latest_listings("OMEGA")
        image_urls = await port.fetch_listing_image_urls(
            build_listing(MERCARI_ITEM_ID, ListingKind.MERCARI)
        )

    assert listings
    assert image_urls
