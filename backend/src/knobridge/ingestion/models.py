"""The indexed knowledge of a workspace: ``Collection``, ``Source``, ``Run``, ``RunError``,
``RunItem``, ``Document`` and ``Chunk`` (``docs/adr/0004-indice-de-conhecimento.md``).

Workspace data with forced row-level security (``docs/adr/0001-tenancy-e-rls.md``). Every
reference between these tables is composite, ``(workspace_id, <parent>_id)``, so the database
itself refuses a parent of another workspace. A collection fixes the embedding credential and
model; each source feeds exactly one collection; deletes cascade from the source down to its
runs, documents and chunks. Vectors have a fixed dimension (``EMBEDDING_DIMENSION``) and each
chunk records the model that produced its vector, so a model change means reindexing.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.engine.default import DefaultExecutionContext
from sqlalchemy.orm import Mapped, mapped_column

from knobridge.audit.models import JSONValue
from knobridge.core.models import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from knobridge.ingestion.source_config import SourceConfig, SourceKind, parse_source_config
from knobridge.levels.level import ResponseLevel

# Fixed for every collection (ADR 0004): one column type, one HNSW index. Models with larger
# native vectors are used with a reduced output dimension (Matryoshka / ``dimensions``).
EMBEDDING_DIMENSION = 1536
SHA256_HEX_LENGTH = 64
RUN_ERROR_MESSAGE_MAX_LENGTH = 500

# Lexical side of hybrid search: content in Portuguese (stemming), path and symbol with the
# ``simple`` configuration (identifiers must match as written). The path goes in whole (the
# parser keeps it as one token) and split on ``/`` and ``.``, so its segments match too.
# Immutable expression, as a generated column requires.
CHUNK_TSV_EXPRESSION = (
    "to_tsvector('portuguese'::regconfig, content) || "
    "to_tsvector('simple'::regconfig, coalesce(meta ->> 'path', '') || ' ' || "
    "translate(coalesce(meta ->> 'path', ''), '/.', '  ') || ' ' || "
    "coalesce(meta ->> 'symbol', ''))"
)


class RunTrigger(StrEnum):
    MANUAL = "manual"
    SCHEDULE = "schedule"
    # Asked for by a harness result or a knowledge review (plan 0004, ``harness/``).
    HARNESS = "harness"
    # Asked for by tickets pushed to a ``tickets`` source (plan 0005, ``tickets/``).
    INGEST = "ingest"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunErrorStage(StrEnum):
    """Pipeline step where a document failed."""

    FETCH = "fetch"
    PARSE = "parse"
    CHUNK = "chunk"
    EMBED = "embed"
    STORE = "store"


class DocumentKind(StrEnum):
    FILE = "file"
    COMMIT = "commit"
    # A knowledge item of a runner source, rendered as Markdown (``harness/``, ADR 0005).
    KNOWLEDGE = "knowledge"
    # A ticket of a ``tickets`` source, rendered as Markdown (``tickets/``, ADR 0006).
    TICKET = "ticket"
    # A card of a ``cards`` source, rendered as Markdown (``tickets/``, docs/specs/cards.md).
    CARD = "card"


class RunItemChange(StrEnum):
    """What a run does with a listed document: (re)index it or delete it."""

    UPSERT = "upsert"
    REMOVE = "remove"


def _workspace_fk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)


# Minimum level of a new source by kind (docs/specs/produtos-e-niveis.md, "Padrões por tipo"):
# documents and reviewed knowledge for everyone, tickets from support up, code and cards from
# development up.
DEFAULT_SOURCE_MIN_LEVELS: dict[SourceKind, ResponseLevel] = {
    SourceKind.FOLDER: ResponseLevel.END_USER,
    SourceKind.RUNNER: ResponseLevel.END_USER,
    SourceKind.TICKETS: ResponseLevel.SUPPORT,
    SourceKind.GIT: ResponseLevel.PRODUCT_DEV,
    SourceKind.CARDS: ResponseLevel.PRODUCT_DEV,
}


def _default_min_level(context: DefaultExecutionContext) -> str:
    kind = SourceKind(context.get_current_parameters()["kind"])
    return DEFAULT_SOURCE_MIN_LEVELS[kind].value


class Collection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "collections"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name"),
        # Target of the composite foreign keys of ``sources`` and ``chunks``.
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "credential_id"],
            ["provider_credentials.workspace_id", "provider_credentials.id"],
        ),
        CheckConstraint(
            f"embedding_dimension = {EMBEDDING_DIMENSION}", name="embedding_dimension_fixed"
        ),
    )

    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Embedding provider credential of the same workspace; ``NO ACTION`` on delete (in use).
    credential_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Model identifier as the provider knows it (e.g. ``text-embedding-3-small``).
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(
        Integer, nullable=False, default=EMBEDDING_DIMENSION
    )


class Source(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name"),
        # Target of the composite foreign keys of ``runs`` and ``documents``.
        UniqueConstraint("workspace_id", "id"),
        # ``NO ACTION``: a collection with sources cannot be deleted.
        ForeignKeyConstraint(
            ["workspace_id", "collection_id"],
            ["collections.workspace_id", "collections.id"],
        ),
        CheckConstraint("jsonb_typeof(config) = 'object'", name="config_is_object"),
        CheckConstraint(
            "NOT schedule_enabled OR schedule_cron IS NOT NULL", name="schedule_needs_cron"
        ),
        # A runner serves a repository to at most one source of the workspace.
        Index(
            "uq_sources_workspace_id_runner_repository",
            "workspace_id",
            text("(config ->> 'runner_id')"),
            text("(config ->> 'repository')"),
            unique=True,
            postgresql_where=text("kind = 'runner'"),
        ),
    )

    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    collection_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    kind: Mapped[SourceKind] = mapped_column(str_enum(SourceKind, "kind"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Shape depends on ``kind`` (``source_config.py``); validated at the boundary.
    config: Mapped[dict[str, JSONValue]] = mapped_column(JSONB, nullable=False)
    # Glob patterns over document paths, applied by the ingestion engine for every kind.
    include_globs: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'::text[]")
    )
    exclude_globs: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'::text[]")
    )
    # Five-field cron expression of the scheduled runs; validated at the boundary.
    schedule_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    schedule_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Incremental position of the connector (e.g. ``{"commit": "<sha>"}``); ``None``: never ran.
    cursor: Mapped[dict[str, JSONValue] | None] = mapped_column(JSONB, nullable=True)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    # A harness sync was asked for while another run was in progress; the next successful run
    # consumes it and the workflow continues with a new run (``ingestion.runs``).
    sync_pending: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Lowest level of question that may read the source; the default depends on the kind.
    min_level: Mapped[ResponseLevel] = mapped_column(
        str_enum(ResponseLevel, "min_level"), nullable=False, default=_default_min_level
    )

    def typed_config(self) -> SourceConfig:
        """The stored config validated against the model of ``kind``."""
        return parse_source_config(self.kind, self.config)


class Run(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One execution of the ingestion of a source; ``created_at`` is when it was queued."""

    __tablename__ = "runs"
    __table_args__ = (
        # Target of the composite foreign key of ``run_errors``.
        UniqueConstraint("workspace_id", "id"),
        ForeignKeyConstraint(
            ["workspace_id", "source_id"],
            ["sources.workspace_id", "sources.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "documents_new >= 0 AND documents_changed >= 0 AND documents_removed >= 0 "
            "AND documents_failed >= 0 AND chunks_written >= 0 AND embedding_tokens >= 0",
            name="counts_not_negative",
        ),
        Index(None, "workspace_id", "source_id", "created_at"),
    )

    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    trigger: Mapped[RunTrigger] = mapped_column(str_enum(RunTrigger, "trigger"), nullable=False)
    status: Mapped[RunStatus] = mapped_column(str_enum(RunStatus, "status"), nullable=False)
    documents_new: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    documents_changed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    documents_removed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    documents_failed: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    chunks_written: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    embedding_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    # Estimated embedding cost in USD; ``None`` when the price of the model is unknown.
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Short summary of why the run failed (never a stack trace, a prompt or document content).
    error: Mapped[str | None] = mapped_column(String(RUN_ERROR_MESSAGE_MAX_LENGTH), nullable=True)
    # Cursor produced by this run's listing; copied to ``sources.cursor`` only on success.
    pending_cursor: Mapped[dict[str, JSONValue] | None] = mapped_column(JSONB, nullable=True)


class RunError(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A document that failed in a run; the run goes on with the other documents."""

    __tablename__ = "run_errors"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["runs.workspace_id", "runs.id"],
            ondelete="CASCADE",
        ),
        Index(None, "run_id"),
    )

    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Natural key of the document (it may have failed before having a ``documents`` row).
    document_key: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[RunErrorStage] = mapped_column(str_enum(RunErrorStage, "stage"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(String(RUN_ERROR_MESSAGE_MAX_LENGTH), nullable=False)


class RunItem(Base):
    """One listed document a run still has to process, in listing order (``ordinal``).

    The change set of a source can hold thousands of documents, too many for the Temporal
    history, so the listing activity stores it here and each batch activity reads a page.
    ``done`` is set in the same transaction that writes the document, so a retried batch skips
    what was already processed. Rows are deleted when the run finishes.
    """

    __tablename__ = "run_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["runs.workspace_id", "runs.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("ordinal >= 0", name="ordinal_not_negative"),
    )

    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_key: Mapped[str] = mapped_column(Text, nullable=False)
    document_kind: Mapped[DocumentKind] = mapped_column(
        str_enum(DocumentKind, "document_kind"), nullable=False
    )
    change: Mapped[RunItemChange] = mapped_column(str_enum(RunItemChange, "change"), nullable=False)
    done: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class Document(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        # Target of the composite foreign key of ``chunks``.
        UniqueConstraint("workspace_id", "id"),
        # The incremental key: a path (``file``) or a commit SHA (``commit``) inside the source.
        UniqueConstraint("source_id", "natural_key"),
        ForeignKeyConstraint(
            ["workspace_id", "source_id"],
            ["sources.workspace_id", "sources.id"],
            ondelete="CASCADE",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    source_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    natural_key: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[DocumentKind] = mapped_column(str_enum(DocumentKind, "kind"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    # Where a citation points to (file URL, commit URL or local path).
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    # SHA-256 (hex) of the content; unchanged hash = nothing to reindex.
    content_hash: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), nullable=False)
    # Programming or natural language detected for the content, when known.
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict[str, JSONValue]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # When the current content was fully indexed; ``None`` while it is being (re)indexed.
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Refinement of the source's minimum level set by the connector (code in a folder, inferred
    # knowledge); ``None``: the source's. Only raises the level, never editable by the API.
    min_level: Mapped[ResponseLevel | None] = mapped_column(
        str_enum(ResponseLevel, "min_level"), nullable=True
    )


class Chunk(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "position"),
        ForeignKeyConstraint(
            ["workspace_id", "document_id"],
            ["documents.workspace_id", "documents.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "collection_id"],
            ["collections.workspace_id", "collections.id"],
            ondelete="CASCADE",
        ),
        CheckConstraint("position >= 0", name="position_not_negative"),
        Index(None, "workspace_id", "collection_id"),
        # Embedding cache lookup: a vector already computed for the same text in the collection.
        Index(None, "collection_id", "content_hash"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_chunks_tsv_gin", "tsv", postgresql_using="gin"),
    )

    workspace_id: Mapped[uuid.UUID] = _workspace_fk()
    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Denormalized from the source of the document, so retrieval filters chunks directly.
    collection_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Order of the chunk inside its document, from 0.
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Citation data: ``path``, ``start_line``, ``end_line``, ``symbol``, ``headings``.
    meta: Mapped[dict[str, JSONValue]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    # SHA-256 (hex) of the content: key of the embedding cache.
    content_hash: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), nullable=False)
    # Model that produced ``embedding``; differs from the collection's after a model change.
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_DIMENSION), nullable=False)
    tsv: Mapped[str] = mapped_column(
        TSVECTOR, Computed(CHUNK_TSV_EXPRESSION, persisted=True), nullable=False
    )
    # Effective minimum level: the highest of the source's, the document's and ``meta.min_level``.
    # Search filters it in SQL. Unset, the database writes the highest level, so a chunk whose
    # writer forgot the level is never shown below development.
    min_level: Mapped[ResponseLevel] = mapped_column(
        str_enum(ResponseLevel, "min_level"),
        nullable=False,
        server_default=ResponseLevel.PRODUCT_DEV.value,
    )
