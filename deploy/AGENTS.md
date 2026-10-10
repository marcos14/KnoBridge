# deploy/

**Função**: infraestrutura para subir o KnoBridge. Hoje, o Docker Compose do ambiente de desenvolvimento completo (Postgres + pgvector, Temporal, MinIO, Mailpit como SMTP de desenvolvimento, migrações, API, worker e painel). O Helm chart virá depois, em `deploy/helm/`.

**Entra aqui**:
- `docker-compose.yml`: o ambiente de desenvolvimento; `docker compose -f deploy/docker-compose.yml up --build`.
- `.env.example`: todas as variáveis que o compose interpola, com defaults de desenvolvimento.
- `postgres/`: scripts de inicialização do Postgres (bancos e papéis da aplicação e do Temporal).
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
- Em dev, todo e-mail vai para o `mailpit` (UI em `MAILPIT_UI_PORT`); nada é entregue a caixas reais.
- Scripts de shell com fim de linha LF (garantido pelo `.gitattributes`).

**Como testar**:

```bash
docker compose -f deploy/docker-compose.yml config -q
docker compose -f deploy/docker-compose.yml up -d --build --wait
curl -f http://localhost:8000/v1/health/ready
curl -f http://localhost:5173/v1/health/ready
docker compose -f deploy/docker-compose.yml down -v
```

**Leia também**: [docs/guias/subir-ambiente.md](../docs/guias/subir-ambiente.md); seções 4 e 9 do [AGENTS.md da raiz](../AGENTS.md); [backend/AGENTS.md](../backend/AGENTS.md); [frontend/AGENTS.md](../frontend/AGENTS.md).
