import io
import json
import logging
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any

import pytest
import structlog

from mercari_alert_bot.shared.logging import configure_logging


@pytest.fixture
def log_buffer() -> Iterator[io.StringIO]:
    buffer = io.StringIO()
    yield buffer
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def read_log_lines(buffer: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in buffer.getvalue().splitlines()]


def test_log_line_is_single_json_object(log_buffer: io.StringIO) -> None:
    configure_logging(logging.INFO, log_buffer)

    structlog.get_logger().info("scan_cycle_completed")

    [log_line] = read_log_lines(log_buffer)
    assert log_line["event"] == "scan_cycle_completed"
    assert log_line["level"] == "info"


def test_timestamp_is_iso_utc(log_buffer: io.StringIO) -> None:
    configure_logging(logging.INFO, log_buffer)

    structlog.get_logger().info("scan_cycle_completed")

    [log_line] = read_log_lines(log_buffer)
    logged_at = datetime.fromisoformat(log_line["timestamp"])
    assert logged_at.utcoffset() == timedelta(0)


def test_bound_context_vars_appear_on_every_line(log_buffer: io.StringIO) -> None:
    configure_logging(logging.INFO, log_buffer)
    logger = structlog.get_logger()

    with structlog.contextvars.bound_contextvars(rule_name="pokemon", cycle_id="c1"):
        logger.info("scan_started")
        logger.info("scan_completed")

    log_lines = read_log_lines(log_buffer)
    assert len(log_lines) == 2
    for log_line in log_lines:
        assert log_line["rule_name"] == "pokemon"
        assert log_line["cycle_id"] == "c1"


def test_messages_below_configured_level_are_dropped(log_buffer: io.StringIO) -> None:
    configure_logging(logging.WARNING, log_buffer)

    structlog.get_logger().info("scan_cycle_completed")

    assert log_buffer.getvalue() == ""


def test_exception_traceback_is_rendered_into_json(log_buffer: io.StringIO) -> None:
    configure_logging(logging.INFO, log_buffer)

    try:
        raise ZeroDivisionError("boom")
    except ZeroDivisionError:
        structlog.get_logger().exception("scan_failed")

    [log_line] = read_log_lines(log_buffer)
    assert log_line["level"] == "error"
    assert "ZeroDivisionError: boom" in log_line["exception"]
