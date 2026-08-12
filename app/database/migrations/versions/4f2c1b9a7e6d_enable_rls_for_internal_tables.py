"""enable_rls_for_internal_tables

Revision ID: 4f2c1b9a7e6d
Revises: 8bafd82c2a3a
Create Date: 2026-08-12

The bot accesses PostgreSQL only through its trusted backend role. Public
Supabase API roles must not read or write operational, audit, or media data.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f2c1b9a7e6d"
down_revision: str | None = "8bafd82c2a3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INTERNAL_TABLES = (
    "admins",
    "audit_log",
    "backups",
    "categories",
    "duplicate_groups",
    "settings",
    "tags",
    "media",
    "publish_jobs",
    "duplicate_group_members",
    "media_tags",
    "publish_queue_items",
    "sorting_sessions",
    "alembic_version",
)


def upgrade() -> None:
    """Protect all internal tables from Supabase API roles."""
    for table_name in _INTERNAL_TABLES:
        op.execute(f'ALTER TABLE public."{table_name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'REVOKE ALL ON TABLE public."{table_name}" FROM anon, authenticated')

    op.execute("REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated")


def downgrade() -> None:
    """Disable RLS and restore the default public-role table privileges."""
    for table_name in _INTERNAL_TABLES:
        op.execute(f'ALTER TABLE public."{table_name}" DISABLE ROW LEVEL SECURITY')
        op.execute(f'GRANT ALL ON TABLE public."{table_name}" TO anon, authenticated')

    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO anon, authenticated")
