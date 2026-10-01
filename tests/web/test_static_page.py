import re
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mercari_alert_bot.web.app import STATIC_DIRECTORY, create_web_app

STATIC_FILE_NAMES: Final = ("index.html", "app.js", "app.css")

EXTERNAL_RESOURCE_PATTERN: Final = re.compile(
    r"""(?:src|href)\s*=\s*["']?\s*(?:https?:)?//|url\(\s*["']?\s*(?:https?:)?//|@import""",
    re.IGNORECASE,
)

UI_ENDPOINT_PATHS: Final = (
    "/api/keywords",
    "/reset-baseline",
    "/api/settings",
    "/api/status",
    "/api/listings",
    "/api/actions/test-notification",
    "/api/actions/import-yaml",
)

UNSAFE_DOM_WRITERS: Final = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write")

TELEGRAM_SECRET_NAMES: Final = ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "bot_token", "chat_id")


@asynccontextmanager
async def idle_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_web_app(idle_lifespan)) as test_client:
        yield test_client


def read_static_file(file_name: str) -> str:
    return (STATIC_DIRECTORY / file_name).read_text(encoding="utf-8")


def test_index_page_links_local_script_and_stylesheet(client: TestClient) -> None:
    page = client.get("/").text

    assert 'src="app.js"' in page
    assert 'href="app.css"' in page


def test_script_and_stylesheet_are_served_with_correct_types(client: TestClient) -> None:
    script_response = client.get("/app.js")
    stylesheet_response = client.get("/app.css")

    assert script_response.status_code == 200
    assert "javascript" in script_response.headers["content-type"]
    assert stylesheet_response.status_code == 200
    assert stylesheet_response.headers["content-type"].startswith("text/css")


def test_index_page_has_four_blocks(client: TestClient) -> None:
    page = client.get("/").text

    for section_id in ("keywords", "settings", "status", "listings"):
        assert f'<section id="{section_id}">' in page


@pytest.mark.parametrize("file_name", STATIC_FILE_NAMES)
def test_static_files_load_nothing_external(file_name: str) -> None:
    assert EXTERNAL_RESOURCE_PATTERN.search(read_static_file(file_name)) is None


def test_static_files_contain_no_comments() -> None:
    script_lines = read_static_file("app.js").splitlines()

    assert "<!--" not in read_static_file("index.html")
    assert "/*" not in read_static_file("app.css")
    assert "/*" not in read_static_file("app.js")
    assert not [line for line in script_lines if line.lstrip().startswith("//")]


def test_script_never_uses_inner_html() -> None:
    script = read_static_file("app.js")

    for unsafe_writer in UNSAFE_DOM_WRITERS:
        assert unsafe_writer not in script


def test_script_calls_every_ui_endpoint() -> None:
    script = read_static_file("app.js")
    page = read_static_file("index.html")

    for endpoint_path in UI_ENDPOINT_PATHS:
        assert endpoint_path in script
    assert 'href="/api/actions/export-yaml"' in page


@pytest.mark.parametrize("file_name", STATIC_FILE_NAMES)
def test_static_files_mention_no_telegram_secret(file_name: str) -> None:
    content = read_static_file(file_name)

    for secret_name in TELEGRAM_SECRET_NAMES:
        assert secret_name not in content
