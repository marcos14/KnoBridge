# backend/tests/

**Função**: testes do backend, espelhando `src/knobridge/` (`tests/core/` testa `knobridge/core/`, e assim por diante).

**Entra aqui**:
- `conftest.py` com as fixtures compartilhadas: `settings` (configuração de teste), `app` e `client` (TestClient sobre `create_app`), `postgres_url` (sessão inteira: DSN asyncpg de um container `pgvector/pgvector:pg17` via testcontainers), e uma fixture automática que isola o estado global (variáveis `KNOBRIDGE_*` do host, `.env` local, cache de settings, configuração de logging).
- Uma subpasta por módulo de `src/knobridge/`, com o seu `AGENTS.md`, e `migrations/` para a cadeia do Alembic.
- Futuramente: `fixtures/` (dados sintéticos e pequenos) e `fakes/` (LLM, embeddings, reranker, conectores).

**Não entra aqui**: código de produção, dados reais de clientes, chamadas de rede reais, testes de `scripts/` (ficam em `scripts/tests/`).

**Convenções locais**:
- Nome `test_<unidade>_<comportamento>`, arrange / act / assert, um comportamento por teste.
- Sem rede, sem `sleep`, sem hora real, sem aleatoriedade sem seed. LLM e APIs externas só por fakes.
- A fixture automática muda o cwd para `tmp_path`: crie ali o `.env` quando o teste precisar de um.
- Testes que precisam de Postgres ou Temporal reais levam `@pytest.mark.integration` e rodam por padrão (exigem Docker). Postgres: use a fixture `postgres_url`; crie o engine dentro do loop do teste (`asyncio.run` ou `TestClient`) com `NullPool` ou descarte-o no fim. Quem altera o schema devolve o banco a `base`, porque o container é compartilhado.

**Como testar**: de `backend/`, `uv run pytest` (cobertura de linhas e branches com `--cov-fail-under=95`); só unitários: `uv run pytest -m "not integration"`.

**Leia também**: seção 5 do [AGENTS.md da raiz](../../AGENTS.md); [backend/AGENTS.md](../AGENTS.md).
