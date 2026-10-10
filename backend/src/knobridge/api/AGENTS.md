# backend/src/knobridge/api/

**Função**: fronteira HTTP do backend. A factory `create_app()` monta a aplicação FastAPI (logging, CORS, handlers de erro) e inclui todos os routers sob `/v1`.

**Entra aqui**:
- `app.py`: `create_app(settings=None, engine=None, *, clock=None, password_hasher=None)` e `serve()` (comando `knobridge-api`). A factory guarda em `app.state` as `Settings` (lidas por dependências como `security.csrf.require_csrf`), o `clock` (padrão `SystemClock`) e o `password_hasher` (padrão argon2id de produção); testes injetam `FrozenClock` e parâmetros baratos. O lifespan guarda engine e fábrica de sessões em `app.state`; descarta no shutdown só o engine que ele mesmo criou (o injetado, usado em testes, é do chamador).
- `openapi.py`: comando `knobridge-openapi` (`--output`, padrão `docs/specs/openapi.json` na raiz do repositório), que grava o OpenAPI de `create_app` com saída determinística (chaves ordenadas, indentação 2, newline final). Não precisa de banco.
- Um módulo por recurso com o seu `APIRouter` e schemas Pydantic de entrada e saída:
  - `health.py`: `GET /v1/health/live` e `GET /v1/health/ready` (`SELECT 1`; 503 `service_unavailable` sem expor a mensagem do driver).
  - `setup.py`: `GET /v1/setup/status` (`needs_setup`) e `POST /v1/setup` (cria o superadmin só enquanto não há usuário; 409 `setup_already_completed`).
  - `auth.py`: `GET /v1/auth/csrf` (renova o cookie CSRF e devolve o token), `POST /v1/auth/login` (401 `invalid_credentials` genérico; 429 `too_many_attempts`), `POST /v1/auth/logout` e `POST /v1/auth/logout-all` (204). Helpers `start_browser_session` (cookie de sessão + cookie CSRF) e `clear_browser_session`.
  - `me.py`: `GET /v1/me` (usuário, workspaces com papel, `is_superadmin`) e `build_me`, também usado como resposta de login e setup.
  - `audit.py`: `GET /v1/workspaces/{workspace_id}/audit` (owner/admin; filtros `action`, `actor_user_id`, `occurred_from`, `occurred_to`; `limit`/`offset`).
- `deps.py`: as dependências compartilhadas (abaixo). A lógica de autenticação, setup e consultas fica em `tenancy/`; aqui só se monta o serviço e se lê o cookie.

**Não entra aqui**: regra de negócio (fica no módulo de domínio; o router só valida, chama e serializa), acesso direto a banco, leitura de variável de ambiente (use `core/settings.py`), API compatível com OpenAI e webhooks de canais (vão para `channels/`).

**Padrão de dependências** (`deps.py`):
- `CurrentUserDep` (`current_user`): valida o cookie de sessão (expiração deslizante) e devolve `AuthenticatedUser(user, session_id)`; sem sessão viva ou com usuário suspenso, 401 `unauthenticated`.
- `require_superadmin`: 403 `forbidden` se o usuário não é superadmin. Rotas de instância usam `system_session` depois dela.
- `WorkspaceContextDep` (`workspace_context(workspace_id)`, `scope="function"`): confirma a membership do usuário (não membro: 404 `not_found`, sem revelar se o workspace existe) e o workspace ativo (403 `workspace_suspended`), e entrega `WorkspaceContext(workspace_id, current, role, db)`, com `db` numa transação com `SET LOCAL` de `app.workspace_id` e `app.user_id`. O commit acontece antes da resposta sair; não abra outra sessão para dados do workspace.
- `require_role(Role.X)`: fábrica de dependência sobre o contexto; hierarquia owner > admin > editor > viewer; abaixo do mínimo, 403 `forbidden` com `details.required_role`. Uso: `context: Annotated[WorkspaceContext, Depends(require_role(Role.ADMIN))]`.
- Serviços (`AuthServiceDep`, `SetupServiceDep`), `SettingsDep`, `SessionFactoryDep` e `ClientIpDep` vêm de `app.state`.
- **CSRF**: toda rota não segura que usa o cookie de sessão declara `dependencies=[Depends(require_csrf)]`. Exceções: `POST /v1/auth/login` e `POST /v1/setup`, que só fazem sentido antes de existir sessão (não há sessão a sequestrar; o cookie é `SameSite=Lax` e o corpo é JSON). Login e setup emitem o cookie CSRF; `GET /v1/auth/csrf` renova.

**Convenções locais**:
- Todo router é incluído no router `/v1` de `create_app`; nada fora de `/v1` além do OpenAPI.
- Toda rota declara o tipo de retorno com um schema Pydantic; nunca devolva modelo ORM.
- Erros saem como `KnoBridgeError` (de `core/errors.py`); não monte JSON de erro à mão.
- `workspace_id` vem da autenticação, nunca do corpo ou da query da API pública.
- Listagens sempre paginadas.
- Mudou rota ou schema: `uv run knobridge-openapi` e commite `docs/specs/openapi.json` na mesma entrega (o frontend gera os tipos dele).

**Como testar**: de `backend/`, `uv run pytest tests/api`; os testes sem banco usam a fixture `client` de `tests/conftest.py`, e os com banco, `api`/`empty_api` de `tests/api/conftest.py`.

**Leia também**: [backend/AGENTS.md](../../../AGENTS.md); [core/AGENTS.md](../core/AGENTS.md); seção 6.1 do [AGENTS.md da raiz](../../../../AGENTS.md).
