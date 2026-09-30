import asyncio
import random

import pytest
import structlog

from mercari_alert_bot.infrastructure.scheduling.interval_scheduler import IntervalScheduler
from mercari_alert_bot.shared.jitter import apply_jitter

LONG_INTERVAL_SECONDS = 3600.0
GUARD_SECONDS = 1.0


class JobProbe:
    def __init__(self, *, stop_after_calls: int | None = None) -> None:
        self.call_count = 0
        self.first_call_started = asyncio.Event()
        self.scheduler: IntervalScheduler | None = None
        self._stop_after_calls = stop_after_calls

    async def __call__(self) -> None:
        self.call_count += 1
        self.first_call_started.set()
        if self._stop_after_calls == self.call_count:
            self.stop()

    def stop(self) -> None:
        assert self.scheduler is not None
        self.scheduler.request_stop()


def build_scheduler(
    job: JobProbe,
    *,
    interval_seconds: float = 0.0,
    jitter_ratio: float = 0.0,
    seed: int = 1,
) -> IntervalScheduler:
    scheduler = IntervalScheduler(
        job,
        lambda: interval_seconds,
        jitter_ratio=jitter_ratio,
        rng=random.Random(seed),
    )
    job.scheduler = scheduler
    return scheduler


async def test_runs_job_immediately_on_start() -> None:
    job = JobProbe(stop_after_calls=1)
    scheduler = build_scheduler(job, interval_seconds=LONG_INTERVAL_SECONDS)

    async with asyncio.timeout(GUARD_SECONDS):
        await scheduler.run()

    assert job.call_count == 1


async def test_repeats_job_until_stop_is_requested() -> None:
    job = JobProbe(stop_after_calls=3)
    scheduler = build_scheduler(job)

    async with asyncio.timeout(GUARD_SECONDS):
        await scheduler.run()

    assert job.call_count == 3


async def test_stop_during_wait_returns_promptly() -> None:
    job = JobProbe()
    scheduler = build_scheduler(job, interval_seconds=LONG_INTERVAL_SECONDS)

    with structlog.testing.capture_logs() as captured_logs:
        async with asyncio.timeout(GUARD_SECONDS):
            run_task = asyncio.create_task(scheduler.run())
            await job.first_call_started.wait()
            scheduler.request_stop()
            await run_task

    waiting_logs = [log for log in captured_logs if log["event"] == "scheduled_job_waiting"]
    assert job.call_count == 1
    assert [log["delay_seconds"] for log in waiting_logs] == [LONG_INTERVAL_SECONDS]


async def test_stop_during_job_lets_job_finish() -> None:
    job_started = asyncio.Event()
    release_job = asyncio.Event()
    finished_calls: list[int] = []
    started_calls: list[int] = []

    async def blocking_job() -> None:
        started_calls.append(1)
        job_started.set()
        await release_job.wait()
        finished_calls.append(1)

    scheduler = IntervalScheduler(blocking_job, lambda: 0.0, jitter_ratio=0.0, rng=random.Random(1))

    async with asyncio.timeout(GUARD_SECONDS):
        run_task = asyncio.create_task(scheduler.run())
        await job_started.wait()
        scheduler.request_stop()
        release_job.set()
        await run_task

    assert finished_calls == [1]
    assert started_calls == [1]


async def test_waits_jittered_interval() -> None:
    job = JobProbe(stop_after_calls=2)
    scheduler = build_scheduler(job, interval_seconds=0.01, jitter_ratio=0.2, seed=7)
    expected_delay = apply_jitter(0.01, 0.2, random.Random(7))

    with structlog.testing.capture_logs() as captured_logs:
        async with asyncio.timeout(GUARD_SECONDS):
            await scheduler.run()

    waiting_logs = [log for log in captured_logs if log["event"] == "scheduled_job_waiting"]
    assert [log["delay_seconds"] for log in waiting_logs] == [expected_delay]


async def test_reads_interval_before_every_wait() -> None:
    job = JobProbe(stop_after_calls=3)
    intervals = iter([0.01, 0.02])
    scheduler = IntervalScheduler(
        job, lambda: next(intervals), jitter_ratio=0.0, rng=random.Random(1)
    )
    job.scheduler = scheduler

    with structlog.testing.capture_logs() as captured_logs:
        async with asyncio.timeout(GUARD_SECONDS):
            await scheduler.run()

    waiting_logs = [log for log in captured_logs if log["event"] == "scheduled_job_waiting"]
    assert [log["delay_seconds"] for log in waiting_logs] == [0.01, 0.02]


async def test_job_failure_is_logged_and_loop_continues() -> None:
    call_count = 0

    async def failing_then_stopping_job() -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("boom")
        scheduler.request_stop()

    scheduler = IntervalScheduler(
        failing_then_stopping_job, lambda: 0.0, jitter_ratio=0.0, rng=random.Random(1)
    )

    with structlog.testing.capture_logs() as captured_logs:
        async with asyncio.timeout(GUARD_SECONDS):
            await scheduler.run()

    failure_logs = [log for log in captured_logs if log["event"] == "scheduled_job_failed"]
    assert call_count == 2
    assert len(failure_logs) == 1


async def test_cancellation_propagates() -> None:
    job = JobProbe()
    scheduler = build_scheduler(job, interval_seconds=LONG_INTERVAL_SECONDS)

    async with asyncio.timeout(GUARD_SECONDS):
        run_task = asyncio.create_task(scheduler.run())
        await job.first_call_started.wait()
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task


@pytest.mark.parametrize("jitter_ratio", [-0.1, 1.1])
def test_rejects_jitter_ratio_outside_unit_interval(jitter_ratio: float) -> None:
    with pytest.raises(ValueError, match="jitter_ratio"):
        IntervalScheduler(JobProbe(), lambda: 1.0, jitter_ratio=jitter_ratio, rng=random.Random(1))
