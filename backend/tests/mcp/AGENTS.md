# backend/tests/mcp/

**Função**: testes unitários de `src/knobridge/mcp/` (servidor MCP, [docs/specs/mcp.md](../../../docs/specs/mcp.md)), sem banco e sem HTTP.

**Entra aqui**:
- `test_mcp_server.py`: as três ferramentas publicadas pelo `build_server` (nomes, `read_only_hint`, `inputSchema` igual ao modelo de `mcp/schemas.py`, `outputSchema`), os hosts e origens do SDK (`allowed_hosts`, `transport_security`, `KNOBRIDGE_MCP_ALLOWED_HOSTS`/`_ORIGINS`), a identidade lida fora de uma requisição (`McpContextMissingError`) e a recusa de `Origin` antes da chave no `McpEndpoint`.

**Não entra aqui**: o canal pelo cliente do SDK sobre HTTP com Postgres real (autenticação, ferramentas, nível, isolamento), que fica em `tests/api/test_mcp_auth.py`, `tests/api/test_mcp_tools.py` e `tests/api/test_mcp_documents.py`, com `tests/api/mcp_support.py`.

**Convenções locais**: sem rede, sem banco; o relógio e as fábricas de provedor nunca são necessários aqui.

**Como testar**: de `backend/`, `uv run pytest tests/mcp`. Gate da suíte inteira: `uv run pytest`.

**Leia também**: [src/knobridge/mcp/AGENTS.md](../../src/knobridge/mcp/AGENTS.md); [tests/api/AGENTS.md](../api/AGENTS.md).
