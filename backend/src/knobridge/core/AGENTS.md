# backend/src/knobridge/core/

**Função**: infraestrutura transversal usada por todos os módulos: configuração, logging estruturado, erros de domínio e acesso async ao banco. Mais tarde: segurança e ids.

**Entra aqui**:
- `settings.py`: `Settings` (pydantic-settings, prefixo `KNOBRIDGE_`, `.env` opcional) e `get_settings()` com cache. **Único lugar que lê variável de ambiente.**
- `logging.py`: `configure_logging(settings)` (JSON via structlog, inclusive para o logging da stdlib), `get_logger(name)` e `log_context(workspace_id=, run_id=, conversation_id=)`.
- `db.py`: `create_engine(settings)` (`AsyncEngine` com pool e timeout de conexão), `create_session_factory(engine)`, `ping(engine)` (`SELECT 1`) e as dependências FastAPI `get_engine` e `get_session` (uma sessão por requisição, sempre fechada; transação é responsabilidade de quem usa). Engine e fábrica ficam em `app.state`, criados pelo lifespan de `create_app`.
- `errors.py`: `KnoBridgeError` e subclasses genéricas (`NotFoundError`, `ValidationError`, `ConflictError`, `ServiceUnavailableError`), e `register_error_handlers(app)`, que garante o formato `{"error": {"code", "message", "details"}}` em toda resposta de erro.

**Não entra aqui**: regra de negócio, modelos de domínio, routers (vão para `api/`), adaptadores de provedores externos (`llm/`, `connectors/`, `channels/`).

**Convenções locais**:
- `core/` não importa nenhum outro módulo de `knobridge` (só bibliotecas e outros arquivos de `core/`).
- Variável nova de ambiente: campo em `Settings` + linha comentada em `backend/.env.example` + teste, na mesma entrega.
- Erro novo de domínio: subclasse de `KnoBridgeError` com `code` em snake_case e `status_code` HTTP correto, com teste.
- Segredos em `Settings` são `SecretStr` (ex.: `database_url`); leia com `get_secret_value()` só no ponto de uso.
- Nunca logar segredo, prompt completo, chunk completo ou dado pessoal em INFO.

**Como testar**: de `backend/`, `uv run pytest tests/core` (o gate de cobertura vale para a suíte inteira: `uv run pytest`).

**Leia também**: seções 5 e 6 do [AGENTS.md da raiz](../../../../AGENTS.md); [backend/AGENTS.md](../../../AGENTS.md).
