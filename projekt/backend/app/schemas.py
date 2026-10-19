from datetime import datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.crawler.urls import CrawlError, validate_destination
from app.models import LinkKind, LinkSelection, Scope, SessionStatus, Strategy


def validate_start_url(value: str) -> str:
    try:
        return validate_destination(value)
    except CrawlError as error:
        raise ValueError(str(error)) from error


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class CrawlConfigInput(InputModel):
    strategy: Strategy = Strategy.BFS
    scope: Scope = Scope.SERVER
    link_types: LinkSelection = LinkSelection.HYPERLINKS
    max_depth: Annotated[int, Field(strict=True, ge=0, le=20)] = 3
    max_pages: Annotated[int, Field(strict=True, ge=1, le=10000)] = 100
    timeout_seconds: Annotated[float, Field(strict=True, ge=1, le=60, allow_inf_nan=False)] = 10
    request_delay_ms: Annotated[int, Field(strict=True, ge=100, le=60000)] = 500
    max_duration_seconds: Annotated[int, Field(strict=True, ge=1, le=3600)] = 300
    max_response_bytes: Annotated[int, Field(strict=True, ge=1024, le=10485760)] = 2097152
    max_redirects: Annotated[int, Field(strict=True, ge=0, le=10)] = 5
    concurrency: Annotated[int, Field(strict=True, ge=1, le=8)] = 2
    respect_robots: Annotated[bool, Field(strict=True)] = True
    follow_external_urls: Annotated[bool, Field(strict=True)] = False
    process_one_page: Annotated[bool, Field(strict=True)] = False


class SessionCreate(InputModel):
    start_url: Annotated[str, Field(strict=True, min_length=1, max_length=2048)]
    config: CrawlConfigInput = Field(default_factory=CrawlConfigInput)

    _validate_url = field_validator("start_url")(validate_start_url)


class SessionUpdate(InputModel):
    start_url: Annotated[str, Field(strict=True, min_length=1, max_length=2048)] | None = None
    config: CrawlConfigInput | None = None

    @field_validator("start_url")
    @classmethod
    def validate_url(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("start_url cannot be null")
        return validate_start_url(value)

    @field_validator("config")
    @classmethod
    def validate_config(cls, value: CrawlConfigInput | None) -> CrawlConfigInput:
        if value is None:
            raise ValueError("config cannot be null")
        return value

    @model_validator(mode="after")
    def require_changes(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("Provide start_url or config")
        return self


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    start_url: str
    status: SessionStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    discovered_count: int
    fetched_count: int
    error_count: int
    error: str | None
    config: CrawlConfigInput
    stop_reason: str | None
    link_count: int
    crawler_version: str | None
    user_agent: str | None
    configuration_locked: bool


class SessionList(BaseModel):
    items: list[SessionRead]
    total: int
    offset: int
    limit: int


class PageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    session_id: UUID
    normalized_url: str
    original_url: str
    final_url: str | None
    depth: int
    discovery_order: int
    fetch_order: int | None
    http_status: int | None
    content_type: str | None
    encoding: str | None
    title: str | None
    description: str | None
    keywords: str | None
    error: str | None


class PageRead(PageSummary):
    body: str | None


class PageList(BaseModel):
    items: list[PageSummary]
    total: int
    offset: int
    limit: int


class LinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    source_page_id: UUID
    target_url: str
    target_page_id: UUID | None
    kind: LinkKind
    is_external: bool
    is_followed: bool


class LinkList(BaseModel):
    items: list[LinkRead]
    total: int
    offset: int
    limit: int


class ErrorDetail(BaseModel):
    location: list[str | int]
    message: str
    type: str


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
