# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto adota o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Added

Plataforma navegável (plano [0002](docs/planos/0002-plataforma-navegavel.md)): autenticação, multi-tenant, painel admin e chat com LLM, ainda sem RAG.

- Tenancy: usuários da instância em N workspaces, papéis owner/admin/editor/viewer, superadmin, RLS forçada por `SET LOCAL` em toda tabela de workspace ([ADR 0001](docs/adr/0001-tenancy-e-rls.md)); migrações `0002` a `0009` ([modelo de dados](docs/specs/modelo-de-dados.md)).
- Autenticação: configuração inicial do primeiro superadmin, login por e-mail e senha (argon2id) com sessão server-side e expiração deslizante, CSRF double-submit assinado, limitação de tentativas de login (respeitando `X-Forwarded-For` só de proxies confiáveis), sair de um ou de todos os dispositivos, redefinição de senha e verificação de e-mail por token de uso único ([ADR 0002](docs/adr/0002-sessao-server-side.md); [contrato](docs/specs/autenticacao.md)).
- E-mail transacional por SMTP com templates pt-BR, enviado fora da requisição; Mailpit no compose de desenvolvimento.
- Workspaces: convites por e-mail (reenviar, revogar, aceitar criando conta ou com a conta existente), gestão de membros e papéis, renomear; administração da instância (criar, renomear e suspender workspaces; suspender usuários e conceder superadmin).
- Auditoria: trilha append-only por workspace e da instância, com telas de consulta e filtros.
- LLM: credenciais de provedores (OpenAI, Anthropic, OpenRouter e `fake` para dev e testes) cifradas com AES-256-GCM ([ADR 0003](docs/adr/0003-segredos-cifrados.md)), com teste de conexão; assistentes com prompt, modelo, temperatura, idioma, tom e mensagem de "sem fonte".
- Chat: conversas com assistentes, resposta em streaming por SSE com citações ([contrato SSE](docs/specs/chat-sse.md), [comportamento](docs/specs/chat.md)), regra "sem fonte, sem LLM" com `NullRetriever` até existir indexação, feedback 👍/👎 com comentário e visão administrativa das conversas com totais.
- Painel (`frontend/`): shell com menu por papel, seletor de workspace, tema, telas públicas de setup, login, recuperação de senha, verificação de e-mail e aceite de convite, perfil e segurança, membros, configurações, provedores, assistentes, chat, conversas, auditoria e administração da instância.
- Deploy e CI: E2E Playwright da stack inteira contra o compose (`pnpm e2e:stack`, job `e2e-stack`); nginx do painel como único proxy confiável da API.
- Docs: guia de [primeiro acesso](docs/guias/primeiro-acesso.md), specs de autenticação e de chat, modelo de dados completo.

Bootstrap do monorepo (plano [0001](docs/planos/0001-bootstrap.md)), sem funcionalidades de produto:

- Raiz: `.gitignore`, `.gitattributes`, `.editorconfig`, este changelog e `.pre-commit-config.yaml` (higiene de arquivos, ruff, prettier, gitleaks, `check_agents_md.py` e `check_plans.py`).
- `scripts/check_agents_md.py`: falha se alguma pasta não tiver `AGENTS.md`.
- `scripts/check_plans.py`: valida o frontmatter dos planos em `docs/planos/`.
- Backend (`backend/`): projeto `uv` com ruff, pyright strict e pytest com gate de 95%; settings, logging JSON e formato único de erro; `GET /v1/health/live` e `GET /v1/health/ready`; comando `knobridge-openapi` que exporta o contrato para `docs/specs/openapi.json`; engine async do banco e migrações Alembic (pgvector); worker Temporal com o workflow `knobridge.health.v1`; `Dockerfile` único para api, worker e migrações.
- Frontend (`frontend/`): Vite + React + TypeScript strict, ESLint, Prettier, Vitest com thresholds de 95, roteador, TanStack Query, i18n pt-BR, Tailwind v4 + shadcn/ui, cliente tipado gerado do OpenAPI, indicador de status da API, MSW, smoke E2E com Playwright e imagem nginx.
- Deploy (`deploy/`): Docker Compose de desenvolvimento com Postgres 17 + pgvector, Temporal (server + UI), MinIO, `migrate`, `api`, `worker` e `frontend`; guia [subir-ambiente](docs/guias/subir-ambiente.md).
- CI (`.github/workflows/ci.yml`): gates de `scripts/`, `backend/` (incluindo contrato OpenAPI em dia) e `frontend/` (incluindo `check:api`, build e Playwright), varredura de segredos com gitleaks sobre todo o histórico e validação do compose.
