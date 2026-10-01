import os
import sys
from collections.abc import Mapping
from http import HTTPStatus
from typing import Final
from urllib.request import urlopen

HEALTH_PATH: Final = "/healthz"
DEFAULT_WEB_PORT: Final = "8080"
PROBE_TIMEOUT_SECONDS: Final = 5.0
LOOPBACK_HOST: Final = "127.0.0.1"


def build_health_url(environment: Mapping[str, str]) -> str:
    web_port = environment.get("WEB_PORT", DEFAULT_WEB_PORT)
    return f"http://{LOOPBACK_HOST}:{web_port}{HEALTH_PATH}"


def is_service_healthy(health_url: str, timeout_seconds: float = PROBE_TIMEOUT_SECONDS) -> bool:
    try:
        with urlopen(health_url, timeout=timeout_seconds) as response:
            return bool(response.status == HTTPStatus.OK)
    except OSError:
        return False


def main() -> None:
    is_healthy = is_service_healthy(build_health_url(os.environ))
    sys.exit(0 if is_healthy else 1)


if __name__ == "__main__":
    main()
