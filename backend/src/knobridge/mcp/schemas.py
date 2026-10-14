"""Input and output models of the MCP tools (``docs/specs/mcp.md``, "Ferramentas").

The tools publish these models' JSON Schemas as ``inputSchema`` and ``outputSchema``. Unknown
input fields are ignored. Citations are the chat's objects (``conversations/retrieval.py:
citation``), carried as JSON.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from knobridge.audit.models import JSONValue
from knobridge.conversations.models import MessageStatus
from knobridge.levels.level import ResponseLevel
from knobridge.tickets.models import TicketRequestStatus
from knobridge.tickets.wire import Email

PRODUCT_MAX_LENGTH = 200
QUESTION_MAX_LENGTH = 8000
SUMMARY_MAX_LENGTH = 2000
REQUESTER_NAME_MAX_LENGTH = 200
QUERY_MAX_LENGTH = 2000
DEFAULT_SEARCH_LIMIT = 8
MAX_SEARCH_LIMIT = 20
RESULT_CONTENT_MAX_CHARS = 4000
DEFAULT_DOCUMENT_CHARS = 20_000
MIN_DOCUMENT_CHARS = 1000
MAX_DOCUMENT_CHARS = 50_000
MAX_LISTED_PRODUCTS = 200

ProductRef = Annotated[str, StringConstraints(min_length=1, max_length=PRODUCT_MAX_LENGTH)]
Citation = dict[str, JSONValue]


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ListProductsIn(ToolInput):
    pass


class ProductOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    levels: list[ResponseLevel]
    default_level: ResponseLevel
    ticket_enabled: bool


class ListProductsOut(BaseModel):
    max_level: ResponseLevel
    products: list[ProductOut]
    truncated: bool


class SearchKnowledgeIn(ToolInput):
    product: ProductRef = Field(description="Id ou nome exato do produto.")
    query: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=QUERY_MAX_LENGTH),
    ] = Field(description="O que procurar, em linguagem natural ou com identificadores.")
    level: ResponseLevel | None = Field(
        default=None, description="Nível de resposta; padrão: o máximo da chave."
    )
    limit: int = Field(
        default=DEFAULT_SEARCH_LIMIT,
        ge=1,
        le=MAX_SEARCH_LIMIT,
        strict=True,
        description="Quantos trechos devolver.",
    )


class SearchResultOut(BaseModel):
    index: int
    content: str
    content_truncated: bool
    score: float
    citation: Citation


class SearchKnowledgeOut(BaseModel):
    product_id: uuid.UUID
    product_name: str
    level: ResponseLevel
    results: list[SearchResultOut]
    note: str | None


class GetDocumentIn(ToolInput):
    product: ProductRef = Field(description="Id ou nome exato do produto do documento.")
    document_id: uuid.UUID = Field(description="O document_id de uma citação.")
    level: ResponseLevel | None = Field(
        default=None, description="Nível de resposta; padrão: o máximo da chave."
    )
    offset: int = Field(
        default=0, ge=0, strict=True, description="Posição do primeiro trecho (next_offset)."
    )
    max_chars: int = Field(
        default=DEFAULT_DOCUMENT_CHARS,
        ge=MIN_DOCUMENT_CHARS,
        le=MAX_DOCUMENT_CHARS,
        strict=True,
        description="Soma máxima do conteúdo das partes devolvidas.",
    )


class DocumentOut(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    uri: str
    language: str | None


class DocumentPartOut(BaseModel):
    position: int
    start_line: int | None
    end_line: int | None
    symbol: str | None
    content: str
    truncated: bool


class GetDocumentOut(BaseModel):
    product_id: uuid.UUID
    level: ResponseLevel
    document: DocumentOut
    citation: Citation | None
    parts: list[DocumentPartOut]
    next_offset: int | None


class AskIn(ToolInput):
    product: ProductRef = Field(description="Id ou nome exato do produto.")
    question: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=QUESTION_MAX_LENGTH),
    ] = Field(description="A pergunta, em linguagem natural.")
    level: ResponseLevel | None = Field(
        default=None,
        description="Nível de resposta; padrão: o máximo da chave. Numa conversa continuada, "
        "se informado, tem de ser o nível dela.",
    )
    conversation_id: uuid.UUID | None = Field(
        default=None, description="Continua uma conversa criada por ask (o conversation_id dela)."
    )


class AskOut(BaseModel):
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    level: ResponseLevel
    status: MessageStatus
    answer: str
    citations: list[Citation]
    ticket_enabled: bool
    model: str | None
    cost_usd: float | None


RequesterName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=REQUESTER_NAME_MAX_LENGTH),
]


class OpenTicketIn(ToolInput):
    message_id: uuid.UUID = Field(description="O message_id de uma resposta de ask.")
    summary: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=SUMMARY_MAX_LENGTH),
    ] = Field(description="Resumo do problema para a equipe do produto.")
    requester_email: Email = Field(description="E-mail de quem pede, para a equipe responder.")
    requester_name: RequesterName | None = Field(default=None, description="Nome de quem pede.")


class OpenTicketOut(BaseModel):
    ticket_request_id: uuid.UUID
    status: TicketRequestStatus
    conversation_id: uuid.UUID
    message_id: uuid.UUID
