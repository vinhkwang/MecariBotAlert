from datetime import datetime, timedelta


class FrozenClock:
    def __init__(self, current_time: datetime) -> None:
        if current_time.utcoffset() != timedelta(0):
            raise ValueError("FrozenClock requires a UTC datetime")
        self._current_time = current_time

    def now(self) -> datetime:
        return self._current_time

    def advance(self, elapsed: timedelta) -> None:
        self._current_time += elapsed
