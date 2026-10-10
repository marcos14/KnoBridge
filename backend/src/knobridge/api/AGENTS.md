# backend/src/knobridge/api/

**Função**: fronteira HTTP do backend. A factory `create_app()` monta a aplicação FastAPI (logging, CORS, handlers de erro) e inclui todos os routers sob `/v1`.

**Entra aqui**:
- `app.py`: `create_app(settings=None)` e `serve()` (comando `knobridge-api`).
- Um módulo por recurso com o seu `APIRouter` e schemas Pydantic de entrada e saída (hoje `health.py`: `GET /v1/health/live`).
- Dependências FastAPI (autenticação, sessão, workspace corrente) quando existirem.

**Não entra aqui**: regra de negócio (fica no módulo de domínio; o router só valida, chama e serializa), acesso direto a banco, leitura de variável de ambiente (use `core/settings.py`), API compatível com OpenAI e webhooks de canais (vão para `channels/`).

**Convenções locais**:
- Todo router é incluído no router `/v1` de `create_app`; nada fora de `/v1` além do OpenAPI.
- Toda rota declara o tipo de retorno com um schema Pydantic; nunca devolva modelo ORM.
- Erros saem como `KnoBridgeError` (de `core/errors.py`); não monte JSON de erro à mão.
- `workspace_id` vem da autenticação, nunca do corpo ou da query da API pública.
- Listagens sempre paginadas.

**Como testar**: de `backend/`, `uv run pytest tests/api`; os testes usam a fixture `client` (TestClient sobre `create_app`) de `tests/conftest.py`.

**Leia também**: [backend/AGENTS.md](../../../AGENTS.md); [core/AGENTS.md](../core/AGENTS.md); seção 6.1 do [AGENTS.md da raiz](../../../../AGENTS.md).
