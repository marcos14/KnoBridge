from __future__ import annotations

import pytest

from knobridge.tenancy.models import Role
from knobridge.tenancy.rbac import role_at_least

ORDER = [Role.VIEWER, Role.EDITOR, Role.ADMIN, Role.OWNER]


@pytest.mark.parametrize("role", ORDER)
@pytest.mark.parametrize("minimum", ORDER)
def test_role_at_least_follows_hierarchy(role: Role, minimum: Role) -> None:
    allowed = role_at_least(role, minimum)

    assert allowed is (ORDER.index(role) >= ORDER.index(minimum))
