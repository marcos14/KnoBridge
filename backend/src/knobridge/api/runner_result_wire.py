"""Wire models of ``POST /v1/runner/jobs/{job_id}/result`` (docs/specs/runner.md and the limits
of docs/specs/harness.md, "Limites" and "Itens de conhecimento no resultado").

Schema names are the runner's (``runner/src/knobridge_runner/protocol_result.py``), compared by
its contract test against ``docs/specs/openapi.json``: do not rename. Content keys are the
agent's (pt-BR); wire fields are English.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, RootModel, model_validator

from knobridge.api.runner_jobs import RunnerJobMetrics
from knobridge.api.runner_wire import CommitSha, ModelName, RelativePath, WireRequest
from knobridge.harness.models import HarnessExecutor, KnowledgeItemKind, RejectionBlock

MAX_RANGE_LINES = 80
MAX_EXCERPT_BYTES = 8 * 1024
MAX_EXCERPT_LINE_CHARS = 400
MAX_RULE_ITEMS = 30
MAX_CHANGED_PATHS = 20_000

RejectionCode = Literal[
    "outside_checkout",
    "file_not_found",
    "bad_range",
    "range_too_long",
    "symbol_mismatch",
    "no_valid_source",
]
LongText = Annotated[str, Field(max_length=1000)]
EvidenceIndexes = list[Annotated[int, Field(ge=0)]]


class RunnerEvidenceIn(WireRequest):
    path: RelativePath
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    symbol: str | None = Field(default=None, max_length=200)
    excerpt: str | None = None
    excerpt_truncated: bool = False
    excerpt_omitted: Literal["disabled", "sensitive_file"] | None = None
    redacted: bool = False

    @model_validator(mode="after")
    def _check_range_and_excerpt(self) -> Self:
        lines = self.end_line - self.start_line + 1
        if lines < 1:
            raise ValueError("end_line must be >= start_line")
        if lines > MAX_RANGE_LINES:
            raise ValueError(f"range must have at most {MAX_RANGE_LINES} lines")
        if self.excerpt is None:
            return self
        if len(self.excerpt.encode("utf-8")) > MAX_EXCERPT_BYTES:
            raise ValueError(f"excerpt must have at most {MAX_EXCERPT_BYTES} bytes")
        excerpt_lines = self.excerpt.split("\n")
        if len(excerpt_lines) > lines:
            raise ValueError("excerpt must not have more lines than the cited range")
        if any(len(line) > MAX_EXCERPT_LINE_CHARS for line in excerpt_lines):
            raise ValueError(f"excerpt lines must have at most {MAX_EXCERPT_LINE_CHARS} characters")
        return self


class RuleContent(WireRequest):
    enunciado: LongText
    quando: LongText
    mensagem: str | None = Field(max_length=500)
    resolucao: LongText
    parametros: list[Annotated[str, Field(max_length=100)]] = Field(max_length=10)
    classificacao: Literal["observado", "intencional", "bug_conhecido"]
    relevancia: Literal["alta", "media", "baixa", "sistemica"]


class FlowStep(WireRequest):
    ordem: int
    passo: LongText
    evidencias: EvidenceIndexes


class ModuleMessage(WireRequest):
    mensagem: str = Field(max_length=500)
    causa: LongText
    acao: LongText
    evidencias: EvidenceIndexes


class FaqEntry(WireRequest):
    pergunta: str = Field(max_length=300)
    resposta: LongText
    evidencias: EvidenceIndexes


class OpenQuestion(WireRequest):
    pergunta: str = Field(max_length=300)
    contexto: LongText


class ModuleContent(WireRequest):
    objetivo: LongText
    fluxo_principal: list[FlowStep] = Field(max_length=20)
    mensagens: list[ModuleMessage] = Field(max_length=40)
    faq: list[FaqEntry] = Field(max_length=15)
    duvidas: list[OpenQuestion] = Field(max_length=15)


class RuleItemIn(WireRequest):
    kind: Literal["rule"]
    title: str = Field(max_length=200)
    content: RuleContent
    evidence: list[RunnerEvidenceIn] = Field(min_length=1, max_length=5)


class ModuleItemIn(WireRequest):
    kind: Literal["module"]
    title: str = Field(max_length=200)
    content: ModuleContent
    evidence: list[RunnerEvidenceIn] = Field(min_length=1, max_length=375)

    @model_validator(mode="after")
    def _indexes_point_at_evidence(self) -> Self:
        content = self.content
        referenced = [
            index
            for entry in (*content.fluxo_principal, *content.mensagens, *content.faq)
            for index in entry.evidencias
        ]
        if any(index >= len(self.evidence) for index in referenced):
            raise ValueError("evidencias must point at an evidence of the item")
        return self


class RunnerKnowledgeItemIn(
    RootModel[Annotated[RuleItemIn | ModuleItemIn, Field(discriminator="kind")]]
):
    """A rule item or the module enrichment, told apart by ``kind``."""

    @property
    def kind(self) -> KnowledgeItemKind:
        return KnowledgeItemKind(self.root.kind)


class RunnerRejectionSource(WireRequest):
    path: str | None = Field(max_length=500)
    start_line: int | None
    end_line: int | None
    symbol: str | None = Field(max_length=200)
    code: RejectionCode


class RunnerRejectionIn(WireRequest):
    block: RejectionBlock
    index: int = Field(ge=0)
    label: str = Field(max_length=200)
    code: RejectionCode
    reason: str = Field(max_length=500)
    sources: list[RunnerRejectionSource] = Field(max_length=5)


class RunnerExecutorRun(WireRequest):
    name: HarnessExecutor
    version: str | None = Field(default=None, max_length=64)
    # The model actually used when the executor reports it; else the one asked for.
    model: ModelName | None = None
    session_id: str | None = Field(default=None, max_length=100)


class RunnerJobResultIn(WireRequest):
    attempt: int = Field(ge=1)
    commit_sha: CommitSha
    # Changed between the module's ``last_commit`` and ``commit_sha``; ``None`` when unknown.
    changed_paths: list[RelativePath] | None = Field(max_length=MAX_CHANGED_PATHS)
    executor: RunnerExecutorRun
    metrics: RunnerJobMetrics
    items: list[RunnerKnowledgeItemIn] = Field(max_length=MAX_RULE_ITEMS + 1)
    rejections: list[RunnerRejectionIn] = Field(max_length=300)

    @model_validator(mode="after")
    def _check_item_kinds(self) -> Self:
        rules = sum(1 for item in self.items if item.kind == KnowledgeItemKind.RULE)
        if rules > MAX_RULE_ITEMS or len(self.items) - rules > 1:
            raise ValueError(f"at most {MAX_RULE_ITEMS} rule items and 1 module item")
        return self


class RunnerJobResultOut(BaseModel):
    job_id: uuid.UUID
    status: Literal["succeeded"]
    items_accepted: int
    # Reviewed or edited items of the module kept by this result.
    items_preserved: int
    items_rejected: int
    sync_run_id: uuid.UUID | None
    duplicate: bool
