from dataclasses import dataclass

from mercari_alert_bot.domain.errors import InvalidDomainValueError


@dataclass(frozen=True, slots=True)
class JpyAmount:
    yen: int

    def __post_init__(self) -> None:
        if isinstance(self.yen, bool) or not isinstance(self.yen, int):
            raise InvalidDomainValueError(f"yen must be an int, got {type(self.yen).__name__}")
        if self.yen < 0:
            raise InvalidDomainValueError(f"yen must not be negative, got {self.yen}")
