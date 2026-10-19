"""index the audit log for paging, overall and per project

Revision ID: 4b7e2c9a1f05
Revises: d5b5760f8d3e
Create Date: 2026-10-19 14:10:41.203877+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "4b7e2c9a1f05"
down_revision: str | None = "d5b5760f8d3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_audit_entries_at_id", "audit_entries", ["at", "id"])
    op.create_index(
        "ix_audit_entries_project_id_at_id", "audit_entries", ["project_id", "at", "id"]
    )


def downgrade() -> None:
    op.drop_index("ix_audit_entries_project_id_at_id", table_name="audit_entries")
    op.drop_index("ix_audit_entries_at_id", table_name="audit_entries")
