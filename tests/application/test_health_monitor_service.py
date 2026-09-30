from datetime import UTC, datetime, timedelta

import pytest
import structlog

from mercari_alert_bot.application.services.health_monitor_service import (
    HealthMonitorService,
    RuleScanOutcome,
)
from mercari_alert_bot.domain.models.keyword_rule import KeywordRuleId
from tests.fakes.recording_notifier import RecordingNotifier
from tests.shared.fakes import FrozenClock

START = datetime(2026, 9, 30, 10, 0, tzinfo=UTC)
COOLDOWN = timedelta(minutes=30)
THRESHOLD = 3


def succeeded(rule_id: int, listing_count: int = 5) -> RuleScanOutcome:
    return RuleScanOutcome(
        rule_id=KeywordRuleId(rule_id),
        rule_name=f"rule {rule_id}",
        listing_count=listing_count,
        has_failed=False,
    )


def failed(rule_id: int) -> RuleScanOutcome:
    return RuleScanOutcome(
        rule_id=KeywordRuleId(rule_id),
        rule_name=f"rule {rule_id}",
        listing_count=0,
        has_failed=True,
    )


class Harness:
    def __init__(self) -> None:
        self.notifier = RecordingNotifier()
        self.clock = FrozenClock(START)
        self.service = HealthMonitorService(
            self.notifier,
            self.clock,
            consecutive_failure_threshold=THRESHOLD,
            alert_cooldown=COOLDOWN,
        )


async def test_alerts_when_every_succeeded_rule_returns_zero_listings() -> None:
    harness = Harness()

    await harness.service.assess_scan_cycle([succeeded(1, 0), succeeded(2, 0)])

    assert len(harness.notifier.system_alerts) == 1


async def test_stays_silent_when_any_rule_returns_listings() -> None:
    harness = Harness()

    await harness.service.assess_scan_cycle([succeeded(1, 0), succeeded(2, 3)])

    assert harness.notifier.system_alerts == []


async def test_stays_silent_when_no_rules_were_scanned() -> None:
    harness = Harness()

    await harness.service.assess_scan_cycle([])

    assert harness.notifier.system_alerts == []


async def test_does_not_raise_zero_result_alarm_when_every_rule_failed() -> None:
    harness = Harness()

    await harness.service.assess_scan_cycle([failed(1), failed(2)])

    assert harness.notifier.system_alerts == []


async def test_alerts_when_rule_failure_streak_reaches_threshold() -> None:
    harness = Harness()

    await harness.service.assess_scan_cycle([failed(1)])
    await harness.service.assess_scan_cycle([failed(1)])
    assert harness.notifier.system_alerts == []
    await harness.service.assess_scan_cycle([failed(1)])

    assert len(harness.notifier.system_alerts) == 1
    assert "rule 1" in harness.notifier.system_alerts[0]


async def test_success_resets_rule_failure_streak() -> None:
    harness = Harness()

    for outcome in [failed(1), failed(1), succeeded(1), failed(1), failed(1)]:
        await harness.service.assess_scan_cycle([outcome])

    assert harness.notifier.system_alerts == []


async def test_counts_failure_streak_per_rule() -> None:
    harness = Harness()

    await harness.service.assess_scan_cycle([failed(1), succeeded(2)])
    await harness.service.assess_scan_cycle([failed(1), failed(2)])
    await harness.service.assess_scan_cycle([failed(1), succeeded(2)])

    assert len(harness.notifier.system_alerts) == 1
    assert "rule 1" in harness.notifier.system_alerts[0]


async def test_suppresses_repeat_alert_within_cooldown() -> None:
    harness = Harness()

    for _ in range(THRESHOLD + 2):
        await harness.service.assess_scan_cycle([failed(1)])
        harness.clock.advance(timedelta(minutes=1))

    assert len(harness.notifier.system_alerts) == 1


async def test_repeats_alert_after_cooldown_elapses() -> None:
    harness = Harness()
    for _ in range(THRESHOLD):
        await harness.service.assess_scan_cycle([failed(1)])

    harness.clock.advance(COOLDOWN)
    await harness.service.assess_scan_cycle([failed(1)])

    assert len(harness.notifier.system_alerts) == 2


async def test_cooldown_of_one_alert_key_does_not_block_another() -> None:
    harness = Harness()
    await harness.service.assess_scan_cycle([succeeded(1, 0)])
    await harness.service.assess_scan_cycle([failed(2)])
    await harness.service.assess_scan_cycle([failed(2)])
    harness.clock.advance(timedelta(minutes=1))

    await harness.service.assess_scan_cycle([failed(2)])

    assert len(harness.notifier.system_alerts) == 2


async def test_swallows_delivery_failure_and_retries_next_cycle() -> None:
    harness = Harness()
    harness.notifier.is_failing = True

    await harness.service.assess_scan_cycle([succeeded(1, 0)])
    assert harness.notifier.system_alerts == []
    harness.notifier.is_failing = False
    await harness.service.assess_scan_cycle([succeeded(1, 0)])

    assert len(harness.notifier.system_alerts) == 1


async def test_logs_system_alert_delivery_failure() -> None:
    harness = Harness()
    harness.notifier.is_failing = True

    with structlog.testing.capture_logs() as captured_logs:
        await harness.service.assess_scan_cycle([succeeded(1, 0)])

    assert [entry["event"] for entry in captured_logs] == ["system_alert_delivery_failed"]
    assert captured_logs[0]["alert_key"] == "zero_results"


async def test_combines_every_failing_rule_into_one_alert() -> None:
    harness = Harness()
    cycle = [failed(1), failed(2), failed(3)]

    for _ in range(THRESHOLD):
        await harness.service.assess_scan_cycle(cycle)

    assert len(harness.notifier.system_alerts) == 1
    for rule_name in ("rule 1", "rule 2", "rule 3"):
        assert rule_name in harness.notifier.system_alerts[0]


async def test_full_outage_sends_one_failure_alert_per_cooldown_window() -> None:
    harness = Harness()

    for _ in range(10):
        await harness.service.assess_scan_cycle([failed(1), failed(2), failed(3)])
        harness.clock.advance(timedelta(minutes=1))

    assert len(harness.notifier.system_alerts) == 1


async def test_combined_alert_omits_rules_still_cooling_down() -> None:
    harness = Harness()
    for _ in range(THRESHOLD):
        await harness.service.assess_scan_cycle([failed(1), succeeded(2)])
    harness.clock.advance(timedelta(minutes=1))
    await harness.service.assess_scan_cycle([failed(1), failed(2)])
    await harness.service.assess_scan_cycle([failed(1), failed(2)])

    await harness.service.assess_scan_cycle([failed(1), failed(2)])

    assert len(harness.notifier.system_alerts) == 2
    assert "rule 2" in harness.notifier.system_alerts[1]
    assert "rule 1" not in harness.notifier.system_alerts[1]


async def test_retries_every_listed_rule_after_combined_delivery_failure() -> None:
    harness = Harness()
    harness.notifier.is_failing = True
    for _ in range(THRESHOLD):
        await harness.service.assess_scan_cycle([failed(1), failed(2)])
    assert harness.notifier.system_alerts == []
    harness.notifier.is_failing = False

    await harness.service.assess_scan_cycle([failed(1), failed(2)])

    assert len(harness.notifier.system_alerts) == 1
    assert "rule 1" in harness.notifier.system_alerts[0]
    assert "rule 2" in harness.notifier.system_alerts[0]


async def test_logs_rule_names_for_combined_failure_alert() -> None:
    harness = Harness()
    for _ in range(THRESHOLD - 1):
        await harness.service.assess_scan_cycle([failed(1), failed(2)])

    with structlog.testing.capture_logs() as captured_logs:
        await harness.service.assess_scan_cycle([failed(1), failed(2)])

    assert [entry["event"] for entry in captured_logs] == ["system_alert_sent"]
    assert captured_logs[0]["alert_key"] == "rule_failure"
    assert captured_logs[0]["rule_names"] == ["rule 1", "rule 2"]


async def test_forgets_streak_of_rule_absent_from_cycle() -> None:
    harness = Harness()

    await harness.service.assess_scan_cycle([failed(1)])
    await harness.service.assess_scan_cycle([failed(1)])
    await harness.service.assess_scan_cycle([succeeded(2)])
    await harness.service.assess_scan_cycle([failed(1)])

    assert harness.notifier.system_alerts == []


def test_rejects_threshold_below_one() -> None:
    with pytest.raises(ValueError, match="consecutive_failure_threshold"):
        HealthMonitorService(
            RecordingNotifier(),
            FrozenClock(START),
            consecutive_failure_threshold=0,
            alert_cooldown=COOLDOWN,
        )


def test_rejects_negative_cooldown() -> None:
    with pytest.raises(ValueError, match="alert_cooldown"):
        HealthMonitorService(
            RecordingNotifier(),
            FrozenClock(START),
            consecutive_failure_threshold=THRESHOLD,
            alert_cooldown=timedelta(seconds=-1),
        )
