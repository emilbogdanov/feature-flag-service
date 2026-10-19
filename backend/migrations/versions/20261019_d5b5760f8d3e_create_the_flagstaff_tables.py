"""create projects, environments, flags, api keys and the audit log

Revision ID: d5b5760f8d3e
Revises:
Create Date: 2026-10-19 12:32:09.996690+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "d5b5760f8d3e"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Spelled out rather than read from the enums, so this migration keeps creating the schema it
# always created after members are added in later ones.
_FLAG_KINDS = "'boolean', 'string', 'number', 'json'"
_API_KEY_KINDS = "'admin', 'sdk'"
_AUDIT_ACTIONS = ", ".join(
    f"'{action}'"
    for action in [
        "project.created",
        "environment.created",
        "flag.created",
        "flag.details_changed",
        "flag.variants_changed",
        "flag.targeting_changed",
        "flag.enabled",
        "flag.disabled",
        "flag.archived",
        "api_key.issued",
        "api_key.revoked",
    ]
)


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.UniqueConstraint("key", name="uq_projects_key"),
    )
    op.create_table(
        "environments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_order", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("ruleset_version", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_environments"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_environments_project_id_projects"
        ),
        sa.UniqueConstraint("project_id", "key", name="uq_environments_project_id_key"),
    )
    op.create_table(
        "flags",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("variants", JSONB(), nullable=False),
        sa.Column("initial_targeting", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_flags"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name="fk_flags_project_id_projects"
        ),
        sa.UniqueConstraint("project_id", "key", name="uq_flags_project_id_key"),
        sa.CheckConstraint(f"kind IN ({_FLAG_KINDS})", name="ck_flags_flag_kind"),
    )
    op.create_table(
        "flag_targeting",
        sa.Column("flag_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("targeting", JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("flag_id", "environment_id", name="pk_flag_targeting"),
        sa.ForeignKeyConstraint(["flag_id"], ["flags.id"], name="fk_flag_targeting_flag_id_flags"),
        sa.ForeignKeyConstraint(
            ["environment_id"],
            ["environments.id"],
            name="fk_flag_targeting_environment_id_environments",
        ),
    )
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=True),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_api_keys"),
        sa.ForeignKeyConstraint(
            ["environment_id"], ["environments.id"], name="fk_api_keys_environment_id_environments"
        ),
        sa.UniqueConstraint("secret_hash", name="uq_api_keys_secret_hash"),
        sa.CheckConstraint(f"kind IN ({_API_KEY_KINDS})", name="ck_api_keys_api_key_kind"),
        sa.CheckConstraint(
            "(kind = 'sdk') = (environment_id IS NOT NULL)",
            name="ck_api_keys_sdk_keys_have_an_environment",
        ),
    )
    op.create_table(
        "audit_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor_key_id", sa.Uuid(), nullable=True),
        sa.Column("actor_name", sa.String(length=100), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=True),
        sa.Column("environment_id", sa.Uuid(), nullable=True),
        sa.Column("subject", sa.String(length=128), nullable=False),
        sa.Column("changes", JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_entries"),
        sa.CheckConstraint(f"action IN ({_AUDIT_ACTIONS})", name="ck_audit_entries_audit_action"),
    )


def downgrade() -> None:
    op.drop_table("audit_entries")
    op.drop_table("api_keys")
    op.drop_table("flag_targeting")
    op.drop_table("flags")
    op.drop_table("environments")
    op.drop_table("projects")
