# Changelog

Todas as mudanças relevantes deste projeto são registradas aqui.

O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto adota o [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Added

Harness de código com runner local (plano [0004](docs/planos/0004-harness-runner-local.md)): o Claude Code ou o Codex rodam somente leitura na máquina que tem o checkout e o conhecimento gerado, com evidências `arquivo:linhas` verificadas, é revisado no painel e citado no chat.

- Arquitetura ([ADR 0005](docs/adr/0005-runner-local-do-harness.md)): runner na máquina do usuário, credenciais dos CLIs só nela, HTTPS de saída com long-poll, fila de tarefas no Postgres com reserva, fonte do tipo `runner`; specs do [protocolo do runner](docs/specs/runner.md) e do [harness](docs/specs/harness.md).
- Dados: tabelas `runners`, `harness_modules`, `harness_jobs`, `knowledge_items` e `harness_rejections` com RLS; migrações `0014` e `0015` ([modelo de dados](docs/specs/modelo-de-dados.md)).
- Servidor: cadastro de runners com token `kbr_...` mostrado uma vez (hash SHA-256, revogação imediata), heartbeat, relatório de inventário com módulos sugeridos e editáveis, fila com claim por long-poll, heartbeat da tarefa, resultado, falha, adiamento por franquia ou login e expiração preguiçosa; disparo manual ou por commit; revisão (aprovar, editar, descartar, reabrir) e exportação `.md` com frontmatter em `.zip`; conector interno `knowledge` no workflow de ingestão, com sincronização pendente e citação `knowledge` no chat ([SSE v0.5](docs/specs/chat-sse.md)).
- Runner (`runner/`, pacote `knobridge-runner`): `configure`, `doctor` e `run`; camada 0 determinística (seleção de arquivos, inventário, sugestão de módulos, briefing); executores Claude Code (`--tools Read,Grep,Glob`) e Codex (`--sandbox read-only`) com trava de ferramenta que mata a árvore de processos, ambiente filtrado, resgate e classificação de franquia e login; verificação mecânica das evidências, excertos com segredos redigidos; executáveis falsos para a suíte e suíte opt-in `real_harness`.
- Painel: tela de Runners (presença, executores, repositórios, criar com token e comandos, revogar, excluir), formulário da fonte runner e abas Módulos, Tarefas (com rejeitados por motivo), Conhecimento (revisão, edição e exportação) e Indexação; citações de conhecimento com selo e evidências no chat.
- CI e E2E: job `runner`; E2E da stack que cria o runner no painel, sobe o `knobridge-runner` no host com o `claude` falso sobre um repositório sintético, roda um módulo, aprova a regra e vê a citação de conhecimento no chat.
- Docs: guia [mapear código com o runner](docs/guias/mapear-codigo-com-runner.md) (instalar, `configure`, `doctor`, assinatura x chave de API, segurança, o que sai da máquina, custos e fluxo no painel).

Primeiro conhecimento (plano [0003](docs/planos/0003-primeiro-conhecimento.md)): fontes Git e pastas locais indexadas de forma incremental e consultadas pelo chat com citações.

- Índice de conhecimento: coleções (credencial e modelo de embedding, `vector(1536)` fixo com HNSW cosseno e `tsvector` gerado), fontes, execuções, itens e erros por documento, documentos e chunks, todos com RLS ([ADR 0004](docs/adr/0004-indice-de-conhecimento.md)); migrações `0010` a `0012` ([modelo de dados](docs/specs/modelo-de-dados.md)).
- Conectores ([contrato](docs/specs/conectores.md)): pasta local (incremental por hash, atalho por mtime) e Git (árvore do HEAD pelos objetos do Git, clone local somente leitura ou URL https em clone parcial, incremental por SHA com reconstrução após force-push, commits como documentos sem e-mail), com seleção de arquivos compartilhada (raiz permitida, `.gitignore` aninhado, binários, lockfiles, globs, limites, PDF e Office) e suíte de contrato.
- Indexação ([spec](docs/specs/indexacao.md)): parsing para Markdown (MarkItDown para PDF, DOCX, XLSX, PPTX e HTML), chunking por títulos, por AST (tree-sitter para TypeScript, TSX, JavaScript e Go) e por commit, embeddings em lote com cache por hash (OpenAI, OpenRouter e `fake`), custo estimado por execução.
- Execução no Temporal: workflow `knobridge.ingestion.v1` com activities idempotentes e lotes de 50 documentos, uma execução por fonte, cancelamento, cursor gravado só no sucesso; agendamento por cron (UTC) em Temporal Schedules, com reconciliação na subida do worker.
- Busca híbrida (vetorial + textual em português e `simple`, fusão RRF, similaridade mínima, remoção de vizinhos) com rota "testar busca"; `HybridRetriever` no lugar do `NullRetriever`, com coleções e similaridade mínima por assistente e citações com caminho, linhas, símbolo, linguagem, SHA, autor e data.
- Painel: telas de coleções (com "testar busca") e fontes (cadastro Git ou pasta com globs e cron, testar conexão, sincronizar, cancelar, execuções, erros e documentos), coleções no assistente e citações de código e commit no chat.
- Deploy: pasta de fontes do host montada somente leitura em `/sources` (`KNOBRIDGE_SOURCES_DIR`), volume `source-clones` para clones por URL, `git` na imagem e E2E de indexação contra a stack.
- Docs: specs de [conectores](docs/specs/conectores.md) e de [indexação e busca](docs/specs/indexacao.md), guia [indexar uma fonte](docs/guias/indexar-uma-fonte.md).

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
