"""sessions

Revision ID: 0002_sessions
Revises: 0001_bootstrap
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_sessions"
down_revision: str | Sequence[str] | None = "0001_bootstrap"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("start_url", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("experiments", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_experiments_created_at"), ["created_at"], unique=False)

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("start_url", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "queued",
                "running",
                "completed",
                "failed",
                "cancelled",
                name="session_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("discovered_count", sa.Integer(), nullable=False),
        sa.Column("fetched_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "discovered_count >= 0 AND fetched_count >= 0 AND error_count >= 0",
            name="ck_sessions_counters",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.create_index("ix_sessions_created_at_id", ["created_at", "id"], unique=False)
        batch_op.create_index(
            "ix_sessions_status_created_at", ["status", "created_at"], unique=False
        )

    op.create_table(
        "crawl_config",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column(
            "strategy",
            sa.Enum("bfs", "dfs", name="crawl_strategy", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column(
            "scope",
            sa.Enum("server", "web", name="crawl_scope", native_enum=False, create_constraint=True),
            nullable=False,
        ),
        sa.Column(
            "link_types",
            sa.Enum(
                "hyperlinks",
                "images_and_hyperlinks",
                "all_links",
                name="link_selection",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("max_depth", sa.Integer(), nullable=False),
        sa.Column("max_pages", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Float(), nullable=False),
        sa.Column("request_delay_ms", sa.Integer(), nullable=False),
        sa.Column("max_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("max_response_bytes", sa.Integer(), nullable=False),
        sa.Column("max_redirects", sa.Integer(), nullable=False),
        sa.Column("concurrency", sa.Integer(), nullable=False),
        sa.Column("respect_robots", sa.Boolean(create_constraint=True), nullable=False),
        sa.Column("follow_external_urls", sa.Boolean(create_constraint=True), nullable=False),
        sa.Column("process_one_page", sa.Boolean(create_constraint=True), nullable=False),
        sa.CheckConstraint("concurrency BETWEEN 1 AND 8", name="ck_config_concurrency"),
        sa.CheckConstraint("max_depth BETWEEN 0 AND 20", name="ck_config_depth"),
        sa.CheckConstraint("max_duration_seconds BETWEEN 1 AND 3600", name="ck_config_duration"),
        sa.CheckConstraint("max_pages BETWEEN 1 AND 10000", name="ck_config_pages"),
        sa.CheckConstraint("max_redirects BETWEEN 0 AND 10", name="ck_config_redirects"),
        sa.CheckConstraint("max_response_bytes BETWEEN 1024 AND 10485760", name="ck_config_size"),
        sa.CheckConstraint("request_delay_ms BETWEEN 100 AND 60000", name="ck_config_delay"),
        sa.CheckConstraint("timeout_seconds BETWEEN 1 AND 60", name="ck_config_timeout"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_table(
        "experiment_sessions",
        sa.Column("experiment_id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("experiment_id", "session_id"),
    )
    with op.batch_alter_table("experiment_sessions", schema=None) as batch_op:
        batch_op.create_index("ix_experiment_sessions_session_id", ["session_id"], unique=False)

    op.create_table(
        "pages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("original_url", sa.Text(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("discovery_order", sa.Integer(), nullable=False),
        sa.Column("fetch_order", sa.Integer(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("encoding", sa.String(length=100), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("keywords", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.CheckConstraint("depth >= 0", name="ck_pages_depth"),
        sa.CheckConstraint("discovery_order >= 0", name="ck_pages_discovery_order"),
        sa.CheckConstraint("fetch_order IS NULL OR fetch_order >= 0", name="ck_pages_fetch_order"),
        sa.CheckConstraint(
            "http_status IS NULL OR http_status BETWEEN 100 AND 599", name="ck_pages_http_status"
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "id", name="uq_pages_session_id"),
        sa.UniqueConstraint("session_id", "normalized_url", name="uq_pages_session_url"),
    )
    with op.batch_alter_table("pages", schema=None) as batch_op:
        batch_op.create_index("ix_pages_session_depth", ["session_id", "depth"], unique=False)
        batch_op.create_index(
            "ix_pages_session_fetch_order", ["session_id", "fetch_order"], unique=False
        )

    op.create_table(
        "links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("source_page_id", sa.String(length=36), nullable=False),
        sa.Column("target_url", sa.Text(), nullable=False),
        sa.Column("target_page_id", sa.String(length=36), nullable=True),
        sa.Column(
            "kind",
            sa.Enum(
                "hyperlink",
                "image",
                "stylesheet",
                "script",
                "media",
                "other",
                name="link_kind",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("is_external", sa.Boolean(create_constraint=True), nullable=False),
        sa.Column("is_followed", sa.Boolean(create_constraint=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id", "source_page_id"],
            ["pages.session_id", "pages.id"],
            name="fk_links_source_session",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "target_page_id"],
            ["pages.session_id", "pages.id"],
            name="fk_links_target_session",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_page_id"], ["pages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("links", schema=None) as batch_op:
        batch_op.create_index(
            "ix_links_session_source", ["session_id", "source_page_id"], unique=False
        )
        batch_op.create_index(
            "ix_links_session_target_url", ["session_id", "target_url"], unique=False
        )
        batch_op.create_index("ix_links_target_page_id", ["target_page_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("links", schema=None) as batch_op:
        batch_op.drop_index("ix_links_target_page_id")
        batch_op.drop_index("ix_links_session_target_url")
        batch_op.drop_index("ix_links_session_source")

    op.drop_table("links")
    with op.batch_alter_table("pages", schema=None) as batch_op:
        batch_op.drop_index("ix_pages_session_fetch_order")
        batch_op.drop_index("ix_pages_session_depth")

    op.drop_table("pages")
    with op.batch_alter_table("experiment_sessions", schema=None) as batch_op:
        batch_op.drop_index("ix_experiment_sessions_session_id")

    op.drop_table("experiment_sessions")
    op.drop_table("crawl_config")
    with op.batch_alter_table("sessions", schema=None) as batch_op:
        batch_op.drop_index("ix_sessions_status_created_at")
        batch_op.drop_index("ix_sessions_created_at_id")

    op.drop_table("sessions")
    with op.batch_alter_table("experiments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_experiments_created_at"))

    op.drop_table("experiments")
    # ### end Alembic commands ###
