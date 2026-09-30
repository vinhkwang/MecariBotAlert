from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Final

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

WebAppLifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]

STATIC_DIRECTORY: Final[Path] = Path(__file__).parent / "static"


def create_web_app(lifespan: WebAppLifespan) -> FastAPI:
    app = FastAPI(
        title="Mercari Alert Bot",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.mount("/", StaticFiles(directory=STATIC_DIRECTORY, html=True), name="static")
    return app
