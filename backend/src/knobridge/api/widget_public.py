"""Public routes of the embeddable widget (``/v1/widget/{public_key}/…``, ``docs/specs/widget.md``).

No cookie, no CSRF: the browser of a visitor on the host's site calls them. Every request goes
through :func:`public_widget` (key, ``Origin``, availability and the general request limit,
``widget/public.py``) before the route. CORS comes from ``widget/cors.py``, outside the global
``CORSMiddleware``. This plan step (0010 F3.1) serves the preflight of every public path and
the configuration; the visitor's conversation comes in F3.2.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from knobridge.api.deps import ClientIpDep, ClockDep, SessionFactoryDep, SettingsDep
from knobridge.levels.level import ResponseLevel
from knobridge.widget.cors import PREFLIGHT_HEADERS, allow_origin
from knobridge.widget.models import WidgetMode, WidgetPosition, WidgetTheme
from knobridge.widget.origins import instance_origin
from knobridge.widget.public import (
    QUESTION_MAX_CHARS,
    PublicWidget,
    accepted_origin,
    ensure_available,
    resolve_public_widget,
)
from knobridge.widget.rate_limit import RateLimiter, widget_request_limit

CONFIG_CACHE_CONTROL = "private, max-age=60"
_STATE_LIMITER = "widget_rate_limiter"

PUBLIC_ERRORS: dict[int | str, dict[str, object]] = {
    403: {"description": "`Origin` absent or not allowed (`widget_origin_not_allowed`), no CORS."},
    404: {
        "description": "Unknown public key (`not_found`, no CORS) or widget, product or "
        "workspace unavailable (`widget_unavailable`)."
    },
    429: {"description": "Request limit (`rate_limited`, `details.limit`, `Retry-After`)."},
}


def get_rate_limiter(request: Request, clock: ClockDep, settings: SettingsDep) -> RateLimiter:
    """The process-wide limiter (it remembers when it last cleaned old windows up)."""
    state = request.app.state
    limiter: RateLimiter | None = getattr(state, _STATE_LIMITER, None)
    if limiter is None:
        limiter = RateLimiter(clock, secret_key=settings.secret_key.get_secret_value())
        setattr(state, _STATE_LIMITER, limiter)
    return limiter


RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]


async def public_widget(
    public_key: str,
    request: Request,
    factory: SessionFactoryDep,
    settings: SettingsDep,
    limiter: RateLimiterDep,
    ip: ClientIpDep,
) -> PublicWidget:
    """The widget of the path after the four checks of every public request."""
    found = await resolve_public_widget(factory, public_key)
    header = request.headers.get("origin")
    accepted_origin(found, header, instance=instance_origin(settings.public_base_url))
    # From here on, answers (errors included) carry CORS for the origin as the browser sent it.
    allow_origin(request, str(header))
    ensure_available(found)
    await limiter.check(
        factory,
        widget_request_limit(settings.widget_requests_per_minute),
        widget_id=found.widget.id,
        ip=ip,
    )
    return found


PublicWidgetDep = Annotated[PublicWidget, Depends(public_widget)]


class WidgetPublicConfig(BaseModel):
    """What the widget needs to render; nothing about collections, model, limits or cost."""

    public_key: str
    product_name: str
    language: str
    # Already resolved: the product's name when the widget has no title.
    title: str
    greeting: str
    placeholder: str
    mode: WidgetMode
    position: WidgetPosition
    theme: WidgetTheme
    primary_color: str
    feedback_enabled: bool
    # Effective: the widget offers tickets and the product has its webhook.
    ticket_enabled: bool
    # The widget has a signing secret, so it accepts a signed identity.
    identity_enabled: bool
    level: ResponseLevel
    question_max_chars: int


router = APIRouter(prefix="/widget", tags=["widget-public"])


@router.options(
    "/{public_key}/{path:path}", status_code=HTTPStatus.NO_CONTENT, include_in_schema=False
)
async def widget_preflight(public_key: str, path: str, _found: PublicWidgetDep) -> Response:
    """CORS preflight of any public path, answered after the same checks as the request."""
    return Response(status_code=HTTPStatus.NO_CONTENT, headers=PREFLIGHT_HEADERS)


@router.get("/{public_key}/config", responses=PUBLIC_ERRORS)
async def widget_config(
    public_key: str, found: PublicWidgetDep, response: Response
) -> WidgetPublicConfig:
    """Appearance and features of the widget, read when it loads (cacheable for a minute)."""
    widget, product = found.widget, found.product
    response.headers["Cache-Control"] = CONFIG_CACHE_CONTROL
    return WidgetPublicConfig(
        public_key=widget.public_key,
        product_name=product.name,
        language=product.language,
        title=widget.title or product.name,
        greeting=widget.greeting,
        placeholder=widget.placeholder,
        mode=widget.mode,
        position=widget.position,
        theme=widget.theme,
        primary_color=widget.primary_color,
        feedback_enabled=widget.feedback_enabled,
        ticket_enabled=found.ticket_available,
        identity_enabled=widget.signing_secret_ciphertext is not None,
        level=ResponseLevel.END_USER,
        question_max_chars=QUESTION_MAX_CHARS,
    )
