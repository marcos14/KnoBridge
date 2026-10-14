"""Allowed origins of a widget: normalization, each reason of ``widget_origin_invalid``, the
``Origin`` header and the matching, wildcards included (unit tests, no database)."""

from __future__ import annotations

import pytest

from knobridge.widget.origins import (
    Origin,
    WidgetOriginInvalidError,
    instance_origin,
    normalize_origins,
    origin_allowed,
    request_origin,
)


@pytest.mark.parametrize(
    ("raw", "normalized"),
    [
        ("https://app.cliente.com.br", "https://app.cliente.com.br"),
        ("HTTPS://App.Cliente.COM.br", "https://app.cliente.com.br"),
        ("https://a.example:443", "https://a.example"),
        ("http://a.example:80", "http://a.example"),
        ("http://intranet.cliente.local:8080", "http://intranet.cliente.local:8080"),
        ("https://a.example:", "https://a.example"),
        ("https://*.cliente.com.br", "https://*.cliente.com.br"),
        ("https://*.cliente.com.br:8443", "https://*.cliente.com.br:8443"),
        ("http://127.0.0.1:5173", "http://127.0.0.1:5173"),
        ("http://[0:0:0:0:0:0:0:1]:8080", "http://[::1]:8080"),
        ("http://[::1]", "http://[::1]"),
        ("http://localhost", "http://localhost"),
    ],
)
def test_normalize_origins_accepts_and_normalizes(raw: str, normalized: str) -> None:
    assert normalize_origins([raw]) == [normalized]


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("app.cliente.com.br", "malformed"),
        ("https://", "malformed"),
        ("https://user:pass@a.example", "malformed"),
        ("https://a_b.example", "malformed"),
        ("https://-a.example", "malformed"),
        ("https://a.example:99999", "malformed"),
        ("https://[::zz]", "malformed"),
        ("https://[v1.future]", "malformed"),
        ("https://a .example", "malformed"),
        ("ftp://a.example", "scheme_not_allowed"),
        ("javascript://a.example", "scheme_not_allowed"),
        ("https://a.example/", "path_not_allowed"),
        ("https://a.example/app", "path_not_allowed"),
        ("https://a.example?x=1", "path_not_allowed"),
        ("https://a.example?", "path_not_allowed"),
        ("https://a.example#top", "path_not_allowed"),
        ("*", "wildcard_not_allowed"),
        ("https://*", "wildcard_not_allowed"),
        ("https://a.*.example", "wildcard_not_allowed"),
        ("https://*.*.example", "wildcard_not_allowed"),
        ("https://a*.example", "wildcard_not_allowed"),
        ("https://" + "a" * 250 + ".example", "too_long"),
    ],
)
def test_normalize_origins_refuses_with_reason(raw: str, reason: str) -> None:
    with pytest.raises(WidgetOriginInvalidError) as caught:
        normalize_origins([raw])

    assert caught.value.code == "widget_origin_invalid"
    assert caught.value.details == {"origins": [{"origin": raw, "reason": reason}]}


def test_normalize_origins_refuses_duplicates_after_normalizing() -> None:
    with pytest.raises(WidgetOriginInvalidError) as caught:
        normalize_origins(["https://a.example", "HTTPS://A.example:443", "ftp://b.example"])

    assert caught.value.details == {
        "origins": [
            {"origin": "HTTPS://A.example:443", "reason": "duplicate"},
            {"origin": "ftp://b.example", "reason": "scheme_not_allowed"},
        ]
    }


@pytest.mark.parametrize(
    "header", [None, "null", "", "https://*.a.example", "https://a.example/x", "file://"]
)
def test_request_origin_ignores_unusable_headers(header: str | None) -> None:
    assert request_origin(header) is None


@pytest.mark.parametrize(
    ("header", "allowed"),
    [
        ("https://app.cliente.com.br", True),
        ("https://APP.cliente.com.br:443", True),
        ("http://app.cliente.com.br", False),
        ("https://app.cliente.com.br:8443", False),
        ("https://loja.cliente.com.br", False),
        ("https://x.portal.cliente.com", True),
        ("https://a.b.portal.cliente.com", True),
        ("https://portal.cliente.com", False),
        ("https://evilportal.cliente.com", False),
        ("https://x.portal.cliente.com.evil.example", False),
    ],
)
def test_origin_allowed_matches_exact_and_wildcard(header: str, allowed: bool) -> None:
    origin = request_origin(header)
    assert origin is not None

    result = origin_allowed(
        origin, ["https://app.cliente.com.br", "https://*.portal.cliente.com"], instance=None
    )

    assert result is allowed


def test_origin_allowed_always_admits_the_instance() -> None:
    instance = instance_origin("https://kb.empresa.com/painel")
    origin = request_origin("https://kb.empresa.com")
    assert origin is not None

    assert instance == Origin("https", "kb.empresa.com", None)
    assert origin_allowed(origin, ["https://outro.example"], instance=instance) is True


def test_instance_origin_of_an_unusable_url_is_none() -> None:
    assert instance_origin("https://kb_empresa.com") is None


def test_origin_wildcard_does_not_cover_a_wildcard() -> None:
    wildcard = Origin("https", "*.a.example", None)

    assert wildcard.covers(Origin("https", "*.b.a.example", None)) is False
