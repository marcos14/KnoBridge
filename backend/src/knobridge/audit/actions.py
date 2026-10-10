"""Catalog of audit actions. The values are a stable contract: stored in the database, shown
in the panel and filtered on, so a value is never renamed or reused; retire it instead.

Format: ``<area>.<object>[.<detail>].<verb in the past tense>``, lowercase with ``_``.
"""

from __future__ import annotations

from enum import StrEnum


class AuditAction(StrEnum):
    # Instance setup and administration (system mode).
    SETUP_COMPLETED = "setup.completed"
    USER_CREATED = "user.created"
    USER_SUSPENDED = "user.suspended"
    USER_REACTIVATED = "user.reactivated"
    WORKSPACE_CREATED = "workspace.created"
    WORKSPACE_UPDATED = "workspace.updated"
    WORKSPACE_SUSPENDED = "workspace.suspended"
    # Authentication and account.
    AUTH_LOGIN_SUCCEEDED = "auth.login.succeeded"
    AUTH_LOGIN_FAILED = "auth.login.failed"
    AUTH_LOGOUT_SUCCEEDED = "auth.logout.succeeded"
    AUTH_SESSIONS_REVOKED = "auth.sessions.revoked"
    AUTH_PASSWORD_CHANGED = "auth.password.changed"  # noqa: S105 - action name, not a secret
    AUTH_PASSWORD_RESET_REQUESTED = "auth.password_reset.requested"  # noqa: S105 - action name
    AUTH_PASSWORD_RESET_COMPLETED = "auth.password_reset.completed"  # noqa: S105 - action name
    AUTH_EMAIL_VERIFIED = "auth.email.verified"
    # Workspace membership.
    MEMBERSHIP_INVITED = "membership.invited"
    MEMBERSHIP_INVITATION_ACCEPTED = "membership.invitation.accepted"
    MEMBERSHIP_ROLE_CHANGED = "membership.role.changed"
    MEMBERSHIP_REMOVED = "membership.removed"
