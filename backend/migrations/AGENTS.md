# backend/migrations/

**Função**: migrações do banco (Alembic, modo async com `asyncpg`). É a única forma de mudar o schema do Postgres do KnoBridge.

**Entra aqui**:
- `env.py`: ambiente do Alembic; lê a URL de `KNOBRIDGE_DATABASE_URL` via `knobridge.core.settings` (ou de `config.attributes["database_url"]`, usado pelos testes) e roda as migrações com engine async e `NullPool`. `target_metadata` é `Base.metadata`; todo módulo com modelos ORM é importado ali (e em `tests/migrations/test_migrations.py`) para o autogenerate e o teste de divergência enxergarem as tabelas.
- `script.py.mako`: modelo das revisões novas.
- `versions/`: uma revisão por arquivo, gerada por `uv run alembic revision -m "..."` (pasta gerada, sem `AGENTS.md`). Hoje: `0001` habilita a extensão `vector` (pgvector); `0002` cria `users`, `workspaces` e `memberships` com RLS forçada e as políticas do [ADR 0001](../../docs/adr/0001-tenancy-e-rls.md); `0003` cria `sessions` e `user_tokens` com RLS forçada por `user_id` ([ADR 0002](../../docs/adr/0002-sessao-server-side.md)); `0004` cria `audit_events` com RLS forçada e políticas separadas de leitura, inserção e exclusão (sem UPDATE); `0005` cria `login_attempts` (limitação de login) com RLS forçada só para modo de sistema; `0006` cria `invitations` (RLS forçada, política padrão de workspace) e dá a `user_tokens` um `workspace_id` opcional (só em tokens de convite), ampliando `user_tokens_owner` para esse workspace; `0007` cria `provider_credentials` (chaves de provedor de LLM cifradas, RLS forçada, política padrão de workspace; [ADR 0003](../../docs/adr/0003-segredos-cifrados.md)).

**Não entra aqui**: modelos ORM (vão para o módulo de domínio em `src/knobridge/`), dados de seed ou de clientes, SQL solto fora de revisão, configuração (fica em `core/settings.py`; `alembic.ini` fica em `backend/`).

**Convenções locais**:
- Uma migração por mudança de modelo, na mesma entrega do código que a usa.
- Toda migração é reversível: `downgrade()` desfaz exatamente o `upgrade()`. Nada de `pass` no downgrade.
- Tabela de dado da instância ligada a um usuário (ex.: `sessions`, `user_tokens`) não tem `workspace_id` obrigatório, mas também tem RLS forçada, com a política `user_id = app.user_id OR app.system = 'on'` (em `user_tokens`, também `workspace_id = app.workspace_id` para tokens de convite).
- Toda tabela de dados tem `workspace_id NOT NULL` e **RLS ativada e forçada** (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY` + `FORCE ROW LEVEL SECURITY` + `CREATE POLICY`), na mesma migração que cria a tabela. Sem `FORCE`, o papel da aplicação, dono das tabelas, ignora as políticas. Política padrão: `workspace_id = NULLIF(current_setting('app.workspace_id', true), '')::uuid OR coalesce(current_setting('app.system', true), '') = 'on'` (ver [ADR 0001](../../docs/adr/0001-tenancy-e-rls.md)).
- Exceção: `audit_events` aceita `workspace_id` nulo (evento da instância), legível só em modo de sistema. Tabela append-only não ganha política de UPDATE.
- Nomes de restrição seguem `NAMING_CONVENTION` de `core/models.py`; o teste `test_migrations_match_orm_models` compara a migração com os modelos.
- No `downgrade`, remova as políticas que consultam outras tabelas antes de dropar as tabelas.
- Migração que muda tabela atualiza `docs/specs/modelo-de-dados.md` na mesma entrega.
- Nunca edite uma revisão já commitada em `main`; crie outra.
- Nome do arquivo: `AAAAMMDD_<rev>_<slug>.py` (definido em `alembic.ini`).

**Como testar**: de `backend/`, `uv run pytest tests/migrations` (sobe Postgres 17 + pgvector via testcontainers; exige Docker). Cada migração nova estende o teste de upgrade e downgrade. O `env.py` fica fora de `src/` e por isso fora da medição de cobertura; ele é exercitado por esses testes.

**Rodar localmente**: `uv run alembic upgrade head`, `uv run alembic downgrade -1`, `uv run alembic upgrade head --sql` (só imprime o SQL).

**Leia também**: [backend/AGENTS.md](../AGENTS.md); seções 2 (regra 7) e 9 do [AGENTS.md da raiz](../../AGENTS.md).
