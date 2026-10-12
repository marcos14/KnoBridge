# deploy/

**Função**: infraestrutura para subir o KnoBridge. Hoje, o Docker Compose do ambiente de desenvolvimento completo (Postgres + pgvector, Temporal, MinIO, Mailpit como SMTP de desenvolvimento, migrações, API, worker e painel). O Helm chart virá depois, em `deploy/helm/`.

**Entra aqui**:
- `docker-compose.yml`: o ambiente de desenvolvimento; `docker compose -f deploy/docker-compose.yml up --build`.
- `docker-compose.e2e.yml`: camada por cima do anterior para o E2E contra a stack (`frontend/e2e/stack/`): projeto próprio (`knobridge-e2e`) e ambiente não produtivo fixado, que aceita o provedor `fake`; monta `frontend/e2e/stack/fixtures/` em `/sources` no lugar de `sources/`; sobe o `webhook-sink` (sistema de chamados falso, `scripts/webhook_sink.py` montado em `python:3.12.13-alpine3.22`, porta `WEBHOOK_SINK_PORT`) e libera esse host para o webhook dos assistentes com `KNOBRIDGE_WEBHOOK_ALLOWED_HOSTS=webhook-sink`; sempre com `down -v` ao fim.
- `.env.example`: todas as variáveis que o compose interpola, com defaults de desenvolvimento.
- `postgres/`: scripts de inicialização do Postgres (bancos e papéis da aplicação e do Temporal).
- `sources/`: pasta de fontes padrão (`KNOBRIDGE_SOURCES_DIR`), montada somente leitura em `/sources` na `api` e no `worker`; no repositório só o [AGENTS.md](sources/AGENTS.md) dela, o resto é ignorado pelo Git.
- Futuramente: `helm/` (chart de Kubernetes) e scripts de infraestrutura.

**Não entra aqui**:
- `Dockerfile` das imagens próprias: ficam no pacote (`backend/Dockerfile`, `frontend/Dockerfile`, `widget/`).
- Configuração da aplicação: só por variável `KNOBRIDGE_*`, lida em `backend/src/knobridge/core/settings.py`.
- Workflows de CI (`.github/workflows/`) e scripts de checagem do repositório (`scripts/`).
- Guias de operação: `docs/guias/` (o de subida é [subir-ambiente.md](../docs/guias/subir-ambiente.md)).
- `.env` real, segredos, dumps de banco.

**Convenções locais**:
- Imagens de terceiros sempre com tag fixa (nunca `latest`); atualizar versão é PR próprio.
- Toda variável tem default de desenvolvimento no compose (`${VAR:-default}`), para o `up` funcionar sem `.env`, e aparece no `.env.example`. Credenciais de exemplo são só para desenvolvimento e estão marcadas assim.
- Portas do host publicadas em `${BIND_ADDRESS:-127.0.0.1}` e configuráveis por variável (`*_PORT`).
- Todo serviço de longa duração tem `healthcheck`; dependências usam `service_healthy` ou `service_completed_successfully` (caso do `migrate`).
- Uma imagem de backend para `migrate`, `api` e `worker`; muda só o `command`. Variáveis `KNOBRIDGE_*` comuns aos três ficam na âncora `x-backend` (inclusive `KNOBRIDGE_SECRET_KEY`, com default público de dev, e o SMTP fixo no `mailpit`).
- Fontes locais: a pasta do host `KNOBRIDGE_SOURCES_DIR` (padrão `./sources`) entra em `/sources` **somente leitura** na `api` (teste de conexão) e no `worker` (indexação), com `KNOBRIDGE_LOCAL_SOURCES_ROOT=/sources` fixo na âncora; clones de repositórios por URL https vão para o volume nomeado gravável `source-clones` (`KNOBRIDGE_GIT_WORKDIR`), só no `worker` (a `api` não clona).
- Em dev, todo e-mail vai para o `mailpit` (UI em `MAILPIT_UI_PORT`); nada é entregue a caixas reais.
- Em dev, cookies sem `Secure` (`KNOBRIDGE_COOKIE_SECURE=false`), porque o painel é HTTP puro.
- `KNOBRIDGE_WEBHOOK_ALLOWED_HOSTS` (na âncora `x-backend`) fica vazia no ambiente de desenvolvimento: o webhook de chamados dos assistentes só alcança `https` público. Só a camada de E2E a preenche, com o nome do receptor falso.
- Rede com sub-rede fixa (`COMPOSE_SUBNET`) e o `frontend` (nginx, proxy de `/v1`) em endereço fixo (`FRONTEND_IPV4`): é o único proxy cujo `X-Forwarded-For` a `api` aceita (`KNOBRIDGE_FORWARDED_ALLOW_IPS`), para a limitação de login contar o IP do cliente.
- Scripts de shell com fim de linha LF (garantido pelo `.gitattributes`).

**Como testar**:

```bash
docker compose -f deploy/docker-compose.yml config -q
docker compose -f deploy/docker-compose.yml up -d --build --wait
curl -f http://localhost:8000/v1/health/ready
curl -f http://localhost:5173/v1/health/ready
docker compose -f deploy/docker-compose.yml down -v

# E2E contra a stack (de frontend/: pnpm e2e:stack)
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.e2e.yml config -q
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.e2e.yml up -d --build --wait
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.e2e.yml down -v
```

**Leia também**: [docs/guias/subir-ambiente.md](../docs/guias/subir-ambiente.md); seções 4 e 9 do [AGENTS.md da raiz](../AGENTS.md); [backend/AGENTS.md](../backend/AGENTS.md); [frontend/AGENTS.md](../frontend/AGENTS.md).
