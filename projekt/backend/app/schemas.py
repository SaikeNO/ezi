import ipaddress
import re
from datetime import datetime
from typing import Annotated, Self
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    TypeAdapter,
    field_validator,
    model_validator,
)

from app.models import LinkSelection, Scope, SessionStatus, Strategy

http_url = TypeAdapter(HttpUrl)


def validate_start_url(value: str) -> str:
    if len(value) > 2048 or any(
        char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value
    ):
        raise ValueError(
            "URL must contain at most 2048 characters and no whitespace/control characters"
        )
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None or "\\" in value:
        raise ValueError("URL credentials and backslashes are forbidden")
    url = http_url.validate_python(value)
    host = (url.host or "").strip("[]").rstrip(".").lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if (
            len(host) > 253
            or "." not in host
            or any(
                host == suffix or host.endswith("." + suffix)
                for suffix in ("localhost", "local", "internal", "lan", "home")
            )
            or not all(
                re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                for label in host.split(".")
            )
        ):
            raise ValueError("URL must use a valid public hostname") from None
    else:
        if (
            not address.is_global
            or address.is_multicast
            or address.is_reserved
            or getattr(address, "is_site_local", False)
            or getattr(address, "scope_id", None) is not None
        ):
            raise ValueError("URL must not use a private or reserved IP address")
    if url.port not in {80, 443}:
        raise ValueError("Only ports 80 and 443 are supported")
    return str(url).split("#", 1)[0]


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


class SessionList(BaseModel):
    items: list[SessionRead]
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
