from __future__ import annotations

import pytest

from knobridge.tenancy.models import Role
from knobridge.tenancy.rbac import RoleNotAllowedError, ensure_role_within, role_at_least

ORDER = [Role.VIEWER, Role.EDITOR, Role.ADMIN, Role.OWNER]


@pytest.mark.parametrize("role", ORDER)
@pytest.mark.parametrize("minimum", ORDER)
def test_role_at_least_follows_hierarchy(role: Role, minimum: Role) -> None:
    allowed = role_at_least(role, minimum)

    assert allowed is (ORDER.index(role) >= ORDER.index(minimum))


def test_ensure_role_within_allows_same_or_lower_role() -> None:
    ensure_role_within(Role.ADMIN, Role.ADMIN)
    ensure_role_within(Role.ADMIN, Role.VIEWER)


def test_ensure_role_within_refuses_higher_role() -> None:
    with pytest.raises(RoleNotAllowedError) as caught:
        ensure_role_within(Role.ADMIN, Role.OWNER)

    assert caught.value.status_code == 403
    assert caught.value.code == "role_not_allowed"
    assert caught.value.details == {"max_role": "admin"}
