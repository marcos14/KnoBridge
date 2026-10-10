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

## Contrato OpenAPI

O OpenAPI da API é o contrato do frontend e fica versionado em [`docs/specs/openapi.json`](../docs/specs/openapi.json). Mudou rota ou schema, regenere e commite junto (não precisa de banco):

```sh
uv run knobridge-openapi                       # grava docs/specs/openapi.json
uv run knobridge-openapi --output /tmp/oa.json # outro destino
cd ../frontend && pnpm gen:api                 # atualiza os tipos do cliente
```

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

Isolamento entre workspaces: as tabelas com dado de workspace têm row-level security forçada ([ADR 0001](../docs/adr/0001-tenancy-e-rls.md)). O `docker run` acima conecta como superusuário, que ignora RLS: serve para desenvolver, mas não para verificar isolamento. Para isso, use o Postgres do Docker Compose (`deploy/`), em que a aplicação conecta com o papel `knobridge`, dono do banco e não superusuário.

## Worker Temporal

O worker conecta em `KNOBRIDGE_TEMPORAL_ADDRESS` (padrão `localhost:7233`), no namespace `KNOBRIDGE_TEMPORAL_NAMESPACE` (padrão `default`), e consome a task queue `KNOBRIDGE_TEMPORAL_TASK_QUEUE` (padrão `knobridge`). Para um Temporal local descartável, com a UI em `http://localhost:8233`:

```sh
temporal server start-dev            # com a CLI do Temporal instalada
uv run knobridge-worker              # logs JSON em stderr; Ctrl+C encerra
```

Teste rápido, com a CLI: `temporal workflow execute --type knobridge.health.v1 --task-queue knobridge` deve devolver `"ok"`.

## Imagem Docker

Uma única imagem serve api, worker e migrações (o comando padrão é `knobridge-api`, escutando em `0.0.0.0:8000`):

```sh
docker build -t knobridge-backend backend                    # da raiz do repositório
docker run --rm -p 8000:8000 knobridge-backend               # API
docker run --rm knobridge-backend knobridge-worker           # worker
docker run --rm knobridge-backend alembic upgrade head       # migrações
```

Passe a configuração por variáveis `KNOBRIDGE_*` (`-e` ou `--env-file`); o `.env` não entra na imagem. Com `KNOBRIDGE_ENV=production`, defina `KNOBRIDGE_SECRET_KEY` (32+ caracteres): a API não sobe com o valor padrão de desenvolvimento.

## Testar

```sh
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pytest   # inclui cobertura de linhas e branches com gate de 95%
```

Os testes de integração (`@pytest.mark.integration`) sobem Postgres 17 + pgvector via testcontainers (exigem Docker rodando) e o servidor de teste do Temporal (o SDK baixa o binário na primeira execução). Só unitários: `uv run pytest -m "not integration"` (o gate de cobertura pode falhar nesse modo).
