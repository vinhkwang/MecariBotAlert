from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Final

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from mercari_alert_bot.web.routers.actions import actions_router
from mercari_alert_bot.web.routers.keywords import router as keywords_router
from mercari_alert_bot.web.routers.settings import router as settings_router
from mercari_alert_bot.web.routers.status import router as status_router

WebAppLifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]

STATIC_DIRECTORY: Final[Path] = Path(__file__).parent / "static"


def create_web_app(lifespan: WebAppLifespan) -> FastAPI:
    app = FastAPI(
        title="Mercari Alert Bot",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.include_router(keywords_router)
    app.include_router(settings_router)
    app.include_router(status_router)
    app.include_router(actions_router)
    app.mount("/", StaticFiles(directory=STATIC_DIRECTORY, html=True), name="static")
    return app
