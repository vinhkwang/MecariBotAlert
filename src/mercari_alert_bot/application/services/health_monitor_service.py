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
_RULE_FAILURE_ALERT_KEY = "rule_failure"


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
        now = self._clock.now()
        if _is_zero_result_cycle(rule_outcomes):
            await self._alert_about_zero_results(now)
        await self._alert_about_failing_rules(rule_outcomes, now)

    async def _alert_about_zero_results(self, now: datetime) -> None:
        if self._is_cooling_down(_ZERO_RESULTS_ALERT_KEY, now):
            return
        is_delivered = await self._deliver_system_alert(
            _ZERO_RESULTS_ALERT_KEY,
            "Every scanned keyword returned zero listings. The Mercari source may be broken.",
        )
        if is_delivered:
            self._last_alert_sent_at_by_key[_ZERO_RESULTS_ALERT_KEY] = now

    async def _alert_about_failing_rules(
        self,
        rule_outcomes: Sequence[RuleScanOutcome],
        now: datetime,
    ) -> None:
        alertable_outcomes = [
            outcome
            for outcome in rule_outcomes
            if self._failure_streak_by_rule_id[outcome.rule_id]
            >= self._consecutive_failure_threshold
            and not self._is_cooling_down(_rule_failure_key(outcome), now)
        ]
        if not alertable_outcomes:
            return
        rule_lines = [
            f"- {outcome.rule_name}: {self._failure_streak_by_rule_id[outcome.rule_id]}"
            " scans in a row"
            for outcome in alertable_outcomes
        ]
        is_delivered = await self._deliver_system_alert(
            _RULE_FAILURE_ALERT_KEY,
            "\n".join(["Keywords failing repeatedly:", *rule_lines]),
            rule_names=[outcome.rule_name for outcome in alertable_outcomes],
        )
        if is_delivered:
            for outcome in alertable_outcomes:
                self._last_alert_sent_at_by_key[_rule_failure_key(outcome)] = now

    def _update_failure_streaks(self, rule_outcomes: Sequence[RuleScanOutcome]) -> None:
        self._failure_streak_by_rule_id = {
            outcome.rule_id: (
                self._failure_streak_by_rule_id.get(outcome.rule_id, 0) + 1
                if outcome.has_failed
                else 0
            )
            for outcome in rule_outcomes
        }

    def _is_cooling_down(self, alert_key: str, now: datetime) -> bool:
        last_sent_at = self._last_alert_sent_at_by_key.get(alert_key)
        return last_sent_at is not None and now - last_sent_at < self._alert_cooldown

    async def _deliver_system_alert(
        self,
        alert_key: str,
        message: str,
        **log_fields: object,
    ) -> bool:
        try:
            await self._notifier.send_system_alert(message)
        except NotificationDeliveryError:
            logger.warning("system_alert_delivery_failed", alert_key=alert_key, **log_fields)
            return False
        logger.info("system_alert_sent", alert_key=alert_key, **log_fields)
        return True


def _rule_failure_key(outcome: RuleScanOutcome) -> str:
    return f"{_RULE_FAILURE_ALERT_KEY}:{outcome.rule_id}"


def _is_zero_result_cycle(rule_outcomes: Sequence[RuleScanOutcome]) -> bool:
    succeeded_outcomes = [outcome for outcome in rule_outcomes if not outcome.has_failed]
    return bool(succeeded_outcomes) and all(
        outcome.listing_count == 0 for outcome in succeeded_outcomes
    )
