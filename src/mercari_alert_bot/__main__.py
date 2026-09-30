import uvicorn

from mercari_alert_bot.composition_root import build_web_app, configure_process_logging
from mercari_alert_bot.infrastructure.config.env_settings import EnvSettings


def main() -> None:
    settings = EnvSettings()
    configure_process_logging(settings)
    uvicorn.run(
        build_web_app(settings),
        host=settings.web_host,
        port=settings.web_port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
