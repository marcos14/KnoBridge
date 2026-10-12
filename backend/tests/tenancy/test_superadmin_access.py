"""Effective role of a superadmin's access and the session mark honoured only for superadmins."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from knobridge.security.models import Session
from knobridge.tenancy.auth import SuperadminAccess, superadmin_access
from knobridge.tenancy.models import Role, User
from knobridge.tenancy.superadmin_access import effective_role

ENTERED = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("membership", "expected"),
    [
        (None, Role.ADMIN),
        (Role.VIEWER, Role.ADMIN),
        (Role.EDITOR, Role.ADMIN),
        (Role.ADMIN, Role.ADMIN),
        (Role.OWNER, Role.OWNER),
    ],
)
def test_effective_role_is_the_higher_of_membership_and_admin(
    membership: Role | None, expected: Role
) -> None:
    assert effective_role(membership) == expected


def _session(workspace_id: uuid.UUID | None) -> Session:
    return Session(
        superadmin_workspace_id=workspace_id,
        superadmin_entered_at=None if workspace_id is None else ENTERED,
    )


def test_superadmin_access_read_from_superadmin_session() -> None:
    workspace_id = uuid.uuid4()

    access = superadmin_access(User(is_superadmin=True), _session(workspace_id))

    assert access == SuperadminAccess(workspace_id=workspace_id, entered_at=ENTERED)


@pytest.mark.parametrize(("is_superadmin", "workspace_id"), [(False, uuid.uuid4()), (True, None)])
def test_superadmin_access_absent_without_flag_or_mark(
    is_superadmin: bool, workspace_id: uuid.UUID | None
) -> None:
    assert superadmin_access(User(is_superadmin=is_superadmin), _session(workspace_id)) is None
