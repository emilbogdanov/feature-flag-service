from datetime import datetime
from typing import Any
from uuid import UUID

from flagstaff.engine.variants import FlagKind
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from flagstaff_server.domain.api_keys import ApiKeyKind
from flagstaff_server.domain.audit import AuditAction
from flagstaff_server.domain.values import DESCRIPTION_MAX_LENGTH, NAME_MAX_LENGTH, SLUG_MAX_LENGTH

# Deterministic constraint names, so migrations can refer to them and autogenerate never sees
# a renamed constraint as a new one.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# The engine allows flag keys this long; the database must not be the one to refuse them.
FLAG_KEY_MAX_LENGTH = 128
# SHA-256 as hex.
SECRET_HASH_LENGTH = 64


# VARCHAR plus a CHECK constraint rather than a native Postgres enum, so adding a member is a
# one-line migration instead of an ALTER TYPE.
def _string_enum(enum: type[Any], name: str, length: int) -> Enum:
    return Enum(
        enum,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda members: [member.value for member in members],
    )


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {datetime: DateTime(timezone=True)}  # noqa: RUF012


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(SLUG_MAX_LENGTH), unique=True)
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    created_at: Mapped[datetime]


class EnvironmentRow(Base):
    __tablename__ = "environments"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    key: Mapped[str] = mapped_column(String(SLUG_MAX_LENGTH))
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    created_at: Mapped[datetime]
    # dev, staging and prod are created in the same instant, so the creation time alone can't
    # keep them in the order they were made.
    created_order: Mapped[int] = mapped_column(BigInteger, Identity())
    ruleset_version: Mapped[int] = mapped_column(BigInteger)

    # The unique index also serves every lookup and listing by project.
    __table_args__ = (UniqueConstraint("project_id", "key"),)


class FlagRow(Base):
    __tablename__ = "flags"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(ForeignKey("projects.id"))
    key: Mapped[str] = mapped_column(String(FLAG_KEY_MAX_LENGTH))
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    description: Mapped[str] = mapped_column(String(DESCRIPTION_MAX_LENGTH))
    kind: Mapped[FlagKind] = mapped_column(_string_enum(FlagKind, "flag_kind", 16))
    # Variants and targeting are written in the engine's wire format and only ever read whole,
    # so JSONB keeps them as one value instead of a table per rule, condition and split.
    variants: Mapped[list[Any]] = mapped_column(JSONB)
    initial_targeting: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    archived_at: Mapped[datetime | None]
    version: Mapped[int] = mapped_column(Integer)

    __table_args__ = (UniqueConstraint("project_id", "key"),)


class FlagTargetingRow(Base):
    __tablename__ = "flag_targeting"

    flag_id: Mapped[UUID] = mapped_column(ForeignKey("flags.id"), primary_key=True)
    environment_id: Mapped[UUID] = mapped_column(ForeignKey("environments.id"), primary_key=True)
    targeting: Mapped[dict[str, Any]] = mapped_column(JSONB)


class ApiKeyRow(Base):
    __tablename__ = "api_keys"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    kind: Mapped[ApiKeyKind] = mapped_column(_string_enum(ApiKeyKind, "api_key_kind", 8))
    name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    environment_id: Mapped[UUID | None] = mapped_column(ForeignKey("environments.id"))
    # The unique index doubles as the lookup on every authenticated request.
    secret_hash: Mapped[str] = mapped_column(String(SECRET_HASH_LENGTH), unique=True)
    created_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]

    __table_args__ = (
        CheckConstraint(
            "(kind = 'sdk') = (environment_id IS NOT NULL)", name="sdk_keys_have_an_environment"
        ),
    )


class AuditEntryRow(Base):
    __tablename__ = "audit_entries"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    action: Mapped[AuditAction] = mapped_column(_string_enum(AuditAction, "audit_action", 32))
    # No foreign key: the log outlives whatever it names, and must not stop anything from
    # being deleted later.
    actor_key_id: Mapped[UUID | None]
    actor_name: Mapped[str] = mapped_column(String(NAME_MAX_LENGTH))
    at: Mapped[datetime]
    project_id: Mapped[UUID | None]
    environment_id: Mapped[UUID | None]
    subject: Mapped[str] = mapped_column(String(FLAG_KEY_MAX_LENGTH))
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB)

    # One per way the log is paged: everything newest first, or one project's newest first.
    # Postgres walks either backwards, so ascending columns serve the descending order.
    __table_args__ = (
        Index("ix_audit_entries_at_id", "at", "id"),
        Index("ix_audit_entries_project_id_at_id", "project_id", "at", "id"),
    )
