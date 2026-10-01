import json
from collections.abc import Sequence
from datetime import datetime

from mercari_alert_bot.domain.models.listing import ItemId, Listing, ListingKind
from mercari_alert_bot.domain.models.listing_history import ListingHistoryEntry
from mercari_alert_bot.domain.models.money import JpyAmount
from mercari_alert_bot.infrastructure.persistence.database import SqliteDatabase

COUNT_LISTINGS = "SELECT count(*) FROM listings"

SELECT_LATEST_NOTIFIED_AT = "SELECT max(notified_at) FROM listings"

SELECT_RECENT_LISTINGS = """
SELECT
    l.item_id,
    l.kind,
    l.title,
    l.price_jpy,
    l.url,
    l.image_urls,
    l.listed_at,
    l.first_seen_at,
    l.notified_at,
    json_group_array(k.name) FILTER (WHERE k.name IS NOT NULL)
FROM listings AS l
LEFT JOIN listing_rule_matches AS m ON m.item_id = l.item_id
LEFT JOIN keyword_rules AS k ON k.rule_id = m.rule_id
GROUP BY l.item_id
ORDER BY l.first_seen_at DESC, l.item_id
LIMIT ?
"""


class SqliteListingHistoryReader:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    async def count_known_listings(self) -> int:
        async with self._database.connection.execute(COUNT_LISTINGS) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        return int(row[0])

    async def find_latest_notified_at(self) -> datetime | None:
        async with self._database.connection.execute(SELECT_LATEST_NOTIFIED_AT) as cursor:
            row = await cursor.fetchone()
        assert row is not None
        return None if row[0] is None else datetime.fromisoformat(row[0])

    async def list_recent_listings(self, limit: int) -> Sequence[ListingHistoryEntry]:
        async with self._database.connection.execute(SELECT_RECENT_LISTINGS, (limit,)) as cursor:
            rows = await cursor.fetchall()
        return [_build_history_entry(tuple(row)) for row in rows]


def _build_history_entry(row: tuple[object, ...]) -> ListingHistoryEntry:
    (
        item_id,
        kind,
        title,
        price_jpy,
        url,
        image_urls,
        listed_at,
        first_seen_at,
        notified_at,
        matched_rule_names,
    ) = row
    listing = Listing(
        item_id=ItemId(str(item_id)),
        kind=ListingKind(str(kind)),
        title=str(title),
        price=JpyAmount(int(str(price_jpy))),
        url=str(url),
        image_urls=tuple(json.loads(str(image_urls))),
        created_at=datetime.fromisoformat(str(listed_at)),
    )
    return ListingHistoryEntry(
        listing=listing,
        matched_rule_names=tuple(sorted(json.loads(str(matched_rule_names)))),
        first_seen_at=datetime.fromisoformat(str(first_seen_at)),
        notified_at=None if notified_at is None else datetime.fromisoformat(str(notified_at)),
    )
