# backend/src/knobridge/api/

**Função**: fronteira HTTP do backend. A factory `create_app()` monta a aplicação FastAPI (logging, CORS, handlers de erro) e inclui todos os routers sob `/v1`.

**Entra aqui**:
- `app.py`: `create_app(settings=None, engine=None)` e `serve()` (comando `knobridge-api`). A factory guarda as `Settings` em `app.state.settings` (lidas por dependências como `security.csrf.require_csrf`); o lifespan guarda engine e fábrica de sessões em `app.state`; descarta no shutdown só o engine que ele mesmo criou (o injetado, usado em testes, é do chamador).
- `openapi.py`: comando `knobridge-openapi` (`--output`, padrão `docs/specs/openapi.json` na raiz do repositório), que grava o OpenAPI de `create_app` com saída determinística (chaves ordenadas, indentação 2, newline final). Não precisa de banco.
- Um módulo por recurso com o seu `APIRouter` e schemas Pydantic de entrada e saída (hoje `health.py`: `GET /v1/health/live` e `GET /v1/health/ready`, que faz `SELECT 1` e responde 503 `service_unavailable` sem expor a mensagem do driver).
- Dependências FastAPI de API (autenticação, workspace corrente) quando existirem. Sessão de banco: use `get_session` de `core/db.py`.

**Não entra aqui**: regra de negócio (fica no módulo de domínio; o router só valida, chama e serializa), acesso direto a banco, leitura de variável de ambiente (use `core/settings.py`), API compatível com OpenAI e webhooks de canais (vão para `channels/`).

**Convenções locais**:
- Todo router é incluído no router `/v1` de `create_app`; nada fora de `/v1` além do OpenAPI.
- Toda rota declara o tipo de retorno com um schema Pydantic; nunca devolva modelo ORM.
- Erros saem como `KnoBridgeError` (de `core/errors.py`); não monte JSON de erro à mão.
- `workspace_id` vem da autenticação, nunca do corpo ou da query da API pública.
- Listagens sempre paginadas.
- Mudou rota ou schema: `uv run knobridge-openapi` e commite `docs/specs/openapi.json` na mesma entrega (o frontend gera os tipos dele).

**Como testar**: de `backend/`, `uv run pytest tests/api`; os testes usam a fixture `client` (TestClient sobre `create_app`) de `tests/conftest.py`.

**Leia também**: [backend/AGENTS.md](../../../AGENTS.md); [core/AGENTS.md](../core/AGENTS.md); seção 6.1 do [AGENTS.md da raiz](../../../../AGENTS.md).
