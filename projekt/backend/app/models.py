from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.database import Base


def new_id() -> str:
    return str(uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """SQLite stores naive UTC; application always receives aware UTC timestamps."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Timestamp must include a timezone")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        return value.replace(tzinfo=UTC) if value is not None else None


class SessionStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Strategy(StrEnum):
    BFS = "bfs"
    DFS = "dfs"


class Scope(StrEnum):
    SERVER = "server"
    WEB = "web"


class LinkSelection(StrEnum):
    HYPERLINKS = "hyperlinks"
    IMAGES_AND_HYPERLINKS = "images_and_hyperlinks"
    ALL_LINKS = "all_links"


class LinkKind(StrEnum):
    HYPERLINK = "hyperlink"
    IMAGE = "image"
    STYLESHEET = "stylesheet"
    SCRIPT = "script"
    MEDIA = "media"
    OTHER = "other"


def enum_type(enum: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        validate_strings=True,
        values_callable=lambda values: [item.value for item in values],
    )


experiment_sessions = Table(
    "experiment_sessions",
    Base.metadata,
    Column("experiment_id", ForeignKey("experiments.id", ondelete="CASCADE"), primary_key=True),
    Column("session_id", ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True),
    Index("ix_experiment_sessions_session_id", "session_id"),
)


class CrawlSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "discovered_count >= 0 AND fetched_count >= 0 AND error_count >= 0",
            name="ck_sessions_counters",
        ),
        Index("ix_sessions_created_at_id", "created_at", "id"),
        Index("ix_sessions_status_created_at", "status", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    start_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status: Mapped[SessionStatus] = mapped_column(
        enum_type(SessionStatus, "session_status"), default=SessionStatus.QUEUED
    )
    discovered_count: Mapped[int] = mapped_column(Integer, default=0)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    config: Mapped["CrawlConfig"] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        single_parent=True,
    )
    pages: Mapped[list["Page"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )
    links: Mapped[list["Link"]] = relationship(
        back_populates="session",
        foreign_keys="Link.session_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    experiments: Mapped[list["Experiment"]] = relationship(
        secondary=experiment_sessions, back_populates="sessions", passive_deletes=True
    )


class CrawlConfig(Base):
    __tablename__ = "crawl_config"
    __table_args__ = (
        CheckConstraint("max_depth BETWEEN 0 AND 20", name="ck_config_depth"),
        CheckConstraint("max_pages BETWEEN 1 AND 10000", name="ck_config_pages"),
        CheckConstraint("timeout_seconds BETWEEN 1 AND 60", name="ck_config_timeout"),
        CheckConstraint("request_delay_ms BETWEEN 100 AND 60000", name="ck_config_delay"),
        CheckConstraint("max_duration_seconds BETWEEN 1 AND 3600", name="ck_config_duration"),
        CheckConstraint("max_response_bytes BETWEEN 1024 AND 10485760", name="ck_config_size"),
        CheckConstraint("max_redirects BETWEEN 0 AND 10", name="ck_config_redirects"),
        CheckConstraint("concurrency BETWEEN 1 AND 8", name="ck_config_concurrency"),
    )
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), primary_key=True
    )
    strategy: Mapped[Strategy] = mapped_column(enum_type(Strategy, "crawl_strategy"))
    scope: Mapped[Scope] = mapped_column(enum_type(Scope, "crawl_scope"))
    link_types: Mapped[LinkSelection] = mapped_column(enum_type(LinkSelection, "link_selection"))
    max_depth: Mapped[int] = mapped_column(Integer)
    max_pages: Mapped[int] = mapped_column(Integer)
    timeout_seconds: Mapped[float] = mapped_column(Float)
    request_delay_ms: Mapped[int] = mapped_column(Integer)
    max_duration_seconds: Mapped[int] = mapped_column(Integer)
    max_response_bytes: Mapped[int] = mapped_column(Integer)
    max_redirects: Mapped[int] = mapped_column(Integer)
    concurrency: Mapped[int] = mapped_column(Integer)
    respect_robots: Mapped[bool] = mapped_column(Boolean(create_constraint=True))
    follow_external_urls: Mapped[bool] = mapped_column(Boolean(create_constraint=True))
    process_one_page: Mapped[bool] = mapped_column(Boolean(create_constraint=True))
    session: Mapped[CrawlSession] = relationship(back_populates="config")


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (
        UniqueConstraint("session_id", "normalized_url", name="uq_pages_session_url"),
        UniqueConstraint("session_id", "id", name="uq_pages_session_id"),
        CheckConstraint("depth >= 0", name="ck_pages_depth"),
        CheckConstraint("discovery_order >= 0", name="ck_pages_discovery_order"),
        CheckConstraint("fetch_order IS NULL OR fetch_order >= 0", name="ck_pages_fetch_order"),
        CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599", name="ck_pages_http_status"
        ),
        Index("ix_pages_session_depth", "session_id", "depth"),
        Index("ix_pages_session_fetch_order", "session_id", "fetch_order"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    normalized_url: Mapped[str] = mapped_column(Text)
    original_url: Mapped[str] = mapped_column(Text)
    depth: Mapped[int] = mapped_column(Integer)
    discovery_order: Mapped[int] = mapped_column(Integer)
    fetch_order: Mapped[int | None] = mapped_column(Integer)
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(255))
    encoding: Mapped[str | None] = mapped_column(String(100))
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    session: Mapped[CrawlSession] = relationship(back_populates="pages")
    outgoing_links: Mapped[list["Link"]] = relationship(
        foreign_keys="[Link.session_id, Link.source_page_id]", viewonly=True
    )


class Link(Base):
    __tablename__ = "links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "source_page_id"],
            ["pages.session_id", "pages.id"],
            ondelete="CASCADE",
            name="fk_links_source_session",
        ),
        ForeignKeyConstraint(
            ["session_id", "target_page_id"],
            ["pages.session_id", "pages.id"],
            deferrable=True,
            initially="DEFERRED",
            name="fk_links_target_session",
        ),
        Index("ix_links_session_source", "session_id", "source_page_id"),
        Index("ix_links_session_target_url", "session_id", "target_url"),
        Index("ix_links_target_page_id", "target_page_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    source_page_id: Mapped[str] = mapped_column(String(36))
    target_url: Mapped[str] = mapped_column(Text)
    target_page_id: Mapped[str | None] = mapped_column(ForeignKey("pages.id", ondelete="SET NULL"))
    kind: Mapped[LinkKind] = mapped_column(enum_type(LinkKind, "link_kind"))
    is_external: Mapped[bool] = mapped_column(Boolean(create_constraint=True), default=False)
    is_followed: Mapped[bool] = mapped_column(Boolean(create_constraint=True), default=False)
    session: Mapped[CrawlSession] = relationship(back_populates="links", foreign_keys=[session_id])
    source_page: Mapped[Page] = relationship(
        foreign_keys=[session_id, source_page_id], viewonly=True
    )
    target_page: Mapped[Page | None] = relationship(foreign_keys=[target_page_id], viewonly=True)


class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    start_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, index=True)
    sessions: Mapped[list[CrawlSession]] = relationship(
        secondary=experiment_sessions, back_populates="experiments", passive_deletes=True
    )
