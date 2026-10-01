from mercari_alert_bot.application.services.keyword_rule_service import KeywordRuleService


def provide_keyword_rule_service() -> KeywordRuleService:
    raise RuntimeError("keyword rule service is not wired")
