# backend/tests/migrations/

**Função**: testes da cadeia de migrações Alembic de `backend/migrations/`.

**Entra aqui**: `test_migrations.py`, que roda `alembic upgrade` e `downgrade` programaticamente (`alembic.command`) contra o Postgres 17 + pgvector da fixture `postgres_url`, e confere o efeito no catálogo do banco (`pg_extension`, `pg_class.relrowsecurity`/`relforcerowsecurity`, `pg_policies`), além de `test_migrations_match_orm_models`, que compara o schema em `head` com `Base.metadata` (autogenerate sem diferenças).
**Não entra aqui**: testes de consultas e repositórios de domínio (ficam na pasta do módulo), testes de `core/db.py` (`tests/core/test_db.py`).

**Convenções locais**:
- Cada migração nova estende estes testes (a `0011`, por exemplo, em `test_migration_upgrade_downgrade_run_items`): depois do `upgrade` o objeto existe (com RLS, se for tabela de dados) e depois do `downgrade` não existe mais.
- O teste sempre deixa o banco em `base` ao terminar: o container é compartilhado pela sessão de testes.
- Use `config.attributes["configure_logger"] = False` para o `env.py` não reconfigurar o logging dos testes, e `config.attributes["database_url"]` para apontar para o container.
- Testes que tocam o banco levam `@pytest.mark.integration` (exigem Docker).

**Como testar**: de `backend/`, `uv run pytest tests/migrations`.

**Leia também**: [migrations/AGENTS.md](../../migrations/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
