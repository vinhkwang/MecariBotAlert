import asyncio
import random
from collections.abc import Awaitable, Callable

import structlog

from mercari_alert_bot.shared.jitter import apply_jitter

ScheduledJob = Callable[[], Awaitable[None]]
IntervalSecondsProvider = Callable[[], float]

logger = structlog.get_logger(__name__)


class IntervalScheduler:
    def __init__(
        self,
        job: ScheduledJob,
        interval_seconds: IntervalSecondsProvider,
        *,
        jitter_ratio: float,
        rng: random.Random,
    ) -> None:
        if not 0 <= jitter_ratio <= 1:
            raise ValueError(f"jitter_ratio must be within [0, 1]: {jitter_ratio}")
        self._job = job
        self._interval_seconds = interval_seconds
        self._jitter_ratio = jitter_ratio
        self._rng = rng
        self._stop_requested = asyncio.Event()

    async def run(self) -> None:
        while not self._stop_requested.is_set():
            await self._run_job_isolated()
            if self._stop_requested.is_set():
                return
            await self._wait_for_next_run()

    def request_stop(self) -> None:
        self._stop_requested.set()

    async def _run_job_isolated(self) -> None:
        try:
            await self._job()
        except Exception:
            logger.exception("scheduled_job_failed")

    async def _wait_for_next_run(self) -> None:
        delay_seconds = apply_jitter(self._interval_seconds(), self._jitter_ratio, self._rng)
        logger.info("scheduled_job_waiting", delay_seconds=delay_seconds)
        try:
            await asyncio.wait_for(self._stop_requested.wait(), timeout=delay_seconds)
        except TimeoutError:
            return
