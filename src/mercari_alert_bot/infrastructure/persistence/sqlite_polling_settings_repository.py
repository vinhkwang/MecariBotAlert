from mercari_alert_bot.domain.models.polling_settings import PollingSettings
from mercari_alert_bot.infrastructure.persistence.database import SqliteDatabase
from mercari_alert_bot.shared.clock import Clock

SELECT_POLLING_SETTINGS = (
    "SELECT polling_gap_seconds, is_item_detail_fetch_enabled, max_images_per_alert, "
    "consecutive_failure_alert_threshold, system_alert_cooldown_seconds "
    "FROM polling_settings WHERE singleton_id = 1"
)

UPSERT_POLLING_SETTINGS = (
    "INSERT INTO polling_settings "
    "(singleton_id, polling_gap_seconds, is_item_detail_fetch_enabled, max_images_per_alert, "
    "consecutive_failure_alert_threshold, system_alert_cooldown_seconds, updated_at) "
    "VALUES (1, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT (singleton_id) DO UPDATE SET "
    "polling_gap_seconds = excluded.polling_gap_seconds, "
    "is_item_detail_fetch_enabled = excluded.is_item_detail_fetch_enabled, "
    "max_images_per_alert = excluded.max_images_per_alert, "
    "consecutive_failure_alert_threshold = excluded.consecutive_failure_alert_threshold, "
    "system_alert_cooldown_seconds = excluded.system_alert_cooldown_seconds, "
    "updated_at = excluded.updated_at"
)


class SqlitePollingSettingsRepository:
    def __init__(self, database: SqliteDatabase, clock: Clock) -> None:
        self._database = database
        self._clock = clock

    async def load_polling_settings(self) -> PollingSettings | None:
        async with self._database.connection.execute(SELECT_POLLING_SETTINGS) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return PollingSettings(
            polling_gap_seconds=int(row[0]),
            is_item_detail_fetch_enabled=bool(row[1]),
            max_images_per_alert=int(row[2]),
            consecutive_failure_alert_threshold=int(row[3]),
            system_alert_cooldown_seconds=int(row[4]),
        )

    async def save_polling_settings(self, polling_settings: PollingSettings) -> None:
        async with self._database.transaction() as connection:
            await connection.execute(
                UPSERT_POLLING_SETTINGS,
                (
                    polling_settings.polling_gap_seconds,
                    int(polling_settings.is_item_detail_fetch_enabled),
                    polling_settings.max_images_per_alert,
                    polling_settings.consecutive_failure_alert_threshold,
                    polling_settings.system_alert_cooldown_seconds,
                    self._clock.now().isoformat(),
                ),
            )
