# backend/migrations/

**Função**: migrações do banco (Alembic, modo async com `asyncpg`). É a única forma de mudar o schema do Postgres do KnoBridge.

**Entra aqui**:
- `env.py`: ambiente do Alembic; lê a URL de `KNOBRIDGE_DATABASE_URL` via `knobridge.core.settings` (ou de `config.attributes["database_url"]`, usado pelos testes) e roda as migrações com engine async e `NullPool`.
- `script.py.mako`: modelo das revisões novas.
- `versions/`: uma revisão por arquivo, gerada por `uv run alembic revision -m "..."` (pasta gerada, sem `AGENTS.md`). Hoje: `0001` habilita a extensão `vector` (pgvector).

**Não entra aqui**: modelos ORM (vão para o módulo de domínio em `src/knobridge/`), dados de seed ou de clientes, SQL solto fora de revisão, configuração (fica em `core/settings.py`; `alembic.ini` fica em `backend/`).

**Convenções locais**:
- Uma migração por mudança de modelo, na mesma entrega do código que a usa.
- Toda migração é reversível: `downgrade()` desfaz exatamente o `upgrade()`. Nada de `pass` no downgrade.
- Toda tabela de dados tem `workspace_id NOT NULL` e **RLS ativada** com política por workspace (`ALTER TABLE ... ENABLE ROW LEVEL SECURITY` + `CREATE POLICY`), na mesma migração que cria a tabela.
- Nunca edite uma revisão já commitada em `main`; crie outra.
- Nome do arquivo: `AAAAMMDD_<rev>_<slug>.py` (definido em `alembic.ini`).

**Como testar**: de `backend/`, `uv run pytest tests/migrations` (sobe Postgres 17 + pgvector via testcontainers; exige Docker). Cada migração nova estende o teste de upgrade e downgrade. O `env.py` fica fora de `src/` e por isso fora da medição de cobertura; ele é exercitado por esses testes.

**Rodar localmente**: `uv run alembic upgrade head`, `uv run alembic downgrade -1`, `uv run alembic upgrade head --sql` (só imprime o SQL).

**Leia também**: [backend/AGENTS.md](../AGENTS.md); seções 2 (regra 7) e 9 do [AGENTS.md da raiz](../../AGENTS.md).
