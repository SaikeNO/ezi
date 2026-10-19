import asyncio
import logging
from collections.abc import Callable

import httpx
from fastapi import HTTPException
from sqlalchemy import Engine, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.crawler.engine import CrawlEngine
from app.crawler.events import record
from app.crawler.fetcher import Fetcher, OriginLimiter
from app.crawler.ownership import WorkerOwnership
from app.crawler.robots import USER_AGENT
from app.models import CrawlSession, SessionStatus, utc_now
from app.schemas import CrawlConfigInput, SessionRead

logger = logging.getLogger(__name__)
TransportFactory = Callable[[], httpx.AsyncBaseTransport]
TERMINAL = {SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.CANCELLED}


class CrawlManager:
    def __init__(self, engine: Engine, transport_factory: TransportFactory | None = None):
        self.engine, self.transport_factory = engine, transport_factory
        self.jobs: dict[str, asyncio.Task] = {}
        self.limiter = OriginLimiter()
        self.lock = asyncio.Lock()
        self.ownership = WorkerOwnership(str(engine.url))
        self.stopping = False

    def startup(self) -> None:
        self.stopping = False
        self.ownership.acquire()
        try:
            if not inspect(self.engine).has_table("crawl_events"):
                return  # Diagnostics remain available before migrations.
            with Session(self.engine) as db:
                for crawl in db.scalars(
                    select(CrawlSession).where(CrawlSession.status == SessionStatus.RUNNING)
                ):
                    crawl.status, crawl.finished_at = SessionStatus.FAILED, utc_now()
                    crawl.stop_reason, crawl.error = (
                        "interrupted",
                        "Przerwano przez restart backendu",
                    )
                    record(db, crawl, "failure")
                db.commit()
        except SQLAlchemyError:
            logger.exception("Crawler recovery unavailable; check database/migrations")

    async def shutdown(self) -> None:
        self.stopping = True
        tasks = list(self.jobs.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self.ownership.release()

    def get(self, db: Session, session_id: str) -> CrawlSession:
        crawl = db.get(CrawlSession, session_id)
        if crawl is None:
            raise HTTPException(
                404, detail={"code": "session_not_found", "message": "Nie znaleziono sesji"}
            )
        return crawl

    async def start(self, session_id: str) -> SessionRead:
        async with self.lock:
            with Session(self.engine) as db:
                db.connection().exec_driver_sql("BEGIN IMMEDIATE")
                crawl = self.get(db, session_id)
                if crawl.status == SessionStatus.RUNNING:
                    return SessionRead.model_validate(crawl)
                if crawl.status != SessionStatus.QUEUED:
                    raise HTTPException(
                        409,
                        detail={
                            "code": "session_already_finished",
                            "message": "Utwórz nową sesję, aby ponownie pobrać stronę",
                        },
                    )
                if len(self.jobs) >= 4:
                    raise HTTPException(
                        429,
                        detail={
                            "code": "crawler_busy",
                            "message": "Osiągnięto limit równoczesnych sesji. Spróbuj później.",
                        },
                    )
                config = CrawlConfigInput.model_validate(crawl.config)
                crawl.status, crawl.started_at = SessionStatus.RUNNING, utc_now()
                crawl.crawler_version, crawl.user_agent = "0.3.0", USER_AGENT
                record(db, crawl, "progress", effective_concurrency=1)
                start_url = crawl.start_url
                db.commit()
                result = SessionRead.model_validate(crawl)
            try:
                transport = self.transport_factory() if self.transport_factory else None
                fetcher = Fetcher(config, start_url, self.limiter, transport)
            except Exception as error:
                with Session(self.engine) as db:
                    crawl = self.get(db, session_id)
                    crawl.status, crawl.finished_at = SessionStatus.FAILED, utc_now()
                    crawl.stop_reason, crawl.error = (
                        "internal_error",
                        "Nie udało się uruchomić crawlera",
                    )
                    record(db, crawl, "failure")
                    db.commit()
                raise HTTPException(
                    503,
                    detail={
                        "code": "crawler_unavailable",
                        "message": "Nie udało się uruchomić crawlera",
                    },
                ) from error
            worker = CrawlEngine(
                self.engine,
                session_id,
                config,
                start_url,
                fetcher,
                cancel_reason=lambda: "server_shutdown" if self.stopping else "user_cancelled",
            )
            task = asyncio.create_task(worker.run(), name=f"crawl-{session_id}")
            self.jobs[session_id] = task

            def done_callback(done: asyncio.Task) -> None:
                self.jobs.pop(session_id, None)
                if not done.cancelled() and done.exception() is not None:
                    logger.error("Crawler task cleanup failed", exc_info=done.exception())

            task.add_done_callback(done_callback)
            return result

    async def cancel(self, session_id: str) -> SessionRead:
        async with self.lock:
            task = self.jobs.get(session_id)
            if task is not None:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            with Session(self.engine) as db:
                db.connection().exec_driver_sql("BEGIN IMMEDIATE")
                crawl = self.get(db, session_id)
                if crawl.status not in TERMINAL:
                    crawl.status, crawl.finished_at = SessionStatus.CANCELLED, utc_now()
                    crawl.stop_reason = "user_cancelled"
                    record(db, crawl, "cancelled")
                    db.commit()
                return SessionRead.model_validate(crawl)
