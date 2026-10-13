"""Per-kind configuration of a ``Source``, stored as JSON in ``sources.config``.

The database only knows the config is a JSON object; its shape depends on ``sources.kind`` and
is validated here, at the boundary (API, worker), with ``parse_source_config``. Include and
exclude globs are not part of it: they are columns of ``sources``, shared by every kind.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Self

from pydantic import AfterValidator, AnyUrl, BaseModel, ConfigDict, Field, model_validator

from knobridge.harness.models import COMMIT_PATTERN, HarnessExecutor

DEFAULT_INITIAL_COMMIT_LIMIT = 200
MAX_INITIAL_COMMIT_LIMIT = 5000
PATH_MAX_LENGTH = 1000
BRANCH_MAX_LENGTH = 200
# Runner sources (docs/specs/runner.md, "Fonte do tipo runner" and "Formatos validados").
REPOSITORY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
MODEL_PATTERN = r"^[A-Za-z0-9._:/-]{1,100}$"
DEFAULT_BUDGET_USD = 5.0
DEFAULT_TIMEOUT_SECONDS = 1200
DEFAULT_EXCERPT_MAX_LINES = 30


class SourceKind(StrEnum):
    GIT = "git"
    FOLDER = "folder"
    # A repository on a user's machine, mapped by a ``knobridge-runner`` (ADR 0005).
    RUNNER = "runner"
    # Tickets pushed by an external system through ``/v1/ingest/*`` (ADR 0006).
    TICKETS = "tickets"
    # Development cards pushed the same way (docs/specs/cards.md, ADR 0008).
    CARDS = "cards"


# Kinds whose documents are pushed into the inbox (``ticket_inbox``) with an ingest token.
PUSH_SOURCE_KINDS = frozenset({SourceKind.TICKETS, SourceKind.CARDS})


class TicketStatus(StrEnum):
    """Normalized status of a ticket (docs/specs/chamados.md, "Status normalizado")."""

    OPEN = "open"
    PENDING = "pending"
    RESOLVED = "resolved"
    CLOSED = "closed"


# How a status is shown (the ticket's Markdown and the chat context), in pt-BR.
TICKET_STATUS_LABELS = {
    TicketStatus.OPEN: "Aberto",
    TicketStatus.PENDING: "Pendente",
    TicketStatus.RESOLVED: "Resolvido",
    TicketStatus.CLOSED: "Fechado",
}


class CardStatus(StrEnum):
    """Normalized status of a card (docs/specs/cards.md, "Status e tipo normalizados")."""

    BACKLOG = "backlog"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"


class CardType(StrEnum):
    FEATURE = "feature"
    BUG = "bug"
    TASK = "task"
    STORY = "story"
    EPIC = "epic"
    OTHER = "other"


# How a card's status and type are shown (the card's Markdown and the chat context), in pt-BR.
CARD_STATUS_LABELS = {
    CardStatus.BACKLOG: "Backlog",
    CardStatus.IN_PROGRESS: "Em andamento",
    CardStatus.DONE: "Concluído",
    CardStatus.CANCELLED: "Cancelado",
}
CARD_TYPE_LABELS = {
    CardType.FEATURE: "Funcionalidade",
    CardType.BUG: "Bug",
    CardType.TASK: "Tarefa",
    CardType.STORY: "História",
    CardType.EPIC: "Épico",
    CardType.OTHER: "Outro",
}


def _absolute_path(value: str) -> str:
    # The worker reads the path on its own filesystem; a relative path would depend on its cwd.
    if not Path(value).is_absolute():
        raise ValueError("path must be absolute")
    return value


def _public_https_url(value: AnyUrl) -> AnyUrl:
    if value.scheme != "https":
        raise ValueError("url must use https")
    # Credentials in the URL would be stored in clear text; private repositories come later,
    # with an encrypted credential.
    if value.username is not None or value.password is not None:
        raise ValueError("url must not contain credentials")
    return value


def _branch_name(value: str) -> str:
    # A subset of git-check-ref-format, enough to keep the value from being read as an option
    # or a revision range when passed to git.
    forbidden = (" ", "..", "~", "^", ":", "?", "*", "[", "\\", "@{")
    if value.startswith(("-", "/")) or value.endswith(("/", ".lock")):
        raise ValueError("invalid branch name")
    if any(part in value for part in forbidden):
        raise ValueError("invalid branch name")
    return value


type AbsolutePath = Annotated[
    str,
    Field(min_length=1, max_length=PATH_MAX_LENGTH),
    AfterValidator(_absolute_path),
]
type PublicHttpsUrl = Annotated[AnyUrl, AfterValidator(_public_https_url)]
type BranchName = Annotated[
    str, Field(min_length=1, max_length=BRANCH_MAX_LENGTH), AfterValidator(_branch_name)
]


class GitSourceConfig(BaseModel):
    """A Git repository: a local clone (``path``) or a public https remote (``url``)."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    path: AbsolutePath | None = None
    url: PublicHttpsUrl | None = None
    # ``None``: the repository's default branch (``HEAD``).
    branch: BranchName | None = None
    # How many of the most recent commits the first run indexes as ``commit`` documents.
    initial_commit_limit: int = Field(
        default=DEFAULT_INITIAL_COMMIT_LIMIT, ge=0, le=MAX_INITIAL_COMMIT_LIMIT
    )

    @model_validator(mode="after")
    def _exactly_one_location(self) -> Self:
        if (self.path is None) == (self.url is None):
            raise ValueError("exactly one of path or url is required")
        return self


class FolderSourceConfig(BaseModel):
    """A local folder of documents, read from the worker's filesystem."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    path: AbsolutePath


type ModelName = Annotated[str, Field(pattern=MODEL_PATTERN)]
type RepositoryName = Annotated[str, Field(pattern=REPOSITORY_PATTERN)]
type CommitSha = Annotated[str, Field(pattern=COMMIT_PATTERN)]


class RunnerModels(BaseModel):
    """Model per executor; ``None`` is the executor's default model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claude_code: ModelName | None = None
    codex: ModelName | None = None

    def for_executor(self, executor: HarnessExecutor) -> str | None:
        return self.claude_code if executor is HarnessExecutor.CLAUDE_CODE else self.codex


class RunnerSourceConfig(BaseModel):
    """A repository on a user's machine, mapped by a ``knobridge-runner`` (ADR 0005).

    Never an OpenAPI schema (the API takes and returns ``config`` as a plain object): the
    heartbeat already publishes another ``RunnerSourceConfig``, the one the runner reads.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    runner_id: uuid.UUID
    repository: RepositoryName
    default_executor: HarnessExecutor = HarnessExecutor.CLAUDE_CODE
    models: RunnerModels = Field(default_factory=RunnerModels)
    budget_usd: float = Field(default=DEFAULT_BUDGET_USD, ge=0.1, le=100)
    timeout_seconds: int = Field(default=DEFAULT_TIMEOUT_SECONDS, ge=60, le=7200)
    auto_on_commit: bool = False
    excerpt_max_lines: int = Field(default=DEFAULT_EXCERPT_MAX_LINES, ge=0, le=80)
    # Read only: written by the runner's report; the panel's value is ignored.
    head_commit: CommitSha | None = None


def _distinct_statuses[S: StrEnum](value: tuple[S, ...]) -> tuple[S, ...]:
    if len(set(value)) != len(value):
        raise ValueError("statuses must not repeat")
    return value


class TicketsSourceConfig(BaseModel):
    """Tickets pushed by an external system (docs/specs/chamados.md, "Fonte do tipo tickets").

    The settings apply to the tickets processed after a change: the raw payload of a processed
    ticket is gone, so nothing is reprocessed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Internal notes (``public: false`` messages) go into the index.
    include_internal_notes: bool = False
    # Deterministic anonymization before chunking (docs/specs/chamados.md, "Anonimização").
    anonymize: bool = True
    # Statuses indexed; a ticket in any other status is left out of the index (``filtered``).
    statuses: Annotated[
        tuple[TicketStatus, ...], Field(min_length=1), AfterValidator(_distinct_statuses)
    ] = tuple(TicketStatus)


class CardsSourceConfig(BaseModel):
    """Cards pushed by an external system (docs/specs/cards.md, "Fonte do tipo cards"). Like
    the tickets' settings, they apply to the cards processed after a change."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # On by default: cards copy excerpts of tickets, with customers' data.
    anonymize: bool = True
    include_comments: bool = True
    statuses: Annotated[
        tuple[CardStatus, ...], Field(min_length=1), AfterValidator(_distinct_statuses)
    ] = tuple(CardStatus)


type SourceConfig = (
    GitSourceConfig
    | FolderSourceConfig
    | RunnerSourceConfig
    | TicketsSourceConfig
    | CardsSourceConfig
)

_CONFIG_MODELS: dict[
    SourceKind,
    type[GitSourceConfig]
    | type[FolderSourceConfig]
    | type[RunnerSourceConfig]
    | type[TicketsSourceConfig]
    | type[CardsSourceConfig],
] = {
    SourceKind.GIT: GitSourceConfig,
    SourceKind.FOLDER: FolderSourceConfig,
    SourceKind.RUNNER: RunnerSourceConfig,
    SourceKind.TICKETS: TicketsSourceConfig,
    SourceKind.CARDS: CardsSourceConfig,
}


def parse_source_config(kind: SourceKind, data: Mapping[str, object]) -> SourceConfig:
    """Validate ``data`` against the model of ``kind``; raises ``pydantic.ValidationError``."""
    return _CONFIG_MODELS[kind].model_validate(dict(data))
