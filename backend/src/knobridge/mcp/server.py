"""The KnoBridge MCP server: ``MCPServer`` of the official SDK with the read-only tools
(``docs/specs/mcp.md``; ADR 0009).

A tool's arguments are validated here, against the models of ``mcp/schemas.py`` (also its
published ``inputSchema``), so a bad argument is a tool error result with ``validation_error``
and ``[{loc, problem}]`` like the rest of the API, not the SDK's own text. Domain errors
(``KnoBridgeError``) become tool error results with their code, message and details; anything
else is ``internal_error``, logged only by the exception type. Each call logs
``mcp_tool_called`` with the tool, workspace, key, outcome and latency, never the arguments nor
the content returned.
"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Annotated, Any
from urllib.parse import urlsplit

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.tools import Tool
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from pydantic_core import to_jsonable_python
from sqlalchemy.ext.asyncio import AsyncSession

from knobridge import __version__
from knobridge.core.db import scoped_session
from knobridge.core.errors import KnoBridgeError
from knobridge.core.logging import get_logger
from knobridge.core.settings import Settings
from knobridge.mcp.context import McpCall, current_call
from knobridge.mcp.documents import get_document
from knobridge.mcp.schemas import (
    GetDocumentIn,
    GetDocumentOut,
    ListProductsIn,
    ListProductsOut,
    SearchKnowledgeIn,
    SearchKnowledgeOut,
)
from knobridge.mcp.tools import list_products, search_knowledge

SERVER_NAME = "knobridge"
INSTRUCTIONS = (
    "KnoBridge responde dúvidas sobre os produtos da empresa a partir de fontes indexadas "
    "(documentação, código, chamados e cards). Use `list_products` para saber os produtos e "
    "níveis que esta chave alcança. Prefira `search_knowledge` (sem custo de LLM) e responda "
    "só com base nos trechos, citando cada afirmação com a fonte. Se nada for encontrado, diga "
    "que não sabe; não invente. Use `ask` para uma resposta pronta do KnoBridge e `open_ticket` "
    "para abrir um chamado a partir de uma resposta de `ask`."
)
LIST_PRODUCTS = (
    "Lista os produtos que esta chave pode consultar, com os níveis de resposta permitidos em "
    "cada um e o nível usado quando nenhum é informado."
)
SEARCH_KNOWLEDGE = (
    "Busca trechos das fontes de um produto (documentação, código, chamados, cards), só no "
    "nível permitido, sem gerar resposta. Responda a partir dos trechos e cite as fontes. Se "
    "`results` vier vazio, diga que não encontrou a informação."
)
GET_DOCUMENT = (
    "Lê o conteúdo de um documento citado por `search_knowledge` ou `ask` (pelo `document_id` "
    "da citação), só nas partes permitidas ao nível. Use `next_offset` para continuar "
    "documentos longos."
)
LOCAL_HOSTS = ("localhost:*", "127.0.0.1:*")
_READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)

# The SDK validates a tool's arguments against its function signature before calling it. Our
# tool functions take every argument as ``Any`` so that validation always passes and the
# arguments reach ``_run``, which validates them against the models of ``mcp/schemas.py``.
ToolArgument = Any

_log = get_logger(__name__)

type Operation[In: BaseModel, Out: BaseModel] = Callable[
    [AsyncSession, McpCall, In], Awaitable[Out]
]


def _result(body: Mapping[str, object], *, is_error: bool) -> CallToolResult:
    structured = to_jsonable_python(body)
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(structured, ensure_ascii=False))],
        structured_content=structured,
        is_error=is_error,
    )


def _error(code: str, message: str, details: object = None) -> CallToolResult:
    return _result({"error": {"code": code, "message": message, "details": details}}, is_error=True)


async def _run[In: BaseModel, Out: BaseModel](
    tool: str, model: type[In], operation: Operation[In, Out], arguments: Mapping[str, object]
) -> CallToolResult:
    call = current_call()
    identity = call.identity
    started = time.monotonic()
    try:
        request = model.model_validate({k: v for k, v in arguments.items() if v is not None})
        async with scoped_session(
            call.services.factory, workspace_id=identity.workspace_id, user_id=None
        ) as db:
            output = await operation(db, call, request)
        outcome, result = "ok", _result(output.model_dump(mode="json"), is_error=False)
    except PydanticValidationError as exc:
        problems = [{"loc": list(e["loc"]), "problem": e["msg"]} for e in exc.errors()]
        outcome = "validation_error"
        result = _error(outcome, "Invalid tool arguments.", problems)
    except KnoBridgeError as exc:
        outcome, result = exc.code, _error(exc.code, exc.message, exc.details)
    except Exception as exc:
        _log.error("mcp_tool_failed", tool=tool, error_type=type(exc).__name__)
        outcome = "internal_error"
        result = _error(outcome, "An unexpected error occurred.")
    _log.info(
        "mcp_tool_called",
        tool=tool,
        workspace_id=str(identity.workspace_id),
        api_key_id=str(identity.api_key_id),
        outcome=outcome,
        latency_ms=round((time.monotonic() - started) * 1000),
    )
    return result


async def _list_products(db: AsyncSession, call: McpCall, _: ListProductsIn) -> ListProductsOut:
    return await list_products(db, call.identity)


async def _search_knowledge(
    db: AsyncSession, call: McpCall, request: SearchKnowledgeIn
) -> SearchKnowledgeOut:
    return await search_knowledge(db, call.identity, call.services.search, request)


async def _get_document(db: AsyncSession, call: McpCall, request: GetDocumentIn) -> GetDocumentOut:
    return await get_document(db, call.identity, request)


async def list_products_tool() -> Annotated[CallToolResult, ListProductsOut]:
    return await _run("list_products", ListProductsIn, _list_products, {})


async def search_knowledge_tool(
    product: ToolArgument = None,
    query: ToolArgument = None,
    level: ToolArgument = None,
    limit: ToolArgument = None,
) -> Annotated[CallToolResult, SearchKnowledgeOut]:
    arguments = {"product": product, "query": query, "level": level, "limit": limit}
    return await _run("search_knowledge", SearchKnowledgeIn, _search_knowledge, arguments)


async def get_document_tool(
    product: ToolArgument = None,
    document_id: ToolArgument = None,
    level: ToolArgument = None,
    offset: ToolArgument = None,
    max_chars: ToolArgument = None,
) -> Annotated[CallToolResult, GetDocumentOut]:
    arguments = {
        "product": product,
        "document_id": document_id,
        "level": level,
        "offset": offset,
        "max_chars": max_chars,
    }
    return await _run("get_document", GetDocumentIn, _get_document, arguments)


def _tool(fn: Callable[..., Any], name: str, description: str, model: type[BaseModel]) -> Tool:
    tool = Tool.from_function(fn, name=name, description=description, annotations=_READ_ONLY)
    # Publish the schema the arguments are really validated against (see ``ToolArgument``).
    return tool.model_copy(update={"parameters": model.model_json_schema()})


def build_server() -> MCPServer:
    """A new server (each app has its own: the SDK's session manager runs only once)."""
    return MCPServer(
        SERVER_NAME,
        instructions=INSTRUCTIONS,
        version=__version__,
        tools=[
            _tool(list_products_tool, "list_products", LIST_PRODUCTS, ListProductsIn),
            _tool(search_knowledge_tool, "search_knowledge", SEARCH_KNOWLEDGE, SearchKnowledgeIn),
            _tool(get_document_tool, "get_document", GET_DOCUMENT, GetDocumentIn),
        ],
    )


def allowed_hosts(settings: Settings) -> list[str]:
    """``KNOBRIDGE_MCP_ALLOWED_HOSTS``, or the public host (with and without port) and the
    local ones."""
    if settings.mcp_allowed_hosts:
        return list(settings.mcp_allowed_hosts)
    host = (urlsplit(settings.public_base_url).hostname or "").lower()
    return list(dict.fromkeys([host, f"{host}:*", *LOCAL_HOSTS]))


def transport_security(settings: Settings) -> TransportSecuritySettings:
    """The SDK's ``Host``/``Origin`` protection (it answers 421 for a host not listed)."""
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts(settings),
        allowed_origins=list(settings.mcp_allowed_origins),
    )
