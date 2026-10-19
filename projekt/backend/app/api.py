from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.database import session_scope
from app.models import CrawlConfig, CrawlSession, SessionStatus
from app.schemas import ErrorResponse, SessionCreate, SessionList, SessionRead, SessionUpdate

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


@router.patch("/{session_id}", response_model=SessionRead)
def update_session(session_id: UUID, payload: SessionUpdate, db: Database) -> SessionRead:
    crawl = find_session(db, session_id)
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
    crawl = find_session(db, session_id)
    if crawl.status == SessionStatus.RUNNING:
        raise HTTPException(
            409,
            detail={"code": "session_running", "message": "Nie można usunąć uruchomionej sesji"},
        )
    db.delete(crawl)
    db.commit()
    return Response(status_code=204)
