"""ORM foundation: the declarative ``Base`` every domain model inherits, plus shared mixins.

Domain models live in their own modules (``tenancy/models.py``, ...); this module only holds
what they all share. Migrations are written by hand, but constraint names follow
``NAMING_CONVENTION`` so the models and the migrations agree on them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, MetaData, Uuid, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base with a shared, convention-named ``MetaData``."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    """``id`` UUID primary key, generated in Python (known before flush) or by the database."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )


class TimestampMixin:
    """``created_at`` / ``updated_at`` set by the database clock (``now()``)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


def str_enum(enum_class: type[StrEnum], name: str) -> Enum:
    """Map a ``StrEnum`` to ``VARCHAR`` + ``CHECK`` (constraint ``ck_<table>_<name>``).

    Values (not member names) are stored, and no native Postgres enum is created, so adding a
    value later is a plain constraint change in a migration.
    """
    return Enum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
        values_callable=_enum_values,
        validate_strings=True,
    )
