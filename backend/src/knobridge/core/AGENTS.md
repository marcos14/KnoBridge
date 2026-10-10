# backend/src/knobridge/core/

**Função**: infraestrutura transversal usada por todos os módulos: configuração, logging estruturado, erros de domínio, base ORM, relógio injetável e acesso async ao banco com escopo de RLS. Mais tarde: ids. Primitivas de autenticação ficam em `security/`.

**Entra aqui**:
- `settings.py`: `Settings` (pydantic-settings, prefixo `KNOBRIDGE_`, `.env` opcional) e `get_settings()` com cache. **Único lugar que lê variável de ambiente.** Inclui as de autenticação (`secret_key`, que em produção não pode ficar no padrão `DEV_SECRET_KEY`; `session_ttl`; `session_cookie_name`; `cookie_secure`; `login_max_attempts` e `login_attempt_window`, da limitação de login), as de e-mail (`smtp_host`, `smtp_port`, `smtp_user`, `smtp_password` como `SecretStr`, `smtp_from`, `smtp_starttls`, `smtp_timeout`) e `public_base_url`, a URL do painel usada nos links dos e-mails.
- `logging.py`: `configure_logging(settings)` (JSON via structlog, inclusive para o logging da stdlib), `get_logger(name)` e `log_context(workspace_id=, run_id=, conversation_id=)`.
- `db.py`: `create_engine(settings)` (`AsyncEngine` com pool e timeout de conexão), `create_session_factory(engine)`, `ping(engine)` (`SELECT 1`) e as dependências FastAPI `get_engine` e `get_session` (uma sessão por requisição, sempre fechada; transação é responsabilidade de quem usa). Engine e fábrica ficam em `app.state`, criados pelo lifespan de `create_app`. Escopo de RLS: `scoped_session(factory, workspace_id=, user_id=)` abre sessão + transação e grava `app.workspace_id`/`app.user_id` com `set_config(..., true)` (o `SET LOCAL` parametrizado); `system_session(factory)` é o modo de sistema (`app.system = 'on'`), só para setup, superadmin e login; `apply_scope` e `apply_system_scope` fazem o mesmo numa transação já aberta. O escopo morre no commit.
- `models.py`: `Base` declarativa com `NAMING_CONVENTION` (nomes de restrição iguais nos modelos e nas migrações), mixins `UUIDPrimaryKeyMixin` e `TimestampMixin`, e `str_enum(enum, nome)` (enum como `VARCHAR` + `CHECK`, gravando o valor).
- `clock.py`: `Clock` (protocolo com `now()` em UTC com fuso), `SystemClock` (produção) e `FrozenClock` (testes; `advance`). Toda lógica que compara com "agora" recebe um `Clock` injetado.
- `errors.py`: `KnoBridgeError` e subclasses genéricas (`NotFoundError`, `ValidationError`, `ConflictError`, `UnauthenticatedError` 401, `ForbiddenError` 403, `TooManyRequestsError` 429, `ServiceUnavailableError`), e `register_error_handlers(app)`, que garante o formato `{"error": {"code", "message", "details"}}` em toda resposta de erro.

**Não entra aqui**: regra de negócio, modelos de domínio, routers (vão para `api/`), adaptadores de provedores externos (`llm/`, `connectors/`, `channels/`).

**Convenções locais**:
- `core/` não importa nenhum outro módulo de `knobridge` (só bibliotecas e outros arquivos de `core/`).
- Variável nova de ambiente: campo em `Settings` + linha comentada em `backend/.env.example` + teste, na mesma entrega.
- Erro novo de domínio: subclasse de `KnoBridgeError` com `code` em snake_case e `status_code` HTTP correto, com teste.
- Segredos em `Settings` são `SecretStr` (ex.: `database_url`); leia com `get_secret_value()` só no ponto de uso.
- Nunca logar segredo, prompt completo, chunk completo ou dado pessoal em INFO.

**Como testar**: de `backend/`, `uv run pytest tests/core` (o gate de cobertura vale para a suíte inteira: `uv run pytest`).

**Leia também**: [ADR 0001](../../../../docs/adr/0001-tenancy-e-rls.md) (RLS e modo de sistema); seções 5 e 6 do [AGENTS.md da raiz](../../../../AGENTS.md); [backend/AGENTS.md](../../../AGENTS.md).
