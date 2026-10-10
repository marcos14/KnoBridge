# Subir o ambiente de desenvolvimento

> Rascunho v0.1 · 2026-10-10 · Em uso

Como subir o KnoBridge completo na sua máquina com Docker Compose: banco, Temporal, armazenamento de objetos, migrações, API, worker e painel. Ainda não há funcionalidades de produto; o objetivo é ter a base rodando e saudável.

## Pré-requisitos

- Docker com Compose v2 (`docker compose version` deve responder 2.x). No Windows e no macOS, Docker Desktop com engine Linux.
- Cerca de 4 GB de RAM livres para os contêineres e 3 GB de disco para as imagens.
- As portas da tabela abaixo livres no `127.0.0.1` (ou troque-as no `deploy/.env`).

Não é preciso ter Python, `uv`, Node nem `pnpm` instalados para este guia: as imagens do backend e do frontend são construídas dentro do Docker.

## Passos

Todos os comandos rodam a partir da raiz do repositório.

1. Crie o arquivo de variáveis (opcional: sem ele, valem os mesmos defaults de desenvolvimento):

   ```bash
   cp deploy/.env.example deploy/.env
   ```

   As credenciais do exemplo são **só para desenvolvimento**. O `deploy/.env` é ignorado pelo git; nunca o commite.

2. Construa as imagens e suba tudo:

   ```bash
   docker compose -f deploy/docker-compose.yml up --build
   ```

   Para rodar em segundo plano e só devolver o terminal quando todos os serviços estiverem saudáveis:

   ```bash
   docker compose -f deploy/docker-compose.yml up -d --build --wait
   ```

   Ordem de subida: `postgres` saudável → `temporal` e `migrate` → `api` (depois que `migrate` termina com sucesso) e `worker` (depois que `migrate` termina e o Temporal fica saudável) → `frontend` (depois que a `api` fica saudável).

## Serviços e portas

| Serviço | Imagem | Porta no host | Variável da porta | Para quê |
|---|---|---|---|---|
| `postgres` | `pgvector/pgvector:pg17` | 5432 | `POSTGRES_PORT` | Banco da aplicação (`knobridge`) e do Temporal (`temporal`, `temporal_visibility`) |
| `temporal` | `temporalio/auto-setup:1.29.7` | 7233 | `TEMPORAL_PORT` | Servidor Temporal (gRPC) |
| `temporal-ui` | `temporalio/ui:2.55.0` | 8080 | `TEMPORAL_UI_PORT` | Interface web do Temporal |
| `minio` | `pgsty/minio:RELEASE.2026-08-04T00-00-00Z` | 9000 (API S3), 9001 (console) | `MINIO_API_PORT`, `MINIO_CONSOLE_PORT` | Armazenamento de objetos compatível com S3 |
| `migrate` | backend (local) | — | — | Roda `alembic upgrade head` uma vez e termina |
| `api` | backend (local) | 8000 | `API_PORT` | API REST (`knobridge-api`) |
| `worker` | backend (local) | — | — | Worker Temporal (`knobridge-worker`), fila `knobridge` |
| `frontend` | frontend (local) | 5173 | `FRONTEND_PORT` | Painel admin (nginx), com proxy de `/v1/` para a `api` |

Todas as portas são publicadas só em `127.0.0.1` (variável `BIND_ADDRESS`).

## Como verificar

1. Estado dos serviços: todos `running (healthy)`, exceto `migrate`, que deve aparecer `exited (0)`.

   ```bash
   docker compose -f deploy/docker-compose.yml ps -a
   ```

2. API pronta (inclui o teste de conexão com o banco):

   ```bash
   curl http://localhost:8000/v1/health/ready
   # {"status":"ok","checks":{"database":"ok"}}
   ```

3. Painel: abra <http://localhost:5173>. O indicador no topo deve mostrar **"API: disponível"**. A mesma checagem pelo proxy do painel:

   ```bash
   curl http://localhost:5173/v1/health/ready
   ```

4. Worker conectado ao Temporal: o log deve ter o evento `worker_started`, e a fila `knobridge` deve listar pollers.

   ```bash
   docker compose -f deploy/docker-compose.yml logs worker
   docker compose -f deploy/docker-compose.yml exec temporal \
     temporal task-queue describe --address temporal:7233 --task-queue knobridge
   ```

5. Temporal UI: abra <http://localhost:8080> e confira o namespace `default`.

6. Console do MinIO: abra <http://localhost:9001> e entre com `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` (padrão de dev: `knobridge` / `knobridge-dev`).

## Derrubar e limpar

```bash
# Para e remove os contêineres, mantendo os dados (volumes).
docker compose -f deploy/docker-compose.yml down

# Remove também os volumes: banco e MinIO voltam a ficar vazios.
docker compose -f deploy/docker-compose.yml down -v
```

Depois de mudar código do backend ou do frontend, rode de novo com `--build` para reconstruir as imagens.

## Problemas comuns

- **Porta já em uso** (`bind: address already in use` ou `ports are not available`): troque a porta no `deploy/.env` (ex.: `MINIO_API_PORT=9010` e `MINIO_CONSOLE_PORT=9011`) e suba de novo. Para descobrir quem ocupa a porta: `netstat -ano | findstr :9000` (Windows) ou `lsof -i :9000` (Linux/macOS).
- **Mudei usuário, senha ou nome de banco no `.env` e nada mudou**: o script `deploy/postgres/init-databases.sh` só roda com o volume vazio. Rode `down -v` e suba de novo (apaga os dados locais).
- **`migrate` saiu com erro**: veja `docker compose -f deploy/docker-compose.yml logs migrate`. Em geral é banco inacessível ou credencial divergente entre `KNOBRIDGE_DB_*` e um volume antigo; `down -v` resolve em dev.
- **`temporal` demora a ficar saudável**: na primeira subida ele aplica os schemas e registra o namespace; o healthcheck só passa quando o namespace existe. Acompanhe com `docker compose -f deploy/docker-compose.yml logs -f temporal`.
- **Painel mostra "API: indisponível"**: confira se a `api` está `healthy` e se `curl http://localhost:5173/v1/health/ready` responde 200. Se responder 502, o nginx não alcança a `api`.
- **`init-databases.sh` falha com `$'\r': command not found`**: o arquivo foi salvo com fim de linha CRLF. O `.gitattributes` força LF; rode `git add --renormalize .` ou salve o arquivo com LF e faça `down -v`.

## Referências

- Imagem do Postgres com pgvector: <https://hub.docker.com/r/pgvector/pgvector>
- Temporal auto-setup e variáveis (`DB`, `POSTGRES_SEEDS`, `SKIP_DB_CREATE`): <https://hub.docker.com/r/temporalio/auto-setup>
- Temporal UI: <https://hub.docker.com/r/temporalio/ui>
- Build comunitária do MinIO usada aqui (as imagens oficiais `minio/minio` deixaram de ser publicadas publicamente): <https://hub.docker.com/r/pgsty/minio>
- Docker Compose (`depends_on`, `healthcheck`, `--wait`): <https://docs.docker.com/reference/compose-file/services/>
