"""Role hierarchy of a workspace: owner > admin > editor > viewer.

Each role includes every permission of the roles below it, so checks ask for a minimum role.
"""

from __future__ import annotations

from knobridge.core.errors import ForbiddenError
from knobridge.tenancy.models import Role

_RANK: dict[Role, int] = {Role.VIEWER: 0, Role.EDITOR: 1, Role.ADMIN: 2, Role.OWNER: 3}


class RoleNotAllowedError(ForbiddenError):
    """The actor tried to grant, or to act on a member holding, a role above their own."""

    code = "role_not_allowed"


def role_at_least(role: Role, minimum: Role) -> bool:
    """``True`` when ``role`` is ``minimum`` or a more privileged one."""
    return _RANK[role] >= _RANK[minimum]


def ensure_role_within(actor_role: Role, role: Role) -> None:
    """Nobody grants, nor manages a member with, a role above their own.

    Raises :class:`RoleNotAllowedError` (403) with the highest role the actor may handle.
    """
    if not role_at_least(actor_role, role):
        raise RoleNotAllowedError(
            "Your role does not allow handling this role.",
            details={"max_role": actor_role.value},
        )
