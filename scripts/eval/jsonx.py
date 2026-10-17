"""Typed access to decoded JSON, so the rest of the package never touches ``Any``."""

from __future__ import annotations

from typing import cast


class ShapeError(ValueError):
    """A JSON value does not have the expected shape; ``path`` points at it."""

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


def as_object(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ShapeError(path, "expected an object")
    return cast("dict[str, object]", value)


def as_list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise ShapeError(path, "expected a list")
    return cast("list[object]", value)


def get_str(data: dict[str, object], key: str, path: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ShapeError(f"{path}.{key}", "expected a string")
    return value


def get_opt_str(data: dict[str, object], key: str, path: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ShapeError(f"{path}.{key}", "expected a string or null")
    return value


def get_opt_int(data: dict[str, object], key: str, path: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ShapeError(f"{path}.{key}", "expected an integer or null")
    return value


def get_int(data: dict[str, object], key: str, path: str) -> int:
    value = get_opt_int(data, key, path)
    if value is None:
        raise ShapeError(f"{path}.{key}", "expected an integer")
    return value


def get_opt_float(data: dict[str, object], key: str, path: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ShapeError(f"{path}.{key}", "expected a number or null")
    return float(value)


def get_object(data: dict[str, object], key: str, path: str) -> dict[str, object]:
    return as_object(data.get(key), f"{path}.{key}")


def get_opt_object(data: dict[str, object], key: str, path: str) -> dict[str, object] | None:
    value = data.get(key)
    return None if value is None else as_object(value, f"{path}.{key}")


def get_list(data: dict[str, object], key: str, path: str) -> list[object]:
    return as_list(data.get(key), f"{path}.{key}")
