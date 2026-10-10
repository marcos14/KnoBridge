# backend/

**Função**: todo o código Python do KnoBridge. API REST e API compatível com OpenAI (FastAPI), workers e workflows (Temporal), conectores, engine incremental de pipelines, harness de mapeamento de código, parsing, recuperação (busca híbrida + reranker), assistentes, canais (Slack, Google Chat, widget, MCP, webhooks) e migrações. Estado: pacote `knobridge` com `core/` (settings, logging JSON, erros) e `api/` (factory FastAPI e `GET /v1/health/live`); ainda sem banco, Temporal ou domínio. Como instalar e rodar: [README.md](README.md).

**Entra aqui**: código de produção em `src/knobridge/`, testes em `tests/`, migrações em `migrations/`, `pyproject.toml`, `uv.lock`, `.env.example`, `Dockerfile`, `README.md` curto (como rodar).
**Não entra aqui**: documentação (vai para `docs/`), frontend e widget, Docker Compose e Helm (vão para `deploy/`), dados reais de clientes.

**Layout previsto** (crie cada pasta só quando for necessária, sempre com o seu `AGENTS.md`):

```
backend/
  src/knobridge/
    core/          # settings, logging, sessão de banco, segurança, erros, ids
    tenancy/       # workspace, usuários, autenticação e-mail/senha, API keys, RBAC
    sources/       # modelo de Source e registro de conectores
    connectors/    # um pacote por conector (git, files, tickets_<nome>, ...); todos implementam Connector
    harness/       # mapeamento de código por agente: inventário (camada 0), briefing, prompt + schema,
                   # runner (claude / codex), verificação de evidência, escrita de .md, priorização
    parsing/       # docling, markitdown, trafilatura, tree-sitter
    pipelines/     # modelo do grafo, catálogo de nós, compilação para workflows Temporal, lógica incremental
    workers/       # worker Temporal, activities e workflows
    storage/       # postgres/pgvector, qdrant (opcional), destino .md, minio
    retrieval/     # busca híbrida, RRF, reranker, montagem de contexto com citações e ACL
    llm/           # interfaces LLMProvider / EmbeddingProvider / Reranker e adaptadores
                   # (openai, anthropic, openrouter, openai_subscription via codex)
    assistants/    # configuração, orquestração da conversa, ferramentas (actions), memória
    channels/      # rest, openai_compat, webhooks, mcp, widget, slack, google_chat
    api/           # routers FastAPI, schemas Pydantic, dependências, versionamento /v1
    cli/           # comandos de desenvolvimento e o protótipo da Fase 0
  tests/           # espelha src/; fixtures sintéticas em tests/fixtures/; fakes em tests/fakes/
  migrations/      # alembic
```

**Convenções locais**
- Python 3.12+, `uv` para tudo (`uv sync`, `uv run ...`). No Windows, rode com `PYTHONUTF8=1`.
- `ruff` (lint + format, configurado no `pyproject.toml`) e `pyright` em modo strict. A CI falha com qualquer aviso.
- FastAPI com um router por módulo; schemas Pydantic v2 na fronteira; nunca modelo ORM em resposta. Tudo sob `/v1`. O OpenAPI gerado é o contrato do frontend e vai para `docs/specs/` a cada mudança.
- SQLAlchemy 2 tipado e async; uma sessão por requisição ou activity; `workspace_id` em toda tabela de dados; RLS ativada nas migrações; nenhuma consulta sem escopo de workspace (helper central obrigatório, lint próprio quando possível).
- Alembic: uma migração por mudança de modelo, reversível, com teste de upgrade e downgrade.
- Temporal: workflows determinísticos (sem IO), IO só em activities; activities idempotentes com política de retry explícita; nomes de workflow e activity estáveis (versione quando mudar).
- Provedores externos sempre atrás de `Protocol` em `llm/`, `connectors/`, `channels/`. Adaptador novo = implementar a interface e passar na suíte de contrato correspondente.
- Harness: subprocesso somente leitura, `--json-schema` (Claude Code) ou `--output-schema` (Codex), orçamento e timeout por job, log JSONL por execução, detecção de limite de franquia com espera, verificação mecânica de `arquivo:linhas` antes de escrever qualquer `.md`. Item sem fonte válida é rejeitado e registrado. Ver seção 7.1.1 da visão.
- Logging com `structlog` (ou equivalente) em JSON; nunca `print` fora de `cli/`.
- Settings via `pydantic-settings`, num único módulo em `core/`.

**Como testar**
```sh
uv run ruff check . && uv run ruff format --check . && uv run pyright
uv run pytest --cov=knobridge --cov-branch --cov-fail-under=95
```
- Unitários sem rede. Integração com Postgres + pgvector reais via `testcontainers` e Temporal via o ambiente de teste do SDK (`WorkflowEnvironment`). Marque com `@pytest.mark.integration`; a CI roda tudo.
- Suíte de contrato para conectores em `tests/connectors/contract/` e para canais em `tests/channels/contract/`. Fakes de LLM, embeddings e reranker em `tests/fakes/`. Executáveis fake `claude` e `codex` para o harness, que emitem o JSONL esperado.
- Teste de isolamento de workspace para cada repositório ou consulta nova.

**Leia também**: `AGENTS.md` da raiz (seções 5, 6 e 9); `docs/01-visao-do-projeto.md`, seções 6 a 8; `docs/specs/` quando existir.
