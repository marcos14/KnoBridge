"""CORS of the widget's public routes (``docs/specs/widget.md``, "Respostas CORS").

``/v1/widget/*`` leaves the global ``CORSMiddleware`` (which serves the panel with credentials
and ``KNOBRIDGE_CORS_ORIGINS``): :class:`PanelCORSMiddleware` skips those paths. Their CORS
headers come from :class:`WidgetCORSMiddleware`, and only once the route found the widget and
accepted the ``Origin`` (:func:`allow_origin` marks the request): an unknown key or an origin
outside the list answers without CORS, so the browser hides the answer from the page. Never
``Access-Control-Allow-Credentials``: the widget uses no cookie.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from fastapi import Request
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

WIDGET_PATH_PREFIX = "/v1/widget/"
# Key of the request state holding the accepted origin.
_ALLOWED_ORIGIN = "widget_allowed_origin"
PREFLIGHT_HEADERS = {
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Authorization, Content-Type",
    "Access-Control-Max-Age": "600",
}


def is_widget_path(scope: Scope) -> bool:
    return scope["type"] == "http" and str(scope["path"]).startswith(WIDGET_PATH_PREFIX)


def allow_origin(request: Request, origin: str) -> None:
    """Answer this request with CORS for ``origin`` (the widget accepted it)."""
    setattr(request.state, _ALLOWED_ORIGIN, origin)


class PanelCORSMiddleware(CORSMiddleware):
    """Starlette's CORS for the panel, everywhere but the widget's public routes."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if is_widget_path(scope):
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


class WidgetCORSMiddleware:
    """Adds the widget's CORS headers to the answers of an accepted origin."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not is_widget_path(scope):
            await self.app(scope, receive, send)
            return

        async def send_with_cors(message: Message) -> None:
            if message["type"] == "http.response.start":
                # ``Any``: the ASGI state is a plain dict shared with ``request.state``.
                state: MutableMapping[str, Any] = scope.get("state", {})
                origin = state.get(_ALLOWED_ORIGIN)
                if isinstance(origin, str):
                    headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                    headers += [
                        (b"access-control-allow-origin", origin.encode("latin-1")),
                        (b"vary", b"Origin"),
                        (b"access-control-expose-headers", b"Retry-After"),
                    ]
                    message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_cors)
