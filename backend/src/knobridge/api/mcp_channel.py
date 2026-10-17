"""Mounts the MCP server at ``/v1/mcp`` (``docs/specs/mcp.md``, "Transporte").

Streamable HTTP without state and with JSON responses, served at ``/v1/mcp`` and ``/v1/mcp/``
by two plain routes (a ``Mount`` would redirect the path without the slash, and many clients
do not repeat a ``POST`` after a 307). The routes are Starlette ``Route``s, so they stay out of
the OpenAPI: the contract is the spec. The caller runs ``server.session_manager.run()`` in the
app's lifespan (a mounted sub-app does not run its own).

The tools get the app's services (``mcp.context.McpServices``) built per request like the
routes' dependencies, honoring ``app.dependency_overrides`` of the embedding and LLM provider
factories, of the reranker and of the ticket delivery starter, so tests swap them the same
way.
"""

from __future__ import annotations

from fastapi import FastAPI
from mcp.server.mcpserver import MCPServer
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp
from starlette.routing import Route

from knobridge.api.deps import get_embedding_provider_factory, get_provider_factory, get_reranker
from knobridge.api.ticket_requests import get_ticket_webhook_starter
from knobridge.conversations.chat import ChatService
from knobridge.core.crypto import SecretBox
from knobridge.core.settings import Settings
from knobridge.llm.chat_pricing import ChatPriceTable
from knobridge.llm.credentials import CREDENTIALS_KEY_INFO, ProviderCredentialService
from knobridge.llm.factory import EmbeddingProviderFactory, ProviderFactory
from knobridge.mcp.auth import McpEndpoint
from knobridge.mcp.context import McpServices
from knobridge.mcp.server import build_server, transport_security
from knobridge.retrieval.rerank import InstanceReranker, instance_reranker
from knobridge.retrieval.retriever import HybridRetriever
from knobridge.retrieval.search import SearchService
from knobridge.tickets.delivery import TicketWebhookStarter
from knobridge.tickets.requests import TicketRequestService

MCP_PATH = "/v1/mcp"


def mcp_services(app: FastAPI, settings: Settings) -> McpServices:
    box = SecretBox.derive(settings.secret_key.get_secret_value(), info=CREDENTIALS_KEY_INFO)
    clock = app.state.clock
    factory = app.state.session_factory
    credentials = ProviderCredentialService(clock, box, allow_fake=settings.env != "production")
    overrides = app.dependency_overrides
    embeddings: EmbeddingProviderFactory = overrides.get(
        get_embedding_provider_factory, get_embedding_provider_factory
    )()
    providers: ProviderFactory = overrides.get(get_provider_factory, get_provider_factory)()
    starter: TicketWebhookStarter = (
        overrides[get_ticket_webhook_starter]()
        if get_ticket_webhook_starter in overrides
        else app.state.ticket_webhook_starter
    )
    reranker: InstanceReranker | None = (
        overrides[get_reranker]() if get_reranker in overrides else instance_reranker(settings)
    )
    search = SearchService(credentials, embeddings)
    return McpServices(
        factory=factory,
        clock=clock,
        search=search,
        reranker=reranker,
        chat=ChatService(
            clock=clock,
            retriever=HybridRetriever(search, reranker=reranker),
            provider_factory=providers,
            credentials=credentials,
            session_factory=factory,
            prices=ChatPriceTable.from_settings(settings),
        ),
        tickets=TicketRequestService(
            clock=clock,
            provider_factory=providers,
            credentials=credentials,
            public_base_url=settings.public_base_url,
        ),
        starter=starter,
    )


def mount_mcp(app: FastAPI, settings: Settings) -> MCPServer:
    """Add the ``/v1/mcp`` routes to ``app`` and return the server whose session manager the
    lifespan must run."""
    server = build_server()
    server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=transport_security(settings),
    )
    endpoint = McpEndpoint(
        StreamableHTTPASGIApp(server.session_manager),
        allowed_origins=settings.mcp_allowed_origins,
        services=lambda: mcp_services(app, settings),
    )
    for path in (MCP_PATH, f"{MCP_PATH}/"):
        app.router.routes.append(Route(path, endpoint=endpoint))
    return server
