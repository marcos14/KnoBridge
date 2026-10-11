# .github/workflows/

**Função**: workflows do GitHub Actions. `ci.yml` roda todos os gates obrigatórios para merge (seção 8 do [AGENTS.md da raiz](../../AGENTS.md)) em `pull_request` e em `push` na `main`.

**Entra aqui**:
- `ci.yml`, com um job por área:
  - `repo-checks`: lint, format, typecheck e testes de `scripts/`, `check_agents_md.py` e `check_plans.py`.
  - `backend`: ruff, pyright, pytest com gate de 95% (integração com Postgres via testcontainers no Docker do runner) e checagem de que `docs/specs/openapi.json` está em dia.
  - `frontend`: lint, format, typecheck, Vitest com cobertura, build, `check:api` e Playwright (relatório enviado como artefato quando falha).
  - `secrets`: gitleaks sobre todo o histórico.
  - `compose`: `docker compose ... config -q` do compose e da camada de E2E (só valida).
  - `e2e-stack`: instala o runner (`uv sync --frozen` em `runner/`, que o `runner.spec.ts` sobe no host), sobe `deploy/docker-compose.yml` + `deploy/docker-compose.e2e.yml` do zero, roda `pnpm e2e:stack` em `frontend/`, publica o relatório do Playwright e os logs dos contêineres quando falha e sempre termina com `down -v`.
- Workflows futuros (release, publicação de imagens), um arquivo por propósito.

**Não entra aqui**: lógica de checagem com mais de algumas linhas de shell (vira script testado em `scripts/`); segredos; workflows que escrevem no repositório sem decisão registrada.

**Convenções locais**:
- `permissions: contents: read` no topo; cada job pede só o que precisa a mais.
- `concurrency` cancela execuções antigas do mesmo ref.
- Actions fixadas por versão major (`@v7`) ou, quando a action não publica tag major, por SHA com a versão em comentário. Binários baixados têm versão fixa e checksum conferido.
- `actions/checkout` com `persist-credentials: false`.
- Os comandos repetem os do "Como testar" de cada pacote: mudou lá, muda aqui na mesma entrega.
- Runner com versão fixa (`ubuntu-24.04`) e `timeout-minutes` em todo job.

**Como testar**: `docker run --rm -v "$PWD:/repo" -w /repo rhysd/actionlint:1.7.12` na raiz do repositório (sem erros).

**Leia também**: [.github/AGENTS.md](../AGENTS.md); [scripts/AGENTS.md](../../scripts/AGENTS.md); [backend/AGENTS.md](../../backend/AGENTS.md); [frontend/AGENTS.md](../../frontend/AGENTS.md); [deploy/AGENTS.md](../../deploy/AGENTS.md).
