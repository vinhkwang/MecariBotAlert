class DomainError(Exception):
    pass


class InvalidDomainValueError(DomainError, ValueError):
    pass


class ListingSourceError(DomainError):
    pass


class NotificationDeliveryError(DomainError):
    pass


class KeywordRuleNotFoundError(DomainError):
    pass
