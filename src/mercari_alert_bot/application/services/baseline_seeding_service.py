from dataclasses import replace

import structlog

from mercari_alert_bot.domain.models.keyword_rule import KeywordRule
from mercari_alert_bot.domain.ports.keyword_rule_repository import KeywordRuleRepository
from mercari_alert_bot.domain.ports.listing_repository import ListingRepository
from mercari_alert_bot.domain.ports.listing_source import ListingSource
from mercari_alert_bot.shared.clock import Clock

logger = structlog.get_logger(__name__)


class BaselineSeedingService:
    def __init__(
        self,
        listing_source: ListingSource,
        listing_repository: ListingRepository,
        keyword_rule_repository: KeywordRuleRepository,
        clock: Clock,
    ) -> None:
        self._listing_source = listing_source
        self._listing_repository = listing_repository
        self._keyword_rule_repository = keyword_rule_repository
        self._clock = clock

    async def seed_rule_baseline(self, rule: KeywordRule) -> KeywordRule:
        seeded_at = self._clock.now()
        listings = await self._listing_source.fetch_latest_listings(rule.query)
        await self._listing_repository.remember_listings(listings, rule.rule_id, seeded_at)
        current_rule = await self._keyword_rule_repository.get_rule(rule.rule_id)
        if current_rule.query != rule.query:
            return current_rule
        seeded_rule = replace(current_rule, baseline_established_at=seeded_at)
        await self._keyword_rule_repository.save_rule(seeded_rule)
        logger.info(
            "rule_baseline_seeded",
            rule_name=seeded_rule.name,
            seeded_item_count=len(listings),
        )
        return seeded_rule
