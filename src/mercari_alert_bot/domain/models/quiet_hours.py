from dataclasses import dataclass
from datetime import time

from mercari_alert_bot.domain.errors import InvalidDomainValueError


def _is_aware(value: time) -> bool:
    return value.utcoffset() is not None


@dataclass(frozen=True, slots=True, kw_only=True)
class QuietHoursWindow:
    starts_at: time
    ends_at: time

    def __post_init__(self) -> None:
        if _is_aware(self.starts_at):
            raise InvalidDomainValueError("starts_at must be a naive wall-clock time")
        if _is_aware(self.ends_at):
            raise InvalidDomainValueError("ends_at must be a naive wall-clock time")
        if self.starts_at == self.ends_at:
            raise InvalidDomainValueError("starts_at and ends_at must differ")

    @property
    def crosses_midnight(self) -> bool:
        return self.starts_at > self.ends_at

    def contains(self, local_time: time) -> bool:
        if _is_aware(local_time):
            raise InvalidDomainValueError("local_time must be a naive wall-clock time")
        if self.crosses_midnight:
            return local_time >= self.starts_at or local_time < self.ends_at
        return self.starts_at <= local_time < self.ends_at
