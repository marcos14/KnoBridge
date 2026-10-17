"""The ``search_sources`` tool of multi-step search and the sources an answer accumulates
(``docs/specs/chat.md``, "Busca em etapas").

Pure code (no IO): the tool definition sent to the provider, the validation of the model's
arguments, the fixed texts of the tool result and ``SourceList``, the numbered sources of one
answer (the first search's, then each step's new ones, without repeating a source already
listed, up to ``MAX_TURN_SOURCES``).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Literal, cast

from knobridge.audit.models import JSONValue
from knobridge.conversations.prompt import source_block
from knobridge.conversations.retrieval import Source, citation
from knobridge.llm.provider import ToolSpec

SEARCH_TOOL_NAME = "search_sources"
QUERY_MAX_LENGTH = 500
# Budget of the sources of one step (the first search keeps the retriever's 6000).
STEP_CONTEXT_TOKENS = 3000
# Most sources of one answer, over all its steps.
MAX_TURN_SOURCES = 30
# Past this, the next round is the final one, so an answer never reaches the 5 minutes after
# which a ``streaming`` message reads as interrupted (``stale.py``).
TURN_DEADLINE = timedelta(seconds=240)
RETRIEVAL_VERSION = 1

SEARCH_TOOL = ToolSpec(
    name=SEARCH_TOOL_NAME,
    description=(
        "Busca mais trechos nas fontes do produto, no nível desta conversa. Use quando as "
        "fontes listadas não bastarem para responder: escreva uma consulta nova, com outros "
        "termos (sinônimos, nomes de telas, campos, mensagens, rotinas, tabelas ou colunas), "
        "em vez de repetir a pergunta. Devolve as fontes novas numeradas, que você pode citar "
        "como as demais."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Consulta de busca, em poucas palavras, no idioma das fontes.",
                "minLength": 1,
                "maxLength": QUERY_MAX_LENGTH,
            }
        },
        "required": ["query"],
        "additionalProperties": False,
    },
)

INVALID_QUERY = 'Consulta inválida: envie {"query": "..."} com até 500 caracteres.'
ONE_AT_A_TIME = "Uma busca por vez: esta chamada foi ignorada."
LIMIT_REACHED = "Limite de fontes desta resposta atingido; responda com as fontes listadas."
SEARCH_FAILED = (
    "A busca falhou agora; responda com as fontes listadas ou com a mensagem de sem fonte."
)
NO_NEW_SOURCES = "Nenhuma fonte nova para esta consulta."

# ``off``: not offered (no collection or a single step); ``unsupported``: the model refuses
# tool calls; ``offered``: offered, not called; ``used``: at least one step by the tool.
type ToolsState = Literal["off", "unsupported", "offered", "used"]
type SearchStatus = Literal["ok", "empty", "failed"]


def parse_query(arguments: str) -> str | None:
    """The query of a ``search_sources`` call, stripped; ``None`` when invalid."""
    try:
        parsed: object = json.loads(arguments)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    query = cast(dict[str, object], parsed).get("query")
    if not isinstance(query, str):
        return None
    query = query.strip()
    return query if 1 <= len(query) <= QUERY_MAX_LENGTH else None


def _listed(indexes: Sequence[int]) -> str:
    return "Já listadas: " + ", ".join(f"[{index}]" for index in indexes) + "."


@dataclass(frozen=True)
class Added:
    """What one search added: the new sources with their numbers and the numbers of the ones
    already listed (in the order the search returned them)."""

    new: tuple[tuple[int, Source], ...]
    already: tuple[int, ...]

    def tool_result(self) -> str:
        """The text the model reads back from the tool."""
        if not self.new:
            lines = [NO_NEW_SOURCES]
            if self.already:
                lines.append(_listed(self.already))
            return "\n".join(lines)
        blocks = [source_block(index, source) for index, source in self.new]
        text = "Fontes novas:\n\n" + "\n\n".join(blocks)
        if self.already:
            text += "\n\n" + _listed(self.already)
        return text


@dataclass
class SourceList:
    """The numbered sources of one answer; a source is the same when its ``document_id`` and
    ``uri`` are."""

    with_evidence: bool
    items: list[Source] = field(default_factory=lambda: [])
    _numbers: dict[tuple[str | None, str | None], int] = field(default_factory=lambda: {})

    @property
    def full(self) -> bool:
        return len(self.items) >= MAX_TURN_SOURCES

    def add(self, found: Sequence[Source]) -> Added:
        new: list[tuple[int, Source]] = []
        already: list[int] = []
        for source in found:
            key = (source.document_id, source.uri)
            number = self._numbers.get(key)
            if number is not None:
                if number not in already:
                    already.append(number)
                continue
            if self.full:
                break
            self.items.append(source)
            self._numbers[key] = len(self.items)
            new.append((len(self.items), source))
        return Added(tuple(new), tuple(already))

    def citations(self) -> list[JSONValue]:
        return [
            citation(index, source, with_evidence=self.with_evidence)
            for index, source in enumerate(self.items, start=1)
        ]


def search_record(
    *,
    step: int,
    query: str | None,
    status: SearchStatus,
    sources: int,
    new_sources: int,
    duration_ms: int,
) -> JSONValue:
    """One entry of ``retrieval.searches`` (never the content of a chunk)."""
    return {
        "step": step,
        "query": query,
        "status": status,
        "sources": sources,
        "new_sources": new_sources,
        "duration_ms": duration_ms,
    }


def retrieval_summary(
    tools: ToolsState, reranked: bool, searches: Sequence[JSONValue]
) -> dict[str, JSONValue]:
    """``messages.retrieval``: the summary of the searches of an answer."""
    return {
        "version": RETRIEVAL_VERSION,
        "tools": tools,
        "reranked": reranked,
        "searches": list(searches),
    }
