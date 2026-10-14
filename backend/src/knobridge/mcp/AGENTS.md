# backend/src/knobridge/mcp/

**Função**: o servidor MCP do KnoBridge em `/v1/mcp`, para IDEs e agentes (Claude Code, Cursor, Codex), autenticado pela chave `kbk_` com o escopo de produtos e o nível máximo dela ([ADR 0009](../../../../docs/adr/0009-canais-mcp-e-widget.md); contrato em [mcp.md](../../../../docs/specs/mcp.md)). SDK oficial `mcp` 2.x (`MCPServer`), Streamable HTTP sem estado com resposta JSON. Plano 0010: F2.1 (servidor, `list_products`, `search_knowledge`, `get_document`); `ask` e `open_ticket` entram na F2.2.

**Entra aqui**:
- `server.py`: `build_server()` (um `MCPServer("knobridge")` novo por app, com as instruções e as ferramentas; o gerenciador de sessões do SDK só roda uma vez), os textos das descrições em pt-BR, `_run` (valida os argumentos pelos modelos de `schemas.py`, abre `scoped_session` no workspace da chave sem `app.user_id`, transforma `KnoBridgeError` em resultado de erro `{"error": {code, message, details}}`, argumento inválido em `validation_error` com `[{loc, problem}]` e falha inesperada em `internal_error` logada só pelo tipo; loga `mcp_tool_called` com `tool`, `workspace_id`, `api_key_id`, `outcome` e `latency_ms`, nunca argumentos nem conteúdo), `allowed_hosts` e `transport_security` (`TransportSecuritySettings` com `KNOBRIDGE_MCP_ALLOWED_HOSTS`/`_ORIGINS`).
- `auth.py`: `McpEndpoint`, o invólucro ASGI na frente do handler do SDK: `Origin` fora de `KNOBRIDGE_MCP_ALLOWED_ORIGINS` → 403 `origin_not_allowed`; método diferente de `POST` → 405 `method_not_allowed` com `Allow: POST`; chave por `apikeys.auth.authenticate_api_key` e `touch_last_used` numa transação curta em modo de sistema (401 `invalid_api_key`, 403 `workspace_suspended`). Erros saem em HTTP no formato único, pelos handlers do app.
- `context.py`: `McpServices` (sessões, relógio, `SearchService`), `McpCall` e a `ContextVar` que o invólucro preenche (`bound`) e as ferramentas leem (`current_call`, `current_identity`).
- `schemas.py`: modelos Pydantic de entrada (campos desconhecidos ignorados) e saída de cada ferramenta e os limites da spec.
- `tools.py`: `list_products` (até 200, `truncated`), `resolve_product` (id ou nome exato visível à chave, senão `not_found`; depois `level_not_allowed`), `search_knowledge` (o `SearchService` nas coleções do produto, com o `min_similarity` dele e o nível; sem coleção, sem embedding; conteúdo com a linha de chamado ou card, cortado em 4000) e `cite` (a citação do chat, sem evidências em `end_user`).
- `documents.py`: `get_document` em três statements (produto, documento com a checagem de visibilidade, partes por janela no SQL com o filtro de nível), paginado por `offset`/`max_chars`.

**Não entra aqui**: a montagem no FastAPI e as dependências do app (`api/mcp_channel.py`), a busca (`retrieval/`), as chaves (`apikeys/`), a rodada de chat (`conversations/`).

**Convenções locais**:
- Nenhuma ferramenta desta pasta chama o LLM. Só `search_knowledge` chama o embedding.
- O SDK valida os argumentos pela assinatura da função: as funções das ferramentas recebem tudo como `Any` (`ToolArgument`) e o `inputSchema` publicado é o do modelo de `schemas.py`, que é quem valida de fato.
- Produto inexistente, inativo ou fora do escopo é sempre `not_found`; documento acima do nível responde igual a documento inexistente.

**Como testar**: de `backend/`, `uv run pytest tests/mcp tests/api/test_mcp_auth.py tests/api/test_mcp_tools.py tests/api/test_mcp_documents.py` (os de `tests/api` exigem Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [tests/mcp/AGENTS.md](../../../tests/mcp/AGENTS.md); [apikeys/AGENTS.md](../apikeys/AGENTS.md); [retrieval/AGENTS.md](../retrieval/AGENTS.md); [api/AGENTS.md](../api/AGENTS.md).
