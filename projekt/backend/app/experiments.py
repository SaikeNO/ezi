from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.api import Database
from app.comparison import CompareInput, ComparisonRead, compare
from app.models import CrawlConfig, CrawlSession, Experiment, SessionStatus, utc_now
from app.schemas import CrawlConfigInput, ErrorResponse, InputModel, SessionRead, validate_start_url

router = APIRouter(
    prefix="/api",
    tags=["experiments"],
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)


class ExperimentCreate(InputModel):
    name: Annotated[str, Field(strict=True, min_length=1, max_length=200)]
    start_url: Annotated[str, Field(strict=True, min_length=1, max_length=2048)]
    variants: Annotated[list[CrawlConfigInput], Field(min_length=2, max_length=4)]

    _url = field_validator("start_url")(validate_start_url)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Experiment name cannot be blank")
        return value.strip()


class ExperimentRead(BaseModel):
    id: UUID
    name: str
    start_url: str
    created_at: datetime
    state: str
    sessions: list[SessionRead]


class ExperimentList(BaseModel):
    items: list[ExperimentRead]
    total: int
    offset: int
    limit: int


class LaunchError(BaseModel):
    session_id: UUID
    status: int
    code: str
    message: str


class ExperimentLaunch(BaseModel):
    experiment: ExperimentRead
    errors: list[LaunchError]


def find_experiment(db: Session, experiment_id: UUID) -> Experiment:
    experiment = db.get(Experiment, str(experiment_id))
    if experiment is None:
        raise HTTPException(
            404, detail={"code": "experiment_not_found", "message": "Nie znaleziono eksperymentu"}
        )
    return experiment


def read_experiment(experiment: Experiment) -> ExperimentRead:
    sessions = sorted(experiment.sessions, key=lambda value: (value.created_at, value.id))
    states = {session.status for session in sessions}
    state = (
        "incomplete"
        if len(sessions) < 2
        else "running"
        if SessionStatus.RUNNING in states
        else "queued"
        if SessionStatus.QUEUED in states
        else "finished"
    )
    return ExperimentRead(
        id=experiment.id,
        name=experiment.name,
        start_url=experiment.start_url,
        created_at=experiment.created_at,
        state=state,
        sessions=[SessionRead.model_validate(value) for value in sessions],
    )


@router.post("/experiments", response_model=ExperimentRead, status_code=201)
def create_experiment(
    payload: ExperimentCreate, response: Response, db: Database
) -> ExperimentRead:
    timestamp = utc_now()
    experiment = Experiment(
        name=payload.name,
        start_url=payload.start_url,
        sessions=[
            CrawlSession(
                start_url=payload.start_url,
                created_at=timestamp + timedelta(microseconds=index),
                config=CrawlConfig(**config.model_dump()),
            )
            for index, config in enumerate(payload.variants)
        ],
    )
    db.add(experiment)
    db.commit()
    response.headers["Location"] = f"/api/experiments/{experiment.id}"
    return read_experiment(experiment)


@router.get("/experiments", response_model=ExperimentList)
def list_experiments(
    db: Database,
    offset: Annotated[int, Query(ge=0, le=2147483647)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> ExperimentList:
    db.connection().exec_driver_sql("BEGIN")
    total = db.scalar(select(func.count()).select_from(Experiment)) or 0
    rows = db.scalars(
        select(Experiment)
        .options(selectinload(Experiment.sessions).selectinload(CrawlSession.config))
        .order_by(Experiment.created_at.desc(), Experiment.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return ExperimentList(
        items=[read_experiment(value) for value in rows], total=total, offset=offset, limit=limit
    )


@router.get("/experiments/{experiment_id}", response_model=ExperimentRead)
def get_experiment(experiment_id: UUID, db: Database) -> ExperimentRead:
    db.connection().exec_driver_sql("BEGIN")
    return read_experiment(find_experiment(db, experiment_id))


@router.post("/experiments/{experiment_id}/start", response_model=ExperimentLaunch)
async def start_experiment(experiment_id: UUID, request: Request) -> ExperimentLaunch:
    with Session(request.app.state.engine) as db:
        experiment = find_experiment(db, experiment_id)
        if len(experiment.sessions) < 2:
            raise HTTPException(
                409,
                detail={
                    "code": "experiment_incomplete",
                    "message": "Eksperyment ma mniej niż dwie sesje. Utwórz nowy eksperyment.",
                },
            )
        ids = [
            value.id
            for value in sorted(experiment.sessions, key=lambda value: (value.created_at, value.id))
            if value.status == SessionStatus.QUEUED
        ]
    errors = []
    for session_id in ids:
        try:
            await request.app.state.crawler.start(session_id)
        except HTTPException as error:
            detail = error.detail if isinstance(error.detail, dict) else {}
            errors.append(
                LaunchError(
                    session_id=session_id,
                    status=error.status_code,
                    code=detail.get("code", "start_failed"),
                    message=detail.get("message", "Nie udało się uruchomić wariantu"),
                )
            )
    with Session(request.app.state.engine) as db:
        return ExperimentLaunch(
            experiment=read_experiment(find_experiment(db, experiment_id)), errors=errors
        )


@router.delete("/experiments/{experiment_id}", status_code=204)
def delete_experiment(experiment_id: UUID, db: Database) -> Response:
    db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    db.delete(find_experiment(db, experiment_id))
    db.commit()
    return Response(status_code=204)


@router.post("/compare", response_model=ComparisonRead, responses={413: {"model": ErrorResponse}})
def compare_sessions(
    payload: CompareInput,
    db: Database,
    offset: Annotated[int, Query(ge=0, le=2147483647)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ComparisonRead:
    return compare(db, payload.session_ids, offset, limit)
