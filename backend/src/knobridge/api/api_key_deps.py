"""Dependencies of the public API: the bearer API key (``docs/specs/api-publica.md``).

Chain::

    current_api_key -> api_key_context

These routes never read the session cookie nor require CSRF: the ``kbk_`` key is the only
credential they accept, and the key opens no panel route. ``current_api_key`` authenticates in
a short system-mode transaction that also records ``last_used_at`` (at most once a minute) and
commits; ``api_key_context`` then opens the request's transaction scoped to the key's
workspace, without ``app.user_id``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge.api.deps import ClockDep, SessionFactoryDep
from knobridge.apikeys.auth import (
    ApiKeyIdentity,
    authenticate_api_key,
    invalid_api_key,
    touch_last_used,
)
from knobridge.core.db import scoped_session, system_session


def bearer_key(request: Request) -> str:
    """The key of ``Authorization: Bearer <key>``; 401 when absent or another scheme."""
    scheme, _, key = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not key.strip():
        raise invalid_api_key()
    return key.strip()


async def current_api_key(
    request: Request, factory: SessionFactoryDep, clock: ClockDep
) -> ApiKeyIdentity:
    """The key of the request, found by its prefix in system mode (committed on return)."""
    key = bearer_key(request)
    async with system_session(factory) as db:
        identity = await authenticate_api_key(db, key=key)
        await touch_last_used(db, identity, clock.now())
    return identity


ApiKeyIdentityDep = Annotated[ApiKeyIdentity, Depends(current_api_key)]


@dataclass(frozen=True)
class ApiKeyContext:
    """The authenticated key and a session scoped to its workspace."""

    identity: ApiKeyIdentity
    db: AsyncSession

    @property
    def workspace_id(self) -> uuid.UUID:
        return self.identity.workspace_id


async def api_key_context(
    identity: ApiKeyIdentityDep, factory: SessionFactoryDep
) -> AsyncGenerator[ApiKeyContext]:
    """A transaction scoped to the key's workspace; commits before the response is sent."""
    async with scoped_session(factory, workspace_id=identity.workspace_id, user_id=None) as db:
        yield ApiKeyContext(identity=identity, db=db)


ApiKeyContextDep = Annotated[ApiKeyContext, Depends(api_key_context, scope="function")]
