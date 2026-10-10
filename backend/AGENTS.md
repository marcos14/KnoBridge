# backend/

**Função**: todo o código Python do KnoBridge. API REST e API compatível com OpenAI (FastAPI), workers e workflows (Temporal), conectores, engine incremental de pipelines, harness de mapeamento de código, parsing, recuperação (busca híbrida + reranker), assistentes, canais (Slack, Google Chat, widget, MCP, webhooks) e migrações. Estado: pacote `knobridge` com `core/` (settings, logging JSON, erros, base ORM, engine e sessão async do banco com escopo de RLS: `scoped_session`/`system_session`; cifra AES-GCM de segredos em repouso com chave derivada por HKDF, [ADR 0003](../docs/adr/0003-segredos-cifrados.md)) e `api/` (factory FastAPI, `GET /v1/health/live` e `/v1/health/ready`, setup inicial, login/logout, `GET /v1/me`, recuperação de senha, verificação de e-mail, perfil, troca de senha e sessões do próprio usuário, auditoria por workspace, convites (gestão por owner/admin, pré-visualização e aceite por token), membros (listar, mudar papel, remover) e renomear workspace, credenciais de provedor de LLM por workspace (`/v1/workspaces/{id}/providers`, chave nunca devolvida, e teste de conexão em `.../providers/{pid}/test`), assistentes por workspace (`/v1/workspaces/{id}/assistants`; viewer só vê os ativos), conversas com os assistentes (`/v1/workspaces/{id}/conversations`: criar, listar as minhas, ler, excluir, feedback e a pergunta com resposta em SSE, [docs/specs/chat-sse.md](../docs/specs/chat-sse.md)), visão de owner/admin das conversas do workspace (`/v1/workspaces/{id}/admin/conversations`: lista com filtros e contagens, detalhe com o feedback de todos e totais do período em `.../stats`), administração da instância pelo superadmin em `/v1/admin` (workspaces, usuários, auditoria da instância), dependências `current_user`/`optional_current_user`/`require_superadmin`/`superadmin_context`/`workspace_context`/`require_role`, comando `knobridge-openapi` que exporta o contrato para `docs/specs/openapi.json`); `workers/` (worker Temporal `knobridge-worker` com o workflow de saúde `knobridge.health.v1`); `tenancy/` (modelos `User`, `Workspace`, `Membership`, `Invitation`, serviço de autenticação, autosserviço da conta, setup inicial com advisory lock, convites e aceite, gestão de membros, serviços do superadmin, consultas de membership e RBAC); `security/` (senha argon2id, tokens opacos de uso único, sessões server-side com expiração deslizante, CSRF double-submit e limitação de login em tabela, sem rotas; [ADR 0002](../docs/adr/0002-sessao-server-side.md)); `audit/` (trilha de auditoria: modelo `AuditEvent` com RLS forçada e append-only, catálogo estável de ações, `AuditService.record` na mesma transação da mudança e consulta paginada com filtros, sem rotas); `llm/` (modelo `ProviderCredential` com a chave cifrada e o serviço que a gerencia; interface `LLMProvider` com streaming de deltas e uso de tokens, adaptadores sobre os SDKs oficiais `openai` (OpenAI, OpenRouter e compatíveis por `base_url`) e `anthropic`, `FakeLLMProvider` determinístico do tipo `fake`, fábrica por credencial e erros de domínio do provedor; interface `EmbeddingProvider` com lotes por itens e tokens estimados, adaptadores OpenAI/OpenRouter, `FakeEmbeddingProvider` (bag-of-words com hashing) e tabela de preços de embedding sobrescrevível por `KNOBRIDGE_EMBEDDING_PRICES`); `assistants/` (modelo `Assistant` com credencial do mesmo workspace por FK composta, modelo, temperatura, idioma, tom, mensagem de "sem fonte" com padrão em pt-BR e `active`, e o serviço que o gerencia); `conversations/` (modelos `Conversation`, `Message` e `Feedback`, interface `Retriever` com `NullRetriever` em produção, montagem do prompt com fontes numeradas e a rodada de chat em duas fases: sem fonte, a mensagem de "sem fonte" sem chamar o LLM; com fonte, streaming do LLM fora de transação e desfecho gravado no fim; resposta `streaming` órfã há mais de 5 minutos lida e regravada como `interrupted`; consultas administrativas sem N+1 e totais do período); `ingestion/` (modelo do índice de conhecimento, [ADR 0004](../docs/adr/0004-indice-de-conhecimento.md): `Collection`, `Source` com configuração por tipo validada em Pydantic, `Run`, `RunError`, `Document` e `Chunk` com `vector(1536)` e `tsv` gerado; ainda sem ingestão); `email/` (interface `EmailSender`, adaptador SMTP com `aiosmtplib`, envio em segundo plano após a resposta e templates Jinja2 pt-BR dos e-mails transacionais; em dev, o Mailpit do compose); `core/clock.py` com o relógio injetável; `migrations/` com Alembic async, a migração que habilita pgvector, a de tenancy com RLS forçada ([ADR 0001](../docs/adr/0001-tenancy-e-rls.md)) , a de `sessions`/`user_tokens`, a de `audit_events`, a de `login_attempts`, a de `invitations`, a de `provider_credentials`, a de `assistants`, a de `conversations`/`messages`/`feedback` e a do índice de conhecimento (`collections`, `sources`, `runs`, `run_errors`, `documents`, `chunks`); `Dockerfile` com a imagem única de api, worker e migrações; ainda sem workflows de domínio. Como instalar e rodar: [README.md](README.md).

**Entra aqui**: código de produção em `src/knobridge/`, testes em `tests/`, migrações em `migrations/`, `pyproject.toml`, `uv.lock`, `.env.example`, `Dockerfile`, `README.md` curto (como rodar).
**Não entra aqui**: documentação (vai para `docs/`), frontend e widget, Docker Compose e Helm (vão para `deploy/`), dados reais de clientes.

**Layout previsto** (crie cada pasta só quando for necessária, sempre com o seu `AGENTS.md`):

```
backend/
  src/knobridge/
    core/          # settings, logging, sessão de banco, segurança, erros, ids
    tenancy/       # workspace, usuários, autenticação e-mail/senha, API keys, RBAC
    ingestion/     # modelo do índice (Collection, Source, Run, Document, Chunk), parsing, chunking,
                   # orquestração incremental por hash e cursor
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
- FastAPI com um router por módulo; schemas Pydantic v2 na fronteira; nunca modelo ORM em resposta. Tudo sob `/v1`. O OpenAPI gerado é o contrato do frontend e vai para `docs/specs/openapi.json` a cada mudança (`uv run knobridge-openapi`).
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

**Leia também**: `AGENTS.md` da raiz (seções 5, 6 e 9); `docs/01-visao-do-projeto.md`, seções 6 a 8; `docs/specs/` (contrato OpenAPI em `docs/specs/openapi.json`); CI em `.github/workflows/ci.yml` (job `backend`).
