"""Durable crawler state and progress journal."""

import sqlalchemy as sa
from alembic import op

revision = "0003_crawler"
down_revision = "0002_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(sa.Column("stop_reason", sa.String(40), nullable=True))
        batch.add_column(sa.Column("link_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("crawler_version", sa.String(30), nullable=True))
        batch.add_column(sa.Column("user_agent", sa.String(255), nullable=True))
    with op.batch_alter_table("pages") as batch:
        batch.add_column(sa.Column("final_url", sa.Text(), nullable=True))
    op.create_table(
        "crawl_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_crawl_events_session_id_id", "crawl_events", ["session_id", "id"])


def downgrade() -> None:
    op.drop_table("crawl_events")
    # Native DROP COLUMN avoids recreating parent tables and cascading away child rows.
    op.drop_column("pages", "final_url")
    for column in ["user_agent", "crawler_version", "link_count", "stop_reason"]:
        op.drop_column("sessions", column)
