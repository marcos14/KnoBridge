# deploy/sources/

**Função**: pasta de fontes padrão do Docker Compose. É montada somente leitura em `/sources` na `api` e no `worker` quando `KNOBRIDGE_SOURCES_DIR` não é definida. Fontes de pasta e repositórios Git locais cadastrados no painel apontam para caminhos abaixo de `/sources` (`KNOBRIDGE_LOCAL_SOURCES_ROOT`).

**Entra aqui**: só este arquivo no repositório. Na sua máquina, as pastas e os clones que quiser indexar (ex.: `deploy/sources/manual/` vira a fonte `/sources/manual`); o `.gitignore` da raiz ignora tudo aqui, menos este arquivo.
**Não entra aqui**: nada versionado além deste arquivo; dados de clientes nunca são commitados (regra 9 do [AGENTS.md da raiz](../../AGENTS.md)). Fixtures do E2E ficam em `frontend/e2e/stack/fixtures/` (a camada `docker-compose.e2e.yml` monta aquela pasta no lugar desta).

**Convenções locais**: cadastre uma subpasta por fonte (`/sources/<nome>`), não a raiz `/sources`, para não indexar este arquivo. Para usar outra pasta do host, defina `KNOBRIDGE_SOURCES_DIR` em `deploy/.env` (caminho absoluto, ou relativo a `deploy/`).

**Como testar**: `docker compose -f deploy/docker-compose.yml config -q`; com a stack no ar, `docker compose -f deploy/docker-compose.yml exec worker ls /sources`.

**Leia também**: [deploy/AGENTS.md](../AGENTS.md); [docs/guias/subir-ambiente.md](../../docs/guias/subir-ambiente.md).
