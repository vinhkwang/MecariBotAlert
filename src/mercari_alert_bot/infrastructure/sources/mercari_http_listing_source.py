import time
import uuid
from collections.abc import Callable, Sequence
from http import HTTPStatus
from typing import Final

import httpx
import structlog

from mercari_alert_bot.domain.errors import ListingSourceError
from mercari_alert_bot.domain.models.listing import Listing, ListingKind
from mercari_alert_bot.infrastructure.sources.dpop_proof_factory import (
    DPOP_HEADER_NAME,
    DpopProofFactory,
)
from mercari_alert_bot.infrastructure.sources.mercari_search_response_mapper import (
    MercariSearchResponseMapper,
)

MERCARI_SEARCH_URL: Final = "https://api.mercari.jp/v2/entities:search"
MERCARI_ITEM_DETAIL_URL: Final = "https://api.mercari.jp/items/get"
DEFAULT_SEARCH_PAGE_SIZE: Final = 30
MIN_SEARCH_PAGE_SIZE: Final = 1
MAX_SEARCH_PAGE_SIZE: Final = 120
MILLISECONDS_PER_SECOND: Final = 1000
SEARCH_OPERATION: Final = "search"
ITEM_DETAIL_OPERATION: Final = "item_detail"
BROWSER_USER_AGENT: Final = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

logger = structlog.get_logger()


class MercariHttpStatusError(ListingSourceError):
    def __init__(self, operation: str, status_code: int) -> None:
        super().__init__(f"mercari {operation} failed with status {status_code}")
        self.operation = operation
        self.status_code = status_code


class MercariTransportError(ListingSourceError):
    def __init__(self, operation: str, failure_kind: str) -> None:
        super().__init__(f"mercari {operation} transport failure: {failure_kind}")
        self.operation = operation
        self.failure_kind = failure_kind


class MercariNonJsonResponseError(ListingSourceError):
    def __init__(self, operation: str, is_html_page: bool) -> None:
        super().__init__(f"mercari {operation} returned a non-json response")
        self.operation = operation
        self.is_html_page = is_html_page


def generate_uuid4_hex() -> str:
    return uuid.uuid4().hex


class MercariHttpListingSource:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        dpop_proof_factory: DpopProofFactory,
        response_mapper: MercariSearchResponseMapper,
        search_page_size: int = DEFAULT_SEARCH_PAGE_SIZE,
        generate_search_session_id: Callable[[], str] = generate_uuid4_hex,
    ) -> None:
        if not MIN_SEARCH_PAGE_SIZE <= search_page_size <= MAX_SEARCH_PAGE_SIZE:
            raise ValueError(
                f"search_page_size must be within "
                f"[{MIN_SEARCH_PAGE_SIZE}, {MAX_SEARCH_PAGE_SIZE}]: {search_page_size}"
            )
        self._http_client = http_client
        self._dpop_proof_factory = dpop_proof_factory
        self._response_mapper = response_mapper
        self._search_page_size = search_page_size
        self._generate_search_session_id = generate_search_session_id

    async def fetch_latest_listings(self, query: str) -> Sequence[Listing]:
        request = self._http_client.build_request(
            "POST",
            MERCARI_SEARCH_URL,
            json=self._build_search_body(query),
            headers=self._build_headers("POST", MERCARI_SEARCH_URL),
        )
        response_body = await self._send_for_json(SEARCH_OPERATION, request)
        return self._response_mapper.map_search_response(response_body)

    async def fetch_listing_image_urls(self, listing: Listing) -> tuple[str, ...]:
        if listing.kind is not ListingKind.MERCARI:
            return listing.image_urls
        request = self._http_client.build_request(
            "GET",
            MERCARI_ITEM_DETAIL_URL,
            params={"id": listing.item_id},
            headers=self._build_headers("GET", MERCARI_ITEM_DETAIL_URL),
        )
        response_body = await self._send_for_json(ITEM_DETAIL_OPERATION, request)
        photo_urls = self._response_mapper.map_item_detail_photo_urls(response_body)
        return photo_urls or listing.image_urls

    def _build_headers(self, http_method: str, target_url: str) -> dict[str, str]:
        return {
            DPOP_HEADER_NAME: self._dpop_proof_factory.create_proof(http_method, target_url),
            "X-Platform": "web",
            "User-Agent": BROWSER_USER_AGENT,
            "Accept": "application/json",
        }

    def _build_search_body(self, query: str) -> dict[str, object]:
        return {
            "userId": "",
            "pageSize": self._search_page_size,
            "pageToken": "",
            "searchSessionId": self._generate_search_session_id(),
            "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
            "thumbnailTypes": [],
            "searchCondition": {
                "keyword": query,
                "excludeKeyword": "",
                "sort": "SORT_CREATED_TIME",
                "order": "ORDER_DESC",
                "status": ["STATUS_ON_SALE"],
            },
            "defaultDatasets": ["DATASET_TYPE_MERCARI", "DATASET_TYPE_BEYOND"],
            "serviceFrom": "suruga",
            "withItemBrand": False,
            "withItemSize": False,
            "withItemPromotions": False,
            "withItemSizes": False,
            "withShopname": False,
        }

    async def _send_for_json(self, operation: str, request: httpx.Request) -> object:
        started_at = time.perf_counter()
        try:
            response = await self._http_client.send(request)
        except httpx.RequestError as error:
            failure_kind = type(error).__name__
            self._log_request(operation, started_at, failure_kind=failure_kind)
            raise MercariTransportError(operation, failure_kind) from None
        self._log_request(operation, started_at, status_code=response.status_code)
        if response.status_code != HTTPStatus.OK:
            raise MercariHttpStatusError(operation, response.status_code)
        return _decode_json_body(operation, response)

    def _log_request(
        self,
        operation: str,
        started_at: float,
        **request_outcome: int | str,
    ) -> None:
        logger.info(
            "mercari_request",
            operation=operation,
            **request_outcome,
            duration_ms=round((time.perf_counter() - started_at) * MILLISECONDS_PER_SECOND),
        )


def _decode_json_body(operation: str, response: httpx.Response) -> object:
    if "json" not in response.headers.get("content-type", ""):
        raise MercariNonJsonResponseError(
            operation, is_html_page=response.text.lstrip().startswith("<")
        )
    try:
        decoded: object = response.json()
    except ValueError:
        raise MercariNonJsonResponseError(operation, is_html_page=False) from None
    return decoded
