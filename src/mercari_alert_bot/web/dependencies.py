from mercari_alert_bot.application.services.keyword_rule_service import KeywordRuleService
from mercari_alert_bot.application.services.polling_settings_service import (
    PollingSettingsService,
)
from mercari_alert_bot.application.services.system_status_service import SystemStatusService


def provide_keyword_rule_service() -> KeywordRuleService:
    raise RuntimeError("keyword rule service is not wired")


def provide_polling_settings_service() -> PollingSettingsService:
    raise RuntimeError("polling settings service is not wired")


def provide_system_status_service() -> SystemStatusService:
    raise RuntimeError("system status service is not wired")
