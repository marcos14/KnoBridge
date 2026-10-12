"""Knowledge items and rejections of a job result (docs/specs/harness.md, "Itens de conhecimento").

The agent output (already valid against ``schema_version: 1``) is cut to the limits, every source
is verified in the checkout, valid sources become evidence with excerpts, and every text that
leaves the machine is redacted. One rule item per accepted rule, at most one module enrichment.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from knobridge_runner.excerpt import cut, make_excerpt, redact
from knobridge_runner.protocol_result import (
    FaqEntry,
    FlowStep,
    ModuleContent,
    ModuleItemIn,
    ModuleMessage,
    OpenQuestion,
    RejectionBlock,
    RejectionCode,
    RuleContent,
    RuleItemIn,
    RunnerEvidenceIn,
    RunnerRejectionIn,
    RunnerRejectionSource,
)
from knobridge_runner.verify import REASONS, CheckedSource, SourceVerifier, rejection_code

BLOCK_LIMITS: dict[str, int] = {
    "regras": 30,
    "mensagens": 40,
    "fluxo_principal": 20,
    "faq": 15,
    "duvidas": 15,
}
MAX_SOURCES_PER_ITEM = 5
MAX_REJECTIONS = 300
TITLE_CHARS = 200
MESSAGE_CHARS = 500
QUESTION_CHARS = 300
LONG_CHARS = 1000
LABEL_CHARS = 200
SYMBOL_CHARS = 200
MAX_PARAMETERS = 10
PARAMETER_CHARS = 100

Json = Mapping[str, object]
EvidenceKey = tuple[str, int, int]


@dataclass
class Assembly:
    """Items, rejections and the verification counters of ``RunnerJobMetrics``."""

    items: list[RuleItemIn | ModuleItemIn] = field(default_factory=list[RuleItemIn | ModuleItemIn])
    rejections: list[RunnerRejectionIn] = field(default_factory=list[RunnerRejectionIn])
    sources_valid: int = 0
    sources_invalid: int = 0
    items_truncated: int = 0
    redactions: int = 0


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


class _Assembler:
    def __init__(self, verifier: SourceVerifier, excerpt_max_lines: int) -> None:
        self._verifier = verifier
        self._excerpt_max_lines = excerpt_max_lines
        self.result = Assembly()
        # Module enrichment: union of the evidence of steps, messages and FAQ, in order.
        self._module_evidence: list[RunnerEvidenceIn] = []
        self._positions: dict[EvidenceKey, int] = {}

    def text(self, value: object, limit: int) -> str:
        clean, count = redact(_text(value))
        self.result.redactions += count
        return cut(clean, limit)

    def optional_text(self, value: object, limit: int) -> str | None:
        return None if value is None else self.text(value, limit)

    def block(self, output: Json, name: str) -> list[Json]:
        entries = cast(list[Json], output[name])
        limit = BLOCK_LIMITS[name]
        self.result.items_truncated += max(0, len(entries) - limit)
        return entries[:limit]

    def verify(self, entry: Json) -> list[CheckedSource]:
        # Sources beyond the per-item limit are dropped before verification.
        sources = cast(list[Json], entry["fontes"])[:MAX_SOURCES_PER_ITEM]
        checks = [self._verifier.check(source) for source in sources]
        valid = sum(1 for check in checks if check.valid)
        self.result.sources_valid += valid
        self.result.sources_invalid += len(checks) - valid
        return checks

    def evidence(self, check: CheckedSource) -> RunnerEvidenceIn:
        # Only valid sources get here, and a valid source always has a sendable path.
        path = cast(str, check.path)
        excerpt = make_excerpt(
            path, check.lines, check.start_line, check.end_line, self._excerpt_max_lines
        )
        self.result.redactions += excerpt.redactions
        return RunnerEvidenceIn(
            path=path,
            start_line=check.start_line,
            end_line=check.end_line,
            symbol=self.optional_text(check.symbol, SYMBOL_CHARS),
            excerpt=excerpt.text,
            excerpt_truncated=excerpt.truncated,
            excerpt_omitted=excerpt.omitted,
            redacted=excerpt.redactions > 0,
        )

    def accepted(
        self, block: RejectionBlock, index: int, label: object, entry: Json
    ) -> list[CheckedSource] | None:
        """The valid sources of ENTRY, or None after recording its rejection."""
        checks = self.verify(entry)
        code = rejection_code(checks)
        if code is None:
            return [check for check in checks if check.valid]
        self.reject(block, index, label, checks, code)
        return None

    def reject(
        self,
        block: RejectionBlock,
        index: int,
        label: object,
        checks: Sequence[CheckedSource],
        code: RejectionCode,
    ) -> None:
        if len(self.result.rejections) >= MAX_REJECTIONS:
            return
        sources = [
            RunnerRejectionSource(
                path=check.path,
                start_line=check.start_line,
                end_line=check.end_line,
                symbol=self.optional_text(check.symbol, SYMBOL_CHARS),
                # Every source of a rejected entry failed, so each one has its own code.
                code=check.code or code,
            )
            for check in checks
        ]
        self.result.rejections.append(
            RunnerRejectionIn(
                block=block,
                index=index,
                label=self.text(label, LABEL_CHARS),
                code=code,
                reason=REASONS[code],
                sources=sources,
            )
        )

    def rules(self, output: Json) -> None:
        for index, rule in enumerate(self.block(output, "regras")):
            valid = self.accepted("regras", index, rule["titulo"], rule)
            if valid is None:
                continue
            parameters = cast(list[object], rule["parametros"])[:MAX_PARAMETERS]
            # The enums were checked against the schema; pydantic checks them again.
            content = RuleContent.model_validate(
                {
                    "enunciado": self.text(rule["enunciado"], LONG_CHARS),
                    "quando": self.text(rule["quando"], LONG_CHARS),
                    "mensagem": self.optional_text(rule["mensagem"], MESSAGE_CHARS),
                    "resolucao": self.text(rule["resolucao"], LONG_CHARS),
                    "parametros": [self.text(name, PARAMETER_CHARS) for name in parameters],
                    "classificacao": rule["classificacao"],
                    "relevancia": rule["relevancia"],
                }
            )
            self.result.items.append(
                RuleItemIn(
                    kind="rule",
                    title=self.text(rule["titulo"], TITLE_CHARS),
                    content=content,
                    evidence=[self.evidence(check) for check in valid],
                )
            )

    def _indexes(self, valid: list[CheckedSource]) -> list[int]:
        """Positions of VALID in the module evidence, adding the new ones (no repetition)."""
        found: dict[int, None] = {}
        for check in valid:
            key = (cast(str, check.path), check.start_line, check.end_line)
            if key not in self._positions:
                self._positions[key] = len(self._module_evidence)
                self._module_evidence.append(self.evidence(check))
            found[self._positions[key]] = None
        return list(found)

    def _subitems[T](
        self,
        output: Json,
        block: RejectionBlock,
        label_key: str,
        build: Callable[[Json, list[int]], T],
    ) -> list[T]:
        built: list[T] = []
        for index, entry in enumerate(self.block(output, block)):
            valid = self.accepted(block, index, entry[label_key], entry)
            if valid is not None:
                built.append(build(entry, self._indexes(valid)))
        return built

    def module(self, output: Json, title: str) -> None:
        """The module enrichment; sent only if a step, message or FAQ entry survives."""
        steps = self._subitems(
            output,
            "fluxo_principal",
            "passo",
            lambda step, indexes: FlowStep(
                ordem=cast(int, step["ordem"]),
                passo=self.text(step["passo"], LONG_CHARS),
                evidencias=indexes,
            ),
        )
        messages = self._subitems(
            output,
            "mensagens",
            "mensagem",
            lambda message, indexes: ModuleMessage(
                mensagem=self.text(message["mensagem"], MESSAGE_CHARS),
                causa=self.text(message["causa"], LONG_CHARS),
                acao=self.text(message["acao"], LONG_CHARS),
                evidencias=indexes,
            ),
        )
        faq = self._subitems(
            output,
            "faq",
            "pergunta",
            lambda entry, indexes: FaqEntry(
                pergunta=self.text(entry["pergunta"], QUESTION_CHARS),
                resposta=self.text(entry["resposta"], LONG_CHARS),
                evidencias=indexes,
            ),
        )
        questions = [
            OpenQuestion(
                pergunta=self.text(question["pergunta"], QUESTION_CHARS),
                contexto=self.text(question["contexto"], LONG_CHARS),
            )
            for question in self.block(output, "duvidas")
        ]
        if not (steps or messages or faq):
            self.reject("objetivo", 0, title, [], "no_valid_source")
            return
        content = ModuleContent(
            objetivo=self.text(output["objetivo"], LONG_CHARS),
            fluxo_principal=steps,
            mensagens=messages,
            faq=faq,
            duvidas=questions,
        )
        self.result.items.append(
            ModuleItemIn(
                kind="module",
                title=self.text(title, TITLE_CHARS),
                content=content,
                evidence=self._module_evidence,
            )
        )


def assemble(
    output: Json, checkout: Path, *, excerpt_max_lines: int, module_title: str
) -> Assembly:
    """Verify OUTPUT (valid against the schema) in CHECKOUT and build the result items."""
    assembler = _Assembler(SourceVerifier(checkout), excerpt_max_lines)
    assembler.rules(output)
    assembler.module(output, module_title)
    return assembler.result
