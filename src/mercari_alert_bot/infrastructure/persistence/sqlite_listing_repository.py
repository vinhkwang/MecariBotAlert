import json
from collections.abc import Collection, Sequence
from datetime import UTC, datetime

from mercari_alert_bot.domain.errors import InvalidDomainValueError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRuleId
from mercari_alert_bot.domain.models.listing import ItemId, Listing
from mercari_alert_bot.infrastructure.persistence.database import SqliteDatabase

SELECT_KNOWN_ITEM_IDS = """
SELECT item_id FROM listings
WHERE item_id IN (SELECT value FROM json_each(?))
"""

INSERT_LISTING = """
INSERT INTO listings
    (item_id, kind, title, price_jpy, url, image_urls, listed_at, first_seen_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (item_id) DO NOTHING
"""

INSERT_RULE_MATCH = """
INSERT INTO listing_rule_matches (item_id, rule_id, matched_at)
VALUES (?, ?, ?)
ON CONFLICT (item_id, rule_id) DO NOTHING
"""

UPDATE_NOTIFIED_AT = """
UPDATE listings SET notified_at = COALESCE(notified_at, ?)
WHERE item_id = ?
"""


class UnknownListingError(LookupError):
    pass


def format_utc_timestamp(moment: datetime, field_name: str) -> str:
    if moment.utcoffset() is None:
        raise InvalidDomainValueError(f"{field_name} must be timezone-aware")
    return moment.astimezone(UTC).isoformat()


class SqliteListingRepository:
    def __init__(self, database: SqliteDatabase) -> None:
        self._database = database

    async def find_known_item_ids(self, item_ids: Collection[ItemId]) -> frozenset[ItemId]:
        if not item_ids:
            return frozenset()
        async with self._database.connection.execute(
            SELECT_KNOWN_ITEM_IDS, (json.dumps(list(item_ids)),)
        ) as cursor:
            rows = await cursor.fetchall()
        return frozenset(ItemId(row[0]) for row in rows)

    async def remember_listings(
        self,
        listings: Sequence[Listing],
        rule_id: KeywordRuleId,
        seen_at: datetime,
    ) -> None:
        if not listings:
            return
        seen_at_text = format_utc_timestamp(seen_at, "seen_at")
        async with self._database.transaction() as connection:
            for listing in listings:
                await connection.execute(
                    INSERT_LISTING,
                    (
                        listing.item_id,
                        listing.kind.value,
                        listing.title,
                        listing.price.yen,
                        listing.url,
                        json.dumps(listing.image_urls),
                        format_utc_timestamp(listing.created_at, "created_at"),
                        seen_at_text,
                    ),
                )
                await connection.execute(
                    INSERT_RULE_MATCH, (listing.item_id, rule_id, seen_at_text)
                )

    async def mark_listing_notified(self, item_id: ItemId, notified_at: datetime) -> None:
        notified_at_text = format_utc_timestamp(notified_at, "notified_at")
        async with self._database.transaction() as connection:
            cursor = await connection.execute(UPDATE_NOTIFIED_AT, (notified_at_text, item_id))
            if cursor.rowcount == 0:
                raise UnknownListingError(f"listing {item_id} was never remembered")
