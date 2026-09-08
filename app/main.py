from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.db import Base, engine

BASE_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)  # idempotent dev convenience; alters never happen automatically
    yield


def create_app() -> FastAPI:
    from app.config import get_settings
    from app.api.health import router as health_router
    from app.api.pages import router as pages_router

    app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(pages_router)
    app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
    return app


app = create_app()
