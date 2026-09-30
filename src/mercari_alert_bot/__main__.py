import asyncio
import signal
from typing import Final

from mercari_alert_bot.composition_root import configure_process_logging, open_scanner
from mercari_alert_bot.infrastructure.config.env_settings import EnvSettings

SHUTDOWN_SIGNALS: Final = (signal.SIGTERM, signal.SIGINT)


async def run_scanner(settings: EnvSettings) -> None:
    loop = asyncio.get_running_loop()
    async with open_scanner(settings) as scheduler:
        for shutdown_signal in SHUTDOWN_SIGNALS:
            loop.add_signal_handler(shutdown_signal, scheduler.request_stop)
        try:
            await scheduler.run()
        finally:
            for shutdown_signal in SHUTDOWN_SIGNALS:
                loop.remove_signal_handler(shutdown_signal)


def main() -> None:
    settings = EnvSettings()
    configure_process_logging(settings)
    asyncio.run(run_scanner(settings))


if __name__ == "__main__":
    main()
