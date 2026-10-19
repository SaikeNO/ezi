import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api import router
from app.core.config import Settings
from app.crawler.manager import CrawlManager, TransportFactory
from app.database import build_engine
from app.errors import install_error_handlers
from app.experiments import router as experiments_router

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: Literal["ok", "error"]
    database: Literal["ok", "unavailable"]


def create_app(
    settings: Settings | None = None, *, transport_factory: TransportFactory | None = None
) -> FastAPI:
    settings = settings or Settings()
    engine = build_engine(settings.database_url)

    manager = CrawlManager(engine, transport_factory)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            manager.startup()
            yield
        finally:
            await manager.shutdown()
            engine.dispose()

    application = FastAPI(title="WebCrawler Studio", version="0.3.0", lifespan=lifespan)
    application.state.engine = engine
    application.state.crawler = manager
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "Last-Event-ID"],
        expose_headers=["Location"],
    )

    @application.get(
        "/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}}
    )
    def health(response: Response) -> HealthResponse:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            logger.exception("Database health check failed")
            response.status_code = 503
            return HealthResponse(status="error", database="unavailable")
        return HealthResponse(status="ok", database="ok")

    install_error_handlers(application)
    application.include_router(router)
    application.include_router(experiments_router)
    return application


app = create_app()
