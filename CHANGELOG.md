# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto adota o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Added

Bootstrap do monorepo (plano [0001](docs/planos/0001-bootstrap.md)), sem funcionalidades de produto:

- Raiz: `.gitignore`, `.gitattributes`, `.editorconfig`, este changelog e `.pre-commit-config.yaml` (higiene de arquivos, ruff, prettier, gitleaks, `check_agents_md.py` e `check_plans.py`).
- `scripts/check_agents_md.py`: falha se alguma pasta não tiver `AGENTS.md`.
- `scripts/check_plans.py`: valida o frontmatter dos planos em `docs/planos/`.
- Backend (`backend/`): projeto `uv` com ruff, pyright strict e pytest com gate de 95%; settings, logging JSON e formato único de erro; `GET /v1/health/live` e `GET /v1/health/ready`; comando `knobridge-openapi` que exporta o contrato para `docs/specs/openapi.json`; engine async do banco e migrações Alembic (pgvector); worker Temporal com o workflow `knobridge.health.v1`; `Dockerfile` único para api, worker e migrações.
- Frontend (`frontend/`): Vite + React + TypeScript strict, ESLint, Prettier, Vitest com thresholds de 95, roteador, TanStack Query, i18n pt-BR, Tailwind v4 + shadcn/ui, cliente tipado gerado do OpenAPI, indicador de status da API, MSW, smoke E2E com Playwright e imagem nginx.
- Deploy (`deploy/`): Docker Compose de desenvolvimento com Postgres 17 + pgvector, Temporal (server + UI), MinIO, `migrate`, `api`, `worker` e `frontend`; guia [subir-ambiente](docs/guias/subir-ambiente.md).
- CI (`.github/workflows/ci.yml`): gates de `scripts/`, `backend/` (incluindo contrato OpenAPI em dia) e `frontend/` (incluindo `check:api`, build e Playwright), varredura de segredos com gitleaks sobre todo o histórico e validação do compose.
