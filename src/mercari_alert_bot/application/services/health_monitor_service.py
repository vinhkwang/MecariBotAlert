from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import structlog

from mercari_alert_bot.domain.errors import NotificationDeliveryError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRuleId
from mercari_alert_bot.domain.ports.notifier import Notifier
from mercari_alert_bot.shared.clock import Clock

logger = structlog.get_logger(__name__)

_ZERO_RESULTS_ALERT_KEY = "zero_results"


@dataclass(frozen=True, slots=True, kw_only=True)
class RuleScanOutcome:
    rule_id: KeywordRuleId
    rule_name: str
    listing_count: int
    has_failed: bool


class HealthMonitorService:
    def __init__(
        self,
        notifier: Notifier,
        clock: Clock,
        *,
        consecutive_failure_threshold: int,
        alert_cooldown: timedelta,
    ) -> None:
        if consecutive_failure_threshold < 1:
            raise ValueError("consecutive_failure_threshold must be at least 1")
        if alert_cooldown < timedelta(0):
            raise ValueError("alert_cooldown must not be negative")
        self._notifier = notifier
        self._clock = clock
        self._consecutive_failure_threshold = consecutive_failure_threshold
        self._alert_cooldown = alert_cooldown
        self._failure_streak_by_rule_id: dict[KeywordRuleId, int] = {}
        self._last_alert_sent_at_by_key: dict[str, datetime] = {}

    async def assess_scan_cycle(self, rule_outcomes: Sequence[RuleScanOutcome]) -> None:
        self._update_failure_streaks(rule_outcomes)
        if _is_zero_result_cycle(rule_outcomes):
            await self._send_alert_unless_cooling_down(
                _ZERO_RESULTS_ALERT_KEY,
                "Every scanned keyword returned zero listings. The Mercari source may be broken.",
            )
        for outcome in rule_outcomes:
            failure_streak = self._failure_streak_by_rule_id[outcome.rule_id]
            if failure_streak >= self._consecutive_failure_threshold:
                await self._send_alert_unless_cooling_down(
                    f"rule_failure:{outcome.rule_id}",
                    f"Keyword '{outcome.rule_name}' failed {failure_streak} scans in a row.",
                )

    def _update_failure_streaks(self, rule_outcomes: Sequence[RuleScanOutcome]) -> None:
        self._failure_streak_by_rule_id = {
            outcome.rule_id: (
                self._failure_streak_by_rule_id.get(outcome.rule_id, 0) + 1
                if outcome.has_failed
                else 0
            )
            for outcome in rule_outcomes
        }

    async def _send_alert_unless_cooling_down(self, alert_key: str, message: str) -> None:
        now = self._clock.now()
        last_sent_at = self._last_alert_sent_at_by_key.get(alert_key)
        if last_sent_at is not None and now - last_sent_at < self._alert_cooldown:
            return
        try:
            await self._notifier.send_system_alert(message)
        except NotificationDeliveryError:
            logger.warning("system_alert_delivery_failed", alert_key=alert_key)
            return
        self._last_alert_sent_at_by_key[alert_key] = now
        logger.info("system_alert_sent", alert_key=alert_key)


def _is_zero_result_cycle(rule_outcomes: Sequence[RuleScanOutcome]) -> bool:
    succeeded_outcomes = [outcome for outcome in rule_outcomes if not outcome.has_failed]
    return bool(succeeded_outcomes) and all(
        outcome.listing_count == 0 for outcome in succeeded_outcomes
    )
