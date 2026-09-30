from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from mercari_alert_bot.web.app import create_web_app


class RecordingLifespan:
    def __init__(self) -> None:
        self.events: list[str] = []

    @asynccontextmanager
    async def __call__(self, _app: FastAPI) -> AsyncIterator[None]:
        self.events.append("entered")
        try:
            yield
        finally:
            self.events.append("exited")


def test_root_serves_index_page() -> None:
    with TestClient(create_web_app(RecordingLifespan())) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")


def test_lifespan_enters_on_startup_and_exits_on_shutdown() -> None:
    lifespan = RecordingLifespan()

    with TestClient(create_web_app(lifespan)):
        assert lifespan.events == ["entered"]

    assert lifespan.events == ["entered", "exited"]


def test_interactive_docs_are_disabled() -> None:
    with TestClient(create_web_app(RecordingLifespan())) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
