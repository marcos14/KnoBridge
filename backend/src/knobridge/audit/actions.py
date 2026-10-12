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
    USER_SUPERADMIN_GRANTED = "user.superadmin.granted"
    USER_SUPERADMIN_REVOKED = "user.superadmin.revoked"
    WORKSPACE_CREATED = "workspace.created"
    WORKSPACE_UPDATED = "workspace.updated"
    WORKSPACE_SUSPENDED = "workspace.suspended"
    WORKSPACE_REACTIVATED = "workspace.reactivated"
    # Authentication and account.
    AUTH_LOGIN_SUCCEEDED = "auth.login.succeeded"
    AUTH_LOGIN_FAILED = "auth.login.failed"
    AUTH_LOGOUT_SUCCEEDED = "auth.logout.succeeded"
    AUTH_SESSIONS_REVOKED = "auth.sessions.revoked"
    AUTH_PASSWORD_CHANGED = "auth.password.changed"  # noqa: S105 - action name, not a secret
    AUTH_PASSWORD_RESET_REQUESTED = "auth.password_reset.requested"  # noqa: S105 - action name
    AUTH_PASSWORD_RESET_COMPLETED = "auth.password_reset.completed"  # noqa: S105 - action name
    AUTH_EMAIL_VERIFIED = "auth.email.verified"
    AUTH_EMAIL_VERIFICATION_REQUESTED = "auth.email_verification.requested"
    USER_PROFILE_UPDATED = "user.profile.updated"
    # Workspace membership.
    MEMBERSHIP_INVITED = "membership.invited"
    MEMBERSHIP_INVITATION_ACCEPTED = "membership.invitation.accepted"
    MEMBERSHIP_INVITATION_RESENT = "membership.invitation.resent"
    MEMBERSHIP_INVITATION_REVOKED = "membership.invitation.revoked"
    MEMBERSHIP_ROLE_CHANGED = "membership.role.changed"
    MEMBERSHIP_REMOVED = "membership.removed"
    # LLM provider credentials (the key itself never goes into metadata).
    PROVIDER_CREATED = "provider.created"
    PROVIDER_UPDATED = "provider.updated"
    PROVIDER_DELETED = "provider.deleted"
    PROVIDER_TESTED = "provider.tested"
    # Assistants (prompts and messages stay out of metadata: names, models and fields only).
    ASSISTANT_CREATED = "assistant.created"
    ASSISTANT_UPDATED = "assistant.updated"
    ASSISTANT_DELETED = "assistant.deleted"
    # Conversations: only the deletion is audited (no content: ids and counts only).
    CONVERSATION_DELETED = "conversation.deleted"
    # Knowledge index configuration: collections, sources and their runs (names, kinds,
    # changed fields and ids; never document content). Indexed documents are not audited.
    COLLECTION_CREATED = "collection.created"
    COLLECTION_UPDATED = "collection.updated"
    COLLECTION_DELETED = "collection.deleted"
    SOURCE_CREATED = "source.created"
    SOURCE_UPDATED = "source.updated"
    SOURCE_DELETED = "source.deleted"
    SOURCE_TESTED = "source.tested"
    SOURCE_SYNC_STARTED = "source.sync.started"
    SOURCE_SYNC_CANCELLED = "source.sync.cancelled"
    # Ingest token of a ``tickets`` source issued or rotated (the prefix only, never the token).
    SOURCE_INGEST_TOKEN_ROTATED = "source.ingest_token_rotated"  # noqa: S105 - action name
    # File of tickets uploaded in the panel (file name and counts, never the content).
    SOURCE_TICKETS_UPLOADED = "source.tickets_uploaded"
    # Runners of the code harness (name, prefix and changed fields; never the token or hash).
    RUNNER_CREATED = "runner.created"
    RUNNER_UPDATED = "runner.updated"
    RUNNER_REVOKED = "runner.revoked"
    RUNNER_DELETED = "runner.deleted"
    # Harness jobs (module key and ids; never knowledge content).
    HARNESS_JOB_CANCELLED = "harness_job.cancelled"
    HARNESS_JOB_ENQUEUED = "harness_job.enqueued"
    # Modules of runner sources (key, source and changed fields).
    HARNESS_MODULE_CREATED = "harness_module.created"
    HARNESS_MODULE_UPDATED = "harness_module.updated"
    # Review of a knowledge item (key, action and edited fields; never the text).
    KNOWLEDGE_ITEM_UPDATED = "knowledge_item.updated"
