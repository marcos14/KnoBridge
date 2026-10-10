"""Role hierarchy of a workspace: owner > admin > editor > viewer.

Each role includes every permission of the roles below it, so checks ask for a minimum role.
"""

from __future__ import annotations

from knobridge.tenancy.models import Role

_RANK: dict[Role, int] = {Role.VIEWER: 0, Role.EDITOR: 1, Role.ADMIN: 2, Role.OWNER: 3}


def role_at_least(role: Role, minimum: Role) -> bool:
    """``True`` when ``role`` is ``minimum`` or a more privileged one."""
    return _RANK[role] >= _RANK[minimum]
