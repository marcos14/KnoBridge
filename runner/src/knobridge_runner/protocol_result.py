"""Wire models of POST /v1/runner/jobs/{id}/result (docs/specs/runner.md and harness.md).

Limits follow harness.md ("Limites"); the server validates them again and answers 422
``result_invalid`` on any violation.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from knobridge_runner.formats import CommitSha, Executor, ModelName, RelativePath
from knobridge_runner.protocol import RunnerJobMetrics, WireRequest, WireResponse

RejectionCode = Literal[
    "outside_checkout",
    "file_not_found",
    "bad_range",
    "range_too_long",
    "symbol_mismatch",
    "no_valid_source",
]
RejectionBlock = Literal["regras", "mensagens", "fluxo_principal", "faq", "objetivo"]

MAX_RANGE_LINES = 80
MAX_EXCERPT_BYTES = 8 * 1024

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
    def _check_range_and_excerpt(self) -> RunnerEvidenceIn:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        if self.end_line - self.start_line + 1 > MAX_RANGE_LINES:
            raise ValueError(f"range must have at most {MAX_RANGE_LINES} lines")
        if self.excerpt is not None and len(self.excerpt.encode("utf-8")) > MAX_EXCERPT_BYTES:
            raise ValueError(f"excerpt must have at most {MAX_EXCERPT_BYTES} bytes")
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


RunnerKnowledgeItemIn = Annotated[RuleItemIn | ModuleItemIn, Field(discriminator="kind")]


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
    reason: str
    sources: list[RunnerRejectionSource] = Field(max_length=5)


class RunnerExecutorRun(WireRequest):
    name: Executor
    version: str | None = Field(default=None, max_length=64)
    model: ModelName | None = None
    session_id: str | None = Field(default=None, max_length=100)


class RunnerJobResultIn(WireRequest):
    attempt: int = Field(ge=1)
    commit_sha: CommitSha
    changed_paths: list[RelativePath] | None = Field(max_length=20_000)
    executor: RunnerExecutorRun
    metrics: RunnerJobMetrics
    items: list[RunnerKnowledgeItemIn] = Field(max_length=31)
    rejections: list[RunnerRejectionIn] = Field(max_length=300)

    @model_validator(mode="after")
    def _check_item_kinds(self) -> RunnerJobResultIn:
        rules = sum(1 for item in self.items if item.kind == "rule")
        if rules > 30 or len(self.items) - rules > 1:
            raise ValueError("at most 30 rule items and 1 module item")
        return self


class RunnerJobResultOut(WireResponse):
    job_id: UUID
    status: Literal["succeeded"]
    items_accepted: int
    items_preserved: int
    items_rejected: int
    sync_run_id: UUID | None
    duplicate: bool = False
