"""add_topic_sync_catalog

Revision ID: b1c5e3f9a742
Revises: 4f2c1b9a7e6d
Create Date: 2026-08-12

Adds source/target topic identity, an observed-topic catalog, and durable
synchronization reports. New internal tables receive the same RLS and public
role privilege restrictions as the original application tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b1c5e3f9a742"
down_revision: str | None = "4f2c1b9a7e6d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create durable topic-sync structures and secure them from public roles."""
    op.add_column("categories", sa.Column("source_group_id", sa.BigInteger(), nullable=True))
    op.add_column("categories", sa.Column("source_thread_id", sa.BigInteger(), nullable=True))
    op.add_column("categories", sa.Column("target_group_id", sa.BigInteger(), nullable=True))
    op.create_unique_constraint(
        "uq_categories_source_group_thread",
        "categories",
        ["source_group_id", "source_thread_id"],
    )

    op.add_column("media", sa.Column("source_group_id", sa.BigInteger(), nullable=True))
    op.add_column("media", sa.Column("source_thread_id", sa.BigInteger(), nullable=True))
    op.execute(
        "CREATE UNIQUE INDEX uq_media_source_message "
        "ON media (source_group_id, source_message_id) "
        "WHERE source_group_id IS NOT NULL AND source_message_id IS NOT NULL"
    )

    op.create_table(
        "topic_catalog",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("thread_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("normalized_name", sa.Text(), nullable=False),
        sa.Column("icon_color", sa.Integer(), nullable=True),
        sa.Column("is_closed", sa.Boolean(), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chat_id", "thread_id", name="uq_topic_catalog_chat_thread"),
    )
    op.create_index(
        "ix_topic_catalog_chat_normalized",
        "topic_catalog",
        ["chat_id", "normalized_name"],
        unique=False,
    )

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("requested_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("source_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("target_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("started_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_sync_runs_active_topic_broadcast "
        "ON sync_runs (run_type) "
        "WHERE run_type = 'TOPIC_BROADCAST' AND status = 'RUNNING'"
    )
    op.create_table(
        "media_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column("sync_run_id", sa.Integer(), nullable=True),
        sa.Column("target_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("target_thread_id", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("target_message_id", sa.BigInteger(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("sent_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sync_run_id"], ["sync_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "media_id",
            "target_chat_id",
            "target_thread_id",
            name="uq_media_delivery_destination",
        ),
    )
    op.create_index(
        "ix_media_deliveries_run", "media_deliveries", ["sync_run_id", "state"], unique=False
    )

    for table_name in ("topic_catalog", "sync_runs", "media_deliveries"):
        op.execute(f'ALTER TABLE public."{table_name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON TABLE public."{table_name}" FROM anon, authenticated')

    for sequence_name in (
        "topic_catalog_id_seq",
        "sync_runs_id_seq",
        "media_deliveries_id_seq",
    ):
        op.execute(
            f'REVOKE USAGE, SELECT ON SEQUENCE public."{sequence_name}" '
            "FROM anon, authenticated"
        )


def downgrade() -> None:
    """Remove topic-sync structures and restore the prior schema exactly."""
    for sequence_name in (
        "media_deliveries_id_seq",
        "sync_runs_id_seq",
        "topic_catalog_id_seq",
    ):
        op.execute(
            f'GRANT USAGE, SELECT ON SEQUENCE public."{sequence_name}" '
            "TO anon, authenticated"
        )

    for table_name in ("media_deliveries", "sync_runs", "topic_catalog"):
        op.execute(f'ALTER TABLE public."{table_name}" DISABLE ROW LEVEL SECURITY')
        op.execute(f'GRANT ALL ON TABLE public."{table_name}" TO anon, authenticated')

    op.drop_index("ix_media_deliveries_run", table_name="media_deliveries")
    op.execute("DROP INDEX uq_sync_runs_active_topic_broadcast")
    op.drop_table("media_deliveries")
    op.drop_table("sync_runs")
    op.drop_index("ix_topic_catalog_chat_normalized", table_name="topic_catalog")
    op.drop_table("topic_catalog")

    op.execute("DROP INDEX uq_media_source_message")
    op.drop_column("media", "source_thread_id")
    op.drop_column("media", "source_group_id")

    op.drop_constraint(
        "uq_categories_source_group_thread", "categories", type_="unique"
    )
    op.drop_column("categories", "target_group_id")
    op.drop_column("categories", "source_thread_id")
    op.drop_column("categories", "source_group_id")
