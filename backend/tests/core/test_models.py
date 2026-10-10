from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Column, Table

from knobridge.core.models import NAMING_CONVENTION, Base, str_enum


class _Color(StrEnum):
    DARK_BLUE = "dark-blue"
    RED = "red"


def test_str_enum_stores_values_not_member_names() -> None:
    column_type = str_enum(_Color, "color")

    assert column_type.enums == ["dark-blue", "red"]
    assert column_type.native_enum is False


def test_str_enum_check_constraint_follows_naming_convention() -> None:
    table = Table("paints", Base.metadata, Column("color", str_enum(_Color, "color")))
    try:
        names = {constraint.name for constraint in table.constraints}
    finally:
        Base.metadata.remove(table)

    assert "ck_paints_color" in names


def test_base_metadata_uses_naming_convention() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION
