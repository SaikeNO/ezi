import asyncio
import json
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, defer, selectinload
from starlette.background import BackgroundTask

from app.crawler.manager import TERMINAL
from app.database import session_scope
from app.explorer import PageFilters, Separator, export_fields, page_filters, prepare_csv
from app.graph import MAX_GRAPH_EDGES, MAX_GRAPH_NODES, GraphRead, GraphStats, projection
from app.models import CrawlConfig, CrawlEvent, CrawlSession, Link, Page, SessionStatus
from app.schemas import (
    ErrorResponse,
    LinkList,
    LinkRead,
    PageList,
    PageRead,
    PageSummary,
    SessionCreate,
    SessionList,
    SessionRead,
    SessionUpdate,
)

router = APIRouter(
    prefix="/api/sessions",
    tags=["sessions"],
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)


def get_db(request: Request) -> Iterator[Session]:
    yield from session_scope(request.app.state.engine)


Database = Annotated[Session, Depends(get_db)]
Filters = Annotated[PageFilters, Depends(page_filters)]


def find_session(db: Session, session_id: UUID) -> CrawlSession:
    crawl = db.scalar(
        select(CrawlSession)
        .options(selectinload(CrawlSession.config))
        .where(CrawlSession.id == str(session_id))
    )
    if crawl is None:
        raise HTTPException(
            404, detail={"code": "session_not_found", "message": "Nie znaleziono sesji"}
        )
    return crawl


@router.post("", response_model=SessionRead, status_code=201)
def create_session(payload: SessionCreate, response: Response, db: Database) -> SessionRead:
    crawl = CrawlSession(
        start_url=payload.start_url, config=CrawlConfig(**payload.config.model_dump())
    )
    db.add(crawl)
    db.commit()
    db.refresh(crawl)
    response.headers["Location"] = f"/api/sessions/{crawl.id}"
    return SessionRead.model_validate(crawl)


@router.get("", response_model=SessionList)
def list_sessions(
    db: Database,
    offset: Annotated[int, Query(ge=0, le=2147483647)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    status: SessionStatus | None = None,
) -> SessionList:
    filters = [CrawlSession.status == status] if status is not None else []
    total = db.scalar(select(func.count()).select_from(CrawlSession).where(*filters)) or 0
    rows = db.scalars(
        select(CrawlSession)
        .options(selectinload(CrawlSession.config))
        .where(*filters)
        .order_by(CrawlSession.created_at.desc(), CrawlSession.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return SessionList(
        items=[SessionRead.model_validate(row) for row in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/{session_id}", response_model=SessionRead)
def read_session(session_id: UUID, db: Database) -> SessionRead:
    return SessionRead.model_validate(find_session(db, session_id))


@router.get(
    "/{session_id}/graph", response_model=GraphRead, responses={413: {"model": ErrorResponse}}
)
def read_graph(session_id: UUID, db: Database) -> GraphRead:
    return projection(db, session_id, graph_limits=(MAX_GRAPH_NODES, MAX_GRAPH_EDGES))[0]


@router.get("/{session_id}/stats", response_model=GraphStats)
def read_stats(session_id: UUID, db: Database) -> GraphStats:
    return projection(db, session_id, include_edges=False)[1]


def find_page(db: Session, session_id: UUID, page_id: UUID) -> Page:
    find_session(db, session_id)
    page = db.scalar(
        select(Page).where(Page.session_id == str(session_id), Page.id == str(page_id))
    )
    if page is None:
        raise HTTPException(
            404, detail={"code": "page_not_found", "message": "Nie znaleziono strony"}
        )
    return page


@router.get("/{session_id}/pages", response_model=PageList)
def list_pages(
    session_id: UUID,
    db: Database,
    filters: Filters,
    offset: Annotated[int, Query(ge=0, le=2147483647)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PageList:
    db.connection().exec_driver_sql("BEGIN")
    find_session(db, session_id)
    predicates = filters.predicates(str(session_id))
    total = db.scalar(select(func.count()).select_from(Page).where(*predicates)) or 0
    rows = db.scalars(
        select(Page)
        .options(defer(Page.body))
        .where(*predicates)
        .order_by(Page.discovery_order, Page.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return PageList(
        items=[PageSummary.model_validate(row) for row in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{session_id}/export",
    response_class=StreamingResponse,
    responses={
        200: {"content": {"text/csv": {"schema": {"type": "string", "format": "binary"}}}},
        413: {"model": ErrorResponse},
    },
)
def export_pages(
    session_id: UUID,
    db: Database,
    filters: Filters,
    fields: Annotated[list[str], Depends(export_fields)],
    separator: Separator = Separator.COMMA,
    bom: bool = True,
) -> StreamingResponse:
    db.connection().exec_driver_sql("BEGIN")
    find_session(db, session_id)
    output, size = prepare_csv(db, str(session_id), filters, fields, separator, bom)
    try:
        db.rollback()  # Release snapshot before slow network download.
    except BaseException:
        output.close()
        raise

    def chunks():
        try:
            while block := output.read(65536):
                yield block
        finally:
            output.close()

    return StreamingResponse(
        chunks(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="crawl-{session_id}.csv"',
            "Content-Length": str(size),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
        background=BackgroundTask(output.close),
    )


@router.get("/{session_id}/pages/{page_id}", response_model=PageRead)
def read_page(session_id: UUID, page_id: UUID, db: Database) -> PageRead:
    return PageRead.model_validate(find_page(db, session_id, page_id))


@router.get("/{session_id}/pages/{page_id}/links", response_model=LinkList)
def list_page_links(
    session_id: UUID,
    page_id: UUID,
    db: Database,
    offset: Annotated[int, Query(ge=0, le=2147483647)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> LinkList:
    find_page(db, session_id, page_id)
    filters = [Link.session_id == str(session_id), Link.source_page_id == str(page_id)]
    total = db.scalar(select(func.count()).select_from(Link).where(*filters)) or 0
    rows = db.scalars(
        select(Link).where(*filters).order_by(Link.id).offset(offset).limit(limit)
    ).all()
    return LinkList(
        items=[LinkRead.model_validate(row) for row in rows],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.patch("/{session_id}", response_model=SessionRead)
def update_session(session_id: UUID, payload: SessionUpdate, db: Database) -> SessionRead:
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    crawl = find_session(db, session_id)
    if crawl.experiments:
        raise HTTPException(
            409,
            detail={
                "code": "experiment_config_locked",
                "message": "Wariant eksperymentu jest niezmienny. Utwórz nowy eksperyment.",
            },
        )
    if crawl.status != SessionStatus.QUEUED:
        raise HTTPException(
            409,
            detail={
                "code": "session_not_editable",
                "message": "Można edytować tylko oczekującą sesję",
            },
        )
    if payload.start_url is not None:
        crawl.start_url = payload.start_url
    if payload.config is not None:
        for field, value in payload.config.model_dump().items():
            setattr(crawl.config, field, value)
    db.commit()
    db.refresh(crawl)
    return SessionRead.model_validate(crawl)


@router.delete("/{session_id}", status_code=204)
def delete_session(session_id: UUID, db: Database) -> Response:
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    crawl = find_session(db, session_id)
    if crawl.status == SessionStatus.RUNNING:
        raise HTTPException(
            409,
            detail={"code": "session_running", "message": "Nie można usunąć uruchomionej sesji"},
        )
    db.delete(crawl)
    db.commit()
    return Response(status_code=204)


@router.post("/{session_id}/start", response_model=SessionRead)
async def start_session(session_id: UUID, request: Request) -> SessionRead:
    return await request.app.state.crawler.start(str(session_id))


@router.post("/{session_id}/cancel", response_model=SessionRead)
async def cancel_session(session_id: UUID, request: Request) -> SessionRead:
    return await request.app.state.crawler.cancel(str(session_id))


@router.get("/{session_id}/events", response_class=StreamingResponse)
async def session_events(
    session_id: UUID,
    request: Request,
    after: Annotated[int, Query(ge=0, le=9223372036854775807)] = 0,
    last_event_id: Annotated[int | None, Header(ge=0, le=9223372036854775807)] = None,
) -> StreamingResponse:
    with Session(request.app.state.engine) as db:
        find_session(db, session_id)

    async def stream():
        cursor = max(after, last_event_id or 0)
        heartbeat = asyncio.get_running_loop().time()
        yield "retry: 2000\n\n"
        while not await request.is_disconnected():
            with Session(request.app.state.engine) as db:
                crawl = db.get(CrawlSession, str(session_id))
                if crawl is None:
                    return
                terminal = crawl.status in TERMINAL
                events = [
                    (event.id, event.kind, event.data)
                    for event in db.scalars(
                        select(CrawlEvent)
                        .where(CrawlEvent.session_id == str(session_id), CrawlEvent.id > cursor)
                        .order_by(CrawlEvent.id)
                        .limit(200)
                    )
                ]
            for event_id, kind, data in events:
                cursor = event_id
                payload = json.dumps(data, ensure_ascii=False)
                yield f"id: {event_id}\nevent: {kind}\ndata: {payload}\n\n"
            if terminal and not events:
                return
            now = asyncio.get_running_loop().time()
            if now - heartbeat >= 15:
                yield ": heartbeat\n\n"
                heartbeat = now
            await asyncio.sleep(0 if events else 0.2)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
