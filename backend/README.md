# KnoBridge — backend

API e serviços Python do KnoBridge. Visão geral e regras em [`AGENTS.md`](AGENTS.md) e na [documentação](../docs/).

## Instalar

Requer [uv](https://docs.astral.sh/uv/) (ele instala o Python 3.12 sozinho). No Windows, exporte `PYTHONUTF8=1`.

```sh
cd backend
uv sync
cp .env.example .env   # opcional; ajuste as variáveis KNOBRIDGE_*
```

## Rodar a API localmente

```sh
uv run knobridge-api
# ou, com reload:
uv run uvicorn knobridge.api.app:create_app --factory --reload
```

Teste rápido: `curl http://127.0.0.1:8000/v1/health/live` (processo de pé) e `curl http://127.0.0.1:8000/v1/health/ready` (banco respondendo; 503 se não). OpenAPI em `http://127.0.0.1:8000/docs`.

## Banco e migrações

A API usa Postgres 17 com pgvector, na URL de `KNOBRIDGE_DATABASE_URL` (driver `postgresql+asyncpg://`; o padrão aponta para `knobridge:knobridge@localhost:5432/knobridge`). Para um banco local descartável:

```sh
docker run -d --name knobridge-pg -p 5432:5432 \
  -e POSTGRES_USER=knobridge -e POSTGRES_PASSWORD=knobridge -e POSTGRES_DB=knobridge \
  pgvector/pgvector:pg17
```

Migrações (Alembic, de dentro de `backend/`):

```sh
uv run alembic upgrade head          # aplica todas
uv run alembic downgrade -1          # desfaz a última
uv run alembic upgrade head --sql    # só imprime o SQL, sem conectar
uv run alembic revision -m "add sources table"   # nova revisão em migrations/versions/
```

Regras das migrações em [`migrations/AGENTS.md`](migrations/AGENTS.md).

## Testar

```sh
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pytest   # inclui cobertura de linhas e branches com gate de 95%
```

Os testes de integração (`@pytest.mark.integration`) sobem Postgres 17 + pgvector via testcontainers e exigem Docker rodando. Só unitários: `uv run pytest -m "not integration"` (o gate de cobertura pode falhar nesse modo).
