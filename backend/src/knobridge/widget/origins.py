"""Allowed origins of a widget: validation, normalization and matching of the ``Origin`` header
(``docs/specs/widget.md``, "Domínios permitidos e CORS").

An origin is ``http(s)://host[:port]`` without path, query or trailing slash. A wildcard is only
the whole first label (``https://*.cliente.com.br``) and matches any subdomain, at any depth,
never the bare domain. Origins compare case-insensitively with the default port dropped, so
they are stored normalized and without repetitions.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from knobridge.core.errors import ValidationError
from knobridge.widget.models import ORIGIN_MAX_LENGTH

_DEFAULT_PORTS = {"http": 80, "https": 443}
_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")
_WILDCARD = "*"


class OriginProblem(StrEnum):
    MALFORMED = "malformed"
    SCHEME_NOT_ALLOWED = "scheme_not_allowed"
    PATH_NOT_ALLOWED = "path_not_allowed"
    WILDCARD_NOT_ALLOWED = "wildcard_not_allowed"
    TOO_LONG = "too_long"
    DUPLICATE = "duplicate"


class WidgetOriginInvalidError(ValidationError):
    code = "widget_origin_invalid"


class _OriginRejectedError(Exception):
    def __init__(self, problem: OriginProblem) -> None:
        super().__init__(problem.value)
        self.problem = problem


@dataclass(frozen=True)
class Origin:
    """A parsed origin; ``host`` starts with ``*.`` for a wildcard, IPv6 hosts in brackets."""

    scheme: str
    host: str
    port: int | None  # ``None``: the scheme's default port

    @property
    def wildcard(self) -> bool:
        return self.host.startswith(_WILDCARD + ".")

    def render(self) -> str:
        port = "" if self.port is None else f":{self.port}"
        return f"{self.scheme}://{self.host}{port}"

    def covers(self, other: Origin) -> bool:
        """Whether this allowed origin admits the concrete origin ``other``."""
        if (self.scheme, self.port) != (other.scheme, other.port):
            return False
        if not self.wildcard:
            return self.host == other.host
        # ``*.a.com`` -> ``.a.com``: any subdomain at any depth, never ``a.com`` itself.
        return other.host.endswith(self.host[1:]) and not other.wildcard


def _host(raw: str) -> str:
    if raw.startswith("["):
        try:
            address = ipaddress.IPv6Address(raw[1:-1])
        except ValueError as exc:
            raise _OriginRejectedError(OriginProblem.MALFORMED) from exc
        return f"[{address.compressed}]"
    labels = raw.split(".")
    if labels[0] == _WILDCARD:
        if len(labels) == 1 or _WILDCARD in labels[1:]:
            raise _OriginRejectedError(OriginProblem.WILDCARD_NOT_ALLOWED)
        labels = labels[1:]
    elif _WILDCARD in raw:
        raise _OriginRejectedError(OriginProblem.WILDCARD_NOT_ALLOWED)
    if not all(_LABEL.fullmatch(label) for label in labels):
        raise _OriginRejectedError(OriginProblem.MALFORMED)
    return raw


def _parse(value: str) -> Origin:
    if len(value) > ORIGIN_MAX_LENGTH:
        raise _OriginRejectedError(OriginProblem.TOO_LONG)
    if value.strip() == _WILDCARD:
        raise _OriginRejectedError(OriginProblem.WILDCARD_NOT_ALLOWED)
    if "://" not in value or any(char.isspace() for char in value):
        raise _OriginRejectedError(OriginProblem.MALFORMED)
    lowered = value.lower()
    scheme = lowered.split("://", 1)[0]
    if scheme not in _DEFAULT_PORTS:
        raise _OriginRejectedError(OriginProblem.SCHEME_NOT_ALLOWED)
    # A wildcard is not a valid host for the URL parser: parse a stand-in label instead.
    probe = lowered.replace("://*.", "://wildcard-probe.", 1)
    try:
        parts = urlsplit(probe)
    except ValueError as exc:  # e.g. an invalid address in brackets
        raise _OriginRejectedError(OriginProblem.MALFORMED) from exc
    if parts.path or parts.query or parts.fragment or probe.endswith(("?", "#")):
        raise _OriginRejectedError(OriginProblem.PATH_NOT_ALLOWED)
    if parts.username is not None or parts.password is not None or not parts.hostname:
        raise _OriginRejectedError(OriginProblem.MALFORMED)
    try:
        port = parts.port
    except ValueError as exc:
        raise _OriginRejectedError(OriginProblem.MALFORMED) from exc
    netloc = parts.netloc.replace("wildcard-probe.", "*.", 1) if probe != lowered else parts.netloc
    host_part = netloc.rsplit(":", 1)[0] if port is not None or netloc.endswith(":") else netloc
    host = _host(host_part)
    return Origin(scheme, host, None if port == _DEFAULT_PORTS[scheme] else port)


def normalize_origins(values: Sequence[str]) -> list[str]:
    """The origins normalized, in order; 422 ``widget_origin_invalid`` listing every bad one."""
    normalized: list[str] = []
    problems: list[dict[str, str]] = []
    for value in values:
        try:
            origin = _parse(value).render()
        except _OriginRejectedError as rejected:
            problems.append({"origin": value, "reason": rejected.problem.value})
            continue
        if origin in normalized:
            problems.append({"origin": value, "reason": OriginProblem.DUPLICATE.value})
            continue
        normalized.append(origin)
    if problems:
        raise WidgetOriginInvalidError(
            "Some allowed origins are invalid.", details={"origins": problems}
        )
    return normalized


def request_origin(header: str | None) -> Origin | None:
    """The concrete origin of an ``Origin`` header, or ``None`` (absent, ``null``, wildcard or
    malformed)."""
    if header is None:
        return None
    try:
        origin = _parse(header)
    except _OriginRejectedError:
        return None
    return None if origin.wildcard else origin


def instance_origin(public_base_url: str) -> Origin | None:
    """The origin of the instance itself (``KNOBRIDGE_PUBLIC_BASE_URL`` without its path)."""
    parts = urlsplit(public_base_url)
    return request_origin(f"{parts.scheme}://{parts.netloc}")


def origin_allowed(
    origin: Origin, allowed_origins: Sequence[str], *, instance: Origin | None
) -> bool:
    """Whether ``origin`` is the instance's or covered by one of the widget's origins."""
    if instance is not None and origin == instance:
        return True
    return any(_parse(allowed).covers(origin) for allowed in allowed_origins)
