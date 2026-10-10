---
id: 0001
titulo: Bootstrap da arquitetura base (sem features)
slug: bootstrap
solicitado_por: usuario
criado_em: 2026-10-10
atualizado_em: 2026-10-10
status: em_execucao
aprovado_em: 2026-10-10
aprovado_por: usuario
concluido_em: null
branch: plano/0001-bootstrap
fases:
  - id: F1
    titulo: Fundação do repositório
    status: pendente
    subfases:
      - id: F1.1
        titulo: Arquivos da raiz e scripts de checagem
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
  - id: F2
    titulo: Backend base
    status: pendente
    subfases:
      - id: F2.1
        titulo: Pacote Python, core e API com health
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F2.2
        titulo: Banco async, Alembic e readiness
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F2.3
        titulo: Worker Temporal e imagem Docker do backend
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
  - id: F3
    titulo: Frontend base
    status: pendente
    subfases:
      - id: F3.1
        titulo: App Vite com providers, i18n e gates
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F3.2
        titulo: shadcn/ui, cliente gerado do OpenAPI, MSW, Playwright e Dockerfile
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
  - id: F4
    titulo: Infra local e CI
    status: pendente
    subfases:
      - id: F4.1
        titulo: Docker Compose e guia de subida
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F4.2
        titulo: CI no GitHub Actions, pre-commit e docs finais
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
decisoes:
  - id: D1
    data: 2026-10-10
    por: usuario
    decisao: Backend base = infra transversal (settings, logging JSON, sessão async, formato único de erro, /v1/health, Alembic sem tabelas, worker Temporal com workflow de health). Nenhum modelo de domínio.
    motivo: Pedido é só arquitetura base, sem features.
    alternativas: Incluir Workspace com RLS já agora; ou só o mínimo da seção 12 sem banco e sem Temporal.
    adr: null
  - id: D2
    data: 2026-10-10
    por: usuario
    decisao: Pacotes de domínio (tenancy, connectors, pipelines, retrieval, llm, channels...) não são criados agora; nascem quando forem usados.
    motivo: Regra do backend/AGENTS.md ("crie cada pasta só quando for necessária").
    alternativas: Criar todos vazios; criar com Protocols e fakes.
    adr: null
  - id: D3
    data: 2026-10-10
    por: usuario
    decisao: Frontend com roteador, TanStack Query, i18n pt-BR, shadcn/ui, MSW e Playwright (1 smoke). Widget fica para outro plano.
    motivo: Deixar os padrões do frontend/AGENTS.md prontos antes da primeira tela real.
    alternativas: Incluir widget; frontend mínimo.
    adr: null
  - id: D4
    data: 2026-10-10
    por: usuario
    decisao: Branch plano/0001-bootstrap, CI no GitHub Actions, pre-commit com ruff, prettier e gitleaks.
    motivo: Padrão do AGENTS.md (seções 3.4 e 8).
    alternativas: Commitar em Primeira_verao; outra plataforma de CI.
    adr: null
  - id: D5
    data: 2026-10-10
    por: agente
    decisao: scripts/ é um projeto Python próprio (pyproject com uv, pytest, gate 95%), separado do backend.
    motivo: Regra 2 exige gate por pacote; os scripts não devem depender do pacote knobridge.
    alternativas: Colocar os scripts dentro do backend; scripts sem testes.
    adr: null
  - id: D6
    data: 2026-10-10
    por: agente
    decisao: "Ferramentas de apoio: structlog (logs JSON), pydantic-settings, asyncpg, openapi-typescript + openapi-fetch (cliente gerado), react-router, i18next, Temporal via imagem temporalio/auto-setup usando o mesmo Postgres em bancos separados."
    motivo: Mais simples que cumprem as convenções já escritas nos AGENTS.md; nenhuma muda decisão da seção 9 da visão.
    alternativas: orval (cliente com hooks gerados), Temporal com banco próprio, loguru.
    adr: null
  - id: D7
    data: 2026-10-10
    por: agente
    decisao: A primeira migração Alembic só habilita a extensão vector; nenhuma tabela.
    motivo: Prova que a cadeia de migração funciona (upgrade e downgrade testados) sem antecipar modelo de domínio.
    alternativas: Migração vazia; já criar workspace.
    adr: null
pendencias_usuario: []
---

# Plano 0001 — Bootstrap da arquitetura base (sem features)

## 1. Pedido original

> "Com base no docs\01-visao-do-projeto.md, crie a estrutura base do projeto, sem features, apenas arquitetura base"

## 2. Entendimento (perguntas e respostas)

| # | Pergunta | Resposta | Data |
|---|---|---|---|
| 1 | Até onde vai a arquitetura base no backend? | Infra transversal: core (settings, logging JSON, sessão async, erro único), `/v1/health`, Alembic sem tabelas, worker Temporal com workflow de health. Sem modelo de domínio. | 2026-10-10 |
| 2 | Criar já os módulos previstos (tenancy, connectors, pipelines...)? | Não; só quando forem usados. | 2026-10-10 |
| 3 | O que entra no frontend e no widget? | Frontend com providers (roteador, TanStack Query, i18n, shadcn/ui, MSW, Playwright smoke). Widget fica para depois. | 2026-10-10 |
| 4 | Onde commitar e qual CI? | Branch `plano/0001-bootstrap`, GitHub Actions, pre-commit com ruff, prettier e gitleaks. | 2026-10-10 |

**Resumo**: este plano é o bootstrap da seção 12 do `AGENTS.md` da raiz. Monta o esqueleto do monorepo com todos os gates (lint, format, typecheck, testes, cobertura ≥ 95%, checagem de `AGENTS.md`, validação de planos, varredura de segredos) e a infra local (`docker compose up`), sem nenhuma funcionalidade de produto.

**Fora do escopo**: modelos de domínio (Workspace, Source etc.), autenticação, RLS de tabelas, conectores, pipelines, LLM, canais, widget, Helm, Qdrant, Redis.

## 3. Critérios de aceite

- [ ] `uv run pytest` no backend e em `scripts/` passa com cobertura ≥ 95% (linhas e branches); ruff e pyright strict limpos.
- [ ] `pnpm lint && pnpm typecheck && pnpm test -- --coverage` no frontend passa com thresholds 95; `pnpm build` gera o bundle.
- [ ] `docker compose -f deploy/docker-compose.yml up` sobe Postgres+pgvector, Temporal, Temporal UI, MinIO, api, worker e frontend; `GET /v1/health/ready` responde 200 com banco ok; a UI mostra o status da API.
- [ ] `scripts/check_agents_md.py` e `scripts/check_plans.py` passam no repositório e falham nos casos de teste negativos.
- [ ] `.github/workflows/ci.yml` roda todos os gates; `pre-commit run --all-files` limpo.
- [ ] Toda pasta nova tem `AGENTS.md`; tabela da seção 4 e seção 12 do `AGENTS.md` da raiz atualizadas.

## 4. Fases e subfases

### F1 — Fundação do repositório

Arquivos comuns da raiz e as checagens de repositório que a CI usará.

#### F1.1 — Arquivos da raiz e scripts de checagem

- **Objetivo**: criar a base comum e os dois scripts de checagem com testes.
- **Entregáveis**: `.gitignore` (Python, Node, `.env`, caches, coberturas), `.gitattributes` (LF), `.editorconfig`, `CHANGELOG.md` (Keep a Changelog, seção Unreleased); `scripts/AGENTS.md`, `scripts/pyproject.toml` (uv, ruff, pyright strict, pytest com `--cov-fail-under=95`), `scripts/check_agents_md.py` (percorre o repo, ignora pastas geradas/vendorizadas da seção 4 e pastas só de fixtures, lista pastas sem `AGENTS.md`, exit 1), `scripts/check_plans.py` (valida frontmatter YAML de `docs/planos/NNNN-*.md` contra os campos e status do modelo; ignora `0000-modelo.md` no requisito de execução), `scripts/tests/` com fixtures sintéticas em `tmp_path`.
- **Contexto necessário**: `AGENTS.md` da raiz (seções 4, 5, 6.1, 13); `docs/planos/AGENTS.md`; `docs/planos/0000-modelo.md`; esta subfase.
- **Critérios de aceite**: testes `test_check_agents_md_reports_missing_folder`, `..._ignores_generated_dirs`, `..._passes_when_all_present`, `test_check_plans_rejects_invalid_status`, `..._rejects_missing_field`, `..._accepts_valid_plan`; os dois scripts passam no repositório real; cobertura ≥ 95%.
- **Depende de**: nenhuma.
- **Tamanho**: médio.

### F2 — Backend base

Pacote `knobridge` com a infra transversal e nenhum domínio.

#### F2.1 — Pacote Python, core e API com health

- **Objetivo**: projeto Python pronto com gates e a aplicação FastAPI mínima.
- **Entregáveis**: `backend/pyproject.toml` (Python 3.12, deps fixadas por `uv.lock`, ruff, pyright strict, pytest + cov 95, marker `integration`), `backend/README.md`, `backend/.env.example`; `src/knobridge/__init__.py`; `core/settings.py` (pydantic-settings, prefixo `KNOBRIDGE_`), `core/logging.py` (structlog JSON, contexto `workspace_id`/`run_id`/`conversation_id`), `core/errors.py` (exceção base de domínio + handler no formato `{"error": {"code","message","details"}}`); `api/app.py` (factory `create_app`), `api/health.py` (`GET /v1/health/live`); `tests/` espelhando `src/`; `AGENTS.md` em `src/knobridge/`, `core/`, `api/`, `tests/`.
- **Contexto necessário**: `AGENTS.md` da raiz (seções 2, 5, 6); `backend/AGENTS.md`; esta subfase.
- **Critérios de aceite**: `test_settings_reads_env_prefix`, `test_logging_emits_json_with_context`, `test_error_handler_returns_standard_shape`, `test_unhandled_error_returns_500_standard_shape`, `test_health_live_returns_ok`; ruff, format, pyright limpos; cobertura ≥ 95%.
- **Depende de**: F1.1.
- **Tamanho**: médio.

#### F2.2 — Banco async, Alembic e readiness

- **Objetivo**: conexão async com Postgres e cadeia de migrações testada.
- **Entregáveis**: `core/db.py` (engine e `async_sessionmaker` a partir de settings, dependência FastAPI de sessão por requisição); `backend/migrations/` (Alembic async, `env.py`, `AGENTS.md`), migração inicial `CREATE EXTENSION IF NOT EXISTS vector` (D7); `GET /v1/health/ready` (checa `SELECT 1`; 503 no formato de erro se falhar); testes de integração com testcontainers `pgvector/pgvector:pg17`.
- **Contexto necessário**: `backend/AGENTS.md`; `AGENTS.md` da raiz (seção 5); arquivos `core/settings.py`, `core/errors.py`, `api/app.py`, `api/health.py` e `tests/conftest.py` da F2.1; esta subfase.
- **Critérios de aceite**: `test_health_ready_returns_ok_with_database` (integração), `test_health_ready_returns_503_when_database_down` (unitário com engine fake), `test_migrations_upgrade_and_downgrade` (integração, confere a extensão); cobertura ≥ 95%.
- **Depende de**: F2.1.
- **Tamanho**: médio.

#### F2.3 — Worker Temporal e imagem Docker do backend

- **Objetivo**: worker Temporal que sobe e executa um workflow de health; imagem única para api e worker.
- **Entregáveis**: `workers/` (`AGENTS.md`, `worker.py` com função de montagem do `Worker` a partir de settings, `health.py` com `HealthWorkflow` + activity `ping`, retry explícito, nomes estáveis), entry points `knobridge-api` e `knobridge-worker` no `pyproject.toml`, `backend/Dockerfile` (multi-stage com uv, usuário não root), `backend/.dockerignore`.
- **Contexto necessário**: `backend/AGENTS.md` (convenções Temporal); `core/settings.py`, `core/logging.py` e `pyproject.toml` da F2.1; esta subfase.
- **Critérios de aceite**: `test_health_workflow_runs_ping_activity` (via `WorkflowEnvironment` do SDK), `test_build_worker_registers_workflows_and_activities`, teste dos entry points com dependências injetadas; `docker build backend` conclui; cobertura ≥ 95%.
- **Depende de**: F2.1.
- **Tamanho**: médio.

### F3 — Frontend base

Painel React com os padrões do `frontend/AGENTS.md` prontos, sem telas de produto.

#### F3.1 — App Vite com providers, i18n e gates

- **Objetivo**: aplicação Vite + React + TS strict com roteador, TanStack Query, i18n pt-BR e layout vazio.
- **Entregáveis**: `frontend/package.json`, `pnpm-lock.yaml`, `tsconfig*.json`, `vite.config.ts`, `vitest.config.ts` (thresholds 95 em lines/branches/functions/statements), ESLint (flat config) + Prettier, `src/main.tsx`, `src/app/` (providers, router, layout com título e navegação vazia), `src/i18n/` (i18next, `pt-BR.json`), `src/test/setup.ts`; `README.md`; `AGENTS.md` em `src/`, `src/app/`, `src/i18n/`, `src/test/`.
- **Contexto necessário**: `AGENTS.md` da raiz (seções 5, 6.1, 6.3); `frontend/AGENTS.md`; esta subfase.
- **Critérios de aceite**: testes do layout (renderiza título traduzido, landmark `main`), do roteador (rota desconhecida mostra página "não encontrada") e do i18n (chave ausente não quebra); `pnpm lint`, `pnpm typecheck`, `pnpm test -- --coverage`, `pnpm build` passam.
- **Depende de**: F1.1.
- **Tamanho**: médio.

#### F3.2 — shadcn/ui, cliente gerado do OpenAPI, MSW, Playwright e Dockerfile

- **Objetivo**: ligar o frontend ao contrato do backend e fechar o ferramental de testes.
- **Entregáveis**: comando no backend que exporta o OpenAPI (`knobridge-openapi` → `docs/specs/openapi.json`) com teste; `docs/specs/AGENTS.md`; `frontend/src/lib/api/` (tipos gerados por openapi-typescript, cliente openapi-fetch, hook `useApiHealth` com TanStack Query), indicador de status da API no layout; `components/ui/` com shadcn inicializado (só os componentes usados); `src/test/` com handlers MSW; `e2e/` com Playwright e 1 smoke (abre o app, vê o título); `frontend/Dockerfile` (build + nginx) e `.dockerignore`; `AGENTS.md` em `lib/`, `lib/api/`, `components/`, `e2e/`.
- **Contexto necessário**: `frontend/AGENTS.md`; `backend/AGENTS.md` (seção da API); `backend/src/knobridge/api/app.py`; arquivos `src/app/` e `src/test/setup.ts` da F3.1; esta subfase.
- **Critérios de aceite**: `test_export_openapi_writes_file` (backend); testes do hook com MSW para sucesso e falha; teste do indicador nos dois estados; `pnpm e2e` passa localmente; gates do frontend e do backend no verde.
- **Depende de**: F2.2, F3.1.
- **Tamanho**: médio.

### F4 — Infra local e CI

#### F4.1 — Docker Compose e guia de subida

- **Objetivo**: `docker compose up` sobe o ambiente completo.
- **Entregáveis**: `deploy/AGENTS.md`, `deploy/docker-compose.yml` (postgres `pgvector/pgvector:pg17` com healthcheck, `temporalio/auto-setup` + `temporalio/ui`, MinIO, job de migração, `api`, `worker`, `frontend`), `deploy/.env.example`, script de init do Postgres para os bancos do Temporal (se necessário), `docs/guias/AGENTS.md`, `docs/guias/subir-ambiente.md`.
- **Contexto necessário**: `AGENTS.md` da raiz (seções 4, 9); `backend/Dockerfile`, `frontend/Dockerfile`, `backend/.env.example`; esta subfase.
- **Critérios de aceite**: `docker compose config` válido; subida local com todos os serviços saudáveis e `/v1/health/ready` = 200 (verificado pelo orquestrador); guia descreve o passo a passo e as portas.
- **Depende de**: F2.3, F3.2.
- **Tamanho**: pequeno.

#### F4.2 — CI no GitHub Actions, pre-commit e docs finais

- **Objetivo**: todos os gates automáticos e a documentação de raiz atualizada.
- **Entregáveis**: `.github/AGENTS.md`, `.github/workflows/AGENTS.md`, `.github/workflows/ci.yml` (jobs: scripts, backend lint/type/test com cobertura e integração via Docker do runner, frontend lint/type/test/build/e2e, check AGENTS.md, check planos, gitleaks); `.pre-commit-config.yaml` (ruff, prettier, gitleaks, checagens de AGENTS.md e planos); `README.md` da raiz (o que é, como subir, onde ler mais); `AGENTS.md` da raiz (tabela da seção 4, seção 1 de status e seção 12); `CHANGELOG.md`.
- **Contexto necessário**: `AGENTS.md` da raiz inteiro; comandos de teste em `backend/AGENTS.md`, `frontend/AGENTS.md`, `scripts/AGENTS.md`; esta subfase.
- **Critérios de aceite**: YAML da CI válido (actionlint se disponível); `pre-commit run --all-files` limpo; README com comandos que funcionam.
- **Depende de**: F1.1, F2.3, F3.2, F4.1.
- **Tamanho**: pequeno.

## 5. Decisões

Ver `decisoes[]` no frontmatter. Nenhuma muda a seção 9 da visão; por isso não há ADR neste plano.

## 6. Pendências do usuário

Nenhuma no momento. A CI só roda de fato quando o repositório estiver no GitHub; até lá é validada localmente.

## 7. Registro de andamento

- 2026-10-10 — entendimento concluído (4 perguntas respondidas); plano criado; aguardando aprovação.
- 2026-10-10 — plano aprovado pelo usuário; início da execução.

## 8. Encerramento

A preencher ao concluir.
