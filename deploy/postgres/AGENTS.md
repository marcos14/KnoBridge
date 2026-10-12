# deploy/postgres/

**Função**: inicialização do Postgres do Docker Compose. Os scripts daqui são montados em `/docker-entrypoint-initdb.d/` e rodam uma única vez, como superusuário, quando o volume do banco está vazio.

**Entra aqui**:
- `init-databases.sh`: cria o papel e o banco da aplicação (`KNOBRIDGE_DB_*`), cria a extensão `vector` nele, e cria o papel `TEMPORAL_DB_*` dono dos bancos `temporal` e `temporal_visibility` (o Temporal só aplica os schemas, com `SKIP_DB_CREATE=true`).

**Não entra aqui**:
- Tabelas e schema da aplicação: são migrações Alembic em `backend/migrations/`.
- Dados de exemplo ou dumps (nada de dado real; fixtures sintéticas ficam nos `tests/fixtures/` dos pacotes).
- Configuração de produção (virá no Helm chart, `deploy/helm/`).

**Convenções locais**:
- Shell POSIX (`#!/bin/sh`, `set -eu`), fim de linha LF, nomes e senhas só por variável de ambiente.
- SQL via `psql -v ON_ERROR_STOP=1` com variáveis do psql (`:"ident"`, `:'literal'`) para citar nomes e senhas.
- Como só roda com volume vazio, mudança aqui exige `docker compose down -v` para valer.

**Como testar**: subir o compose do zero (`down -v` e depois `up -d --wait`) e conferir que `migrate` sai com 0, `temporal` fica saudável e `curl -f http://localhost:8000/v1/health/ready` responde 200.

**Leia também**: [deploy/AGENTS.md](../AGENTS.md); [docs/guias/subir-ambiente.md](../../docs/guias/subir-ambiente.md).
