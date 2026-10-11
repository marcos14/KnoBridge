"""The code harness of a workspace: ``Runner``, ``HarnessModule``, ``HarnessJob``,
``KnowledgeItem`` and ``HarnessRejection`` (``docs/adr/0005-runner-local-do-harness.md``).

Workspace data with forced row-level security (``docs/adr/0001-tenancy-e-rls.md``). A runner
is a machine that runs the agent; its token is stored only as a SHA-256 hash, and
``token_prefix`` is unique in the whole instance because authentication looks the runner up
in system mode, before the workspace is known (``docs/specs/runner.md``). Every reference
between these tables, and to ``sources``, is composite, ``(workspace_id, <parent>_id)``, so the
database refuses a parent of another workspace. Modules, jobs and items cascade from their
source; a job outlives the runner that leased it and an item outlives its job (both
``SET NULL`` on that column only).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from knobridge.audit.models import JSONValue
from knobridge.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum

TOKEN_PREFIX_LENGTH = 8
SHA256_HEX_LENGTH = 64
MODULE_KEY_MAX_LENGTH = 100
MODULE_PATHS_MAX = 50
# ``<module_key>.R0001``: the module key plus the widest suffix.
ITEM_KEY_MAX_LENGTH = 120
TITLE_MAX_LENGTH = 200
MODEL_MAX_LENGTH = 100
ERROR_MAX_LENGTH = 500
# Formats shared with the wire contract (docs/specs/runner.md, "Formatos validados").
COMMIT_PATTERN = "^[0-9a-f]{40}([0-9a-f]{24})?$"
MODULE_KEY_PATTERN = "^[a-z0-9]+(-[a-z0-9]+)*$"
ITEM_KEY_PATTERN = "^[a-z0-9]+(-[a-z0-9]+)*\\.[RE][0-9]{3,4}$"


class HarnessExecutor(StrEnum):
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"


class HarnessJobTrigger(StrEnum):
    MANUAL = "manual"
    COMMIT = "commit"


class HarnessJobStatus(StrEnum):
    """States of a job in the queue (docs/specs/runner.md, "Estados da tarefa")."""

    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DEFERRED = "deferred"


class KnowledgeItemKind(StrEnum):
    RULE = "rule"
    MODULE = "module"


class KnowledgeConfidence(StrEnum):
    """Trust seal shown with the item; values in pt-BR because they reach the exported
    frontmatter and the chat citation as written."""

    INFERRED = "inferido"
    REVIEWED = "revisado"


class KnowledgeReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DISCARDED = "discarded"


class RejectionBlock(StrEnum):
    """Block of the agent output a rejected item came from (keys of ``schema_version: 1``)."""

    RULES = "regras"
    MESSAGES = "mensagens"
    MAIN_FLOW = "fluxo_principal"
    FAQ = "faq"
    OBJECTIVE = "objetivo"


def _workspace_fk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)


def _empty_object() -> Mapped[dict[str, JSONValue]]:
    return mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))


def _counter() -> Mapped[int]:
    return mapped_column(Integer, nullable=False, default=0, server_default=text("0"))


class Runner(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A machine of the workspace that runs the harness (``knobridge-runner``)."""

    __tablename__ = "runners"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name"),
        # Target of the composite foreign key of ``harness_jobs``.
        UniqueConstraint("workspace_id", "id"),
        CheckConstraint(
            f"token_prefix ~ '^[a-z0-9]{{{TOKEN_PREFIX_LENGTH}}}$'", name="token_prefix_format"
        ),
        CheckConstraint(
            f"token_hash ~ '^[0-9a-f]{{{SHA256_HEX_LENGTH}}}$'", name="token_hash_format"
        ),
        CheckConstraint("jsonb_typeof(capabilities) = 'object'", name="capabilities_is_object"),
    )

    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    name: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH), nullable=False)
    # Public part of the token, unique in the instance: the lookup key in system mode.
    token_prefix: Mapped[str] = mapped_column(
        String(TOKEN_PREFIX_LENGTH), nullable=False, unique=True
    )
    # SHA-256 (hex) of the whole token; the token itself is shown once and never stored.
    token_hash: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ``knobridge-runner`` version reported by the last heartbeat.
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # ``{"platform", "executors", "repositories"}`` from the last heartbeat.
    capabilities: Mapped[dict[str, JSONValue]] = _empty_object()
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class HarnessModule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A module of a runner source: the unit the agent maps in one job."""

    __tablename__ = "harness_modules"
    __table_args__ = (
        UniqueConstraint("source_id", "key"),
        # Target of the composite foreign keys of ``harness_jobs`` and ``knowledge_items``.
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "source_id"],
            ["sources.workspace_id", "sources.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(f"key ~ '{MODULE_KEY_PATTERN}'", name="key_format"),
        CheckConstraint(f"cardinality(paths) BETWEEN 1 AND {MODULE_PATHS_MAX}", name="paths_count"),
        CheckConstraint(f"last_commit ~ '{COMMIT_PATTERN}'", name="last_commit_format"),
        CheckConstraint("jsonb_typeof(inventory) = 'object'", name="inventory_is_object"),
    )

    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Stable key derived from the folder (docs/specs/harness.md, "Chave do módulo").
    key: Mapped[str] = mapped_column(String(MODULE_KEY_MAX_LENGTH), nullable=False)
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH), nullable=False)
    # gitwildmatch patterns relative to the repository root, evaluated like a ``.gitignore``.
    paths: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    # ``True`` while the module is as layer 0 suggested it; editing title or paths clears it.
    suggested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # Commit of the last successful job of the module.
    last_commit: Mapped[str | None] = mapped_column(String(SHA256_HEX_LENGTH), nullable=True)
    # ``{"files", "lines", "languages"}`` of the module, from the last report.
    inventory: Mapped[dict[str, JSONValue]] = _empty_object()


class HarnessJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A job of the leased queue: map one module with one executor."""

    __tablename__ = "harness_jobs"
    __table_args__ = (
        # Target of the composite foreign keys of ``knowledge_items`` and ``harness_rejections``.
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "source_id"],
            ["sources.workspace_id", "sources.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "module_id"],
            ["harness_modules.workspace_id", "harness_modules.id"],
            ondelete="CASCADE",
        ),
        # Only ``runner_id`` is nulled: ``workspace_id`` is part of the key and NOT NULL.
        ForeignKeyConstraint(
            ["workspace_id", "runner_id"],
            ["runners.workspace_id", "runners.id"],
            ondelete="SET NULL (runner_id)",
        ),
        CheckConstraint(f"commit_sha ~ '{COMMIT_PATTERN}'", name="commit_sha_format"),
        CheckConstraint(
            "attempts >= 0 AND items_accepted >= 0 AND items_preserved >= 0 "
            "AND items_rejected >= 0 AND coalesce(input_tokens, 0) >= 0 "
            "AND coalesce(cached_input_tokens, 0) >= 0 AND coalesce(output_tokens, 0) >= 0 "
            "AND coalesce(cost_usd, 0) >= 0 AND coalesce(duration_ms, 0) >= 0",
            name="counts_not_negative",
        ),
        CheckConstraint("jsonb_typeof(metrics) = 'object'", name="metrics_is_object"),
        # The claim scans eligible jobs of the workspace, oldest first.
        Index(None, "workspace_id", "status", "created_at"),
        Index(None, "source_id", "created_at"),
        Index(None, "module_id", "status"),
    )

    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    module_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Runner that holds (or last held) the lease; ``None`` before the first claim.
    runner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    executor: Mapped[HarnessExecutor] = mapped_column(
        str_enum(HarnessExecutor, "executor"), nullable=False
    )
    # ``None``: the executor's default model; after a result, the model actually used.
    model: Mapped[str | None] = mapped_column(String(MODEL_MAX_LENGTH), nullable=True)
    trigger: Mapped[HarnessJobTrigger] = mapped_column(
        str_enum(HarnessJobTrigger, "trigger"), nullable=False
    )
    status: Mapped[HarnessJobStatus] = mapped_column(
        str_enum(HarnessJobStatus, "status"), nullable=False
    )
    # Attempts spent (expired leases and retryable failures; a deferral does not count).
    attempts: Mapped[int] = _counter()
    # Not eligible before this instant (retry delay or deferral).
    not_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # HEAD known at enqueue time; replaced by the commit the result was produced from.
    commit_sha: Mapped[str | None] = mapped_column(String(SHA256_HEX_LENGTH), nullable=True)
    # Metrics summed over the attempts that reported them; ``None`` when never reported.
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # The rest of ``RunnerJobMetrics`` and of the result's ``executor`` (version, session):
    # ``num_turns``, ``tool_calls``, ``rescued``, ``sources_valid``, ``sources_invalid``,
    # ``items_truncated``, ``redactions``, ``executor_version``, ``session_id``.
    metrics: Mapped[dict[str, JSONValue]] = _empty_object()
    items_accepted: Mapped[int] = _counter()
    # Reviewed or edited items kept by the result (returned again on a duplicate result).
    items_preserved: Mapped[int] = _counter()
    items_rejected: Mapped[int] = _counter()
    # ``<code>: <message>`` from fixed templates; never stderr or agent output.
    error: Mapped[str | None] = mapped_column(String(ERROR_MAX_LENGTH), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgeItem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A rule or module item accepted from a job, with its evidence and review state."""

    __tablename__ = "knowledge_items"
    __table_args__ = (
        UniqueConstraint("source_id", "key"),
        ForeignKeyConstraint(
            ["workspace_id", "source_id"],
            ["sources.workspace_id", "sources.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "module_id"],
            ["harness_modules.workspace_id", "harness_modules.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "job_id"],
            ["harness_jobs.workspace_id", "harness_jobs.id"],
            ondelete="SET NULL (job_id)",
        ),
        CheckConstraint(f"key ~ '{ITEM_KEY_PATTERN}'", name="key_format"),
        CheckConstraint(f"commit_sha ~ '{COMMIT_PATTERN}'", name="commit_sha_format"),
        CheckConstraint("jsonb_typeof(content) = 'object'", name="content_is_object"),
        CheckConstraint("jsonb_typeof(evidence) = 'array'", name="evidence_is_array"),
        CheckConstraint(
            "edited IS NULL OR jsonb_typeof(edited) = 'object'", name="edited_is_object"
        ),
        Index(None, "module_id"),
    )

    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    module_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Job that produced the item; ``None`` if that job was deleted.
    job_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    kind: Mapped[KnowledgeItemKind] = mapped_column(
        str_enum(KnowledgeItemKind, "kind"), nullable=False
    )
    # ``<module_key>.R001`` (rule) or ``<module_key>.E001`` (module enrichment), server-assigned.
    key: Mapped[str] = mapped_column(String(ITEM_KEY_MAX_LENGTH), nullable=False)
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH), nullable=False)
    # Shape depends on ``kind`` (docs/specs/harness.md); validated at the boundary.
    content: Mapped[dict[str, JSONValue]] = mapped_column(JSONB, nullable=False)
    # ``[{"path", "start_line", "end_line", "symbol", "excerpt", ...}]``, never edited.
    evidence: Mapped[list[JSONValue]] = mapped_column(JSONB, nullable=False)
    confidence: Mapped[KnowledgeConfidence] = mapped_column(
        str_enum(KnowledgeConfidence, "confidence"),
        nullable=False,
        default=KnowledgeConfidence.INFERRED,
        server_default=KnowledgeConfidence.INFERRED.value,
    )
    review_status: Mapped[KnowledgeReviewStatus] = mapped_column(
        str_enum(KnowledgeReviewStatus, "review_status"),
        nullable=False,
        default=KnowledgeReviewStatus.PENDING,
        server_default=KnowledgeReviewStatus.PENDING.value,
    )
    # ``{"title"?, "content"?}`` edited in review; ``None`` while untouched.
    edited: Mapped[dict[str, JSONValue] | None] = mapped_column(JSONB, nullable=True)
    # A cited file changed after the item was reviewed or edited.
    evidence_changed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    commit_sha: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), nullable=False)
    # ``harness:<executor>:<model>`` or ``harness:<executor>``.
    generated_by: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH), nullable=False)


class HarnessRejection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An item or sub-item of a job that the runner's verification refused."""

    __tablename__ = "harness_rejections"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "job_id"],
            ["harness_jobs.workspace_id", "harness_jobs.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("item_index >= 0", name="item_index_not_negative"),
        CheckConstraint("jsonb_typeof(sources) = 'array'", name="sources_is_array"),
        Index(None, "job_id"),
    )

    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    job_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    block: Mapped[RejectionBlock] = mapped_column(str_enum(RejectionBlock, "block"), nullable=False)
    # Position in the block (``index`` on the wire; 0 for ``objetivo``).
    item_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # ``titulo``, ``mensagem``, ``passo`` or ``pergunta`` of the item, redacted.
    label: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    # Fixed reason in pt-BR.
    reason: Mapped[str] = mapped_column(String(ERROR_MAX_LENGTH), nullable=False)
    # ``[{"path", "start_line", "end_line", "symbol", "code"}]``, up to 5.
    sources: Mapped[list[JSONValue]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
