# KnoBridge

Plataforma open source (Apache 2.0) que conecta repositórios de código, sistemas de chamados e documentações, transforma tudo em índices para RAG por meio de pipelines visuais e incrementais, e entrega suporte em linguagem natural via API REST, API compatível com OpenAI, webhooks, MCP, Slack, Google Chat e chat embutível.

> Status: chamados por API (plano 0005) e harness de código com runner local (plano 0004) sobre o primeiro conhecimento (plano 0003) e a plataforma navegável (plano 0002). Login por e-mail e senha, workspaces multi-tenant com papéis, painel admin, provedores de LLM (OpenAI, Anthropic, OpenRouter) e assistentes com chat em streaming. Repositórios Git e pastas locais são indexados de forma incremental (Temporal, pgvector + busca textual), manualmente ou por agendamento, e o chat responde com citações de arquivo, linhas e commit; sem fonte, o assistente diz que não sabe. O `knobridge-runner`, na máquina que tem o checkout, roda o Claude Code ou o Codex somente leitura por módulo e gera regras de negócio com evidência `arquivo:linhas` verificada, revisadas no painel e citadas no chat. Chamados de qualquer sistema entram por API com token ou por upload de JSON/JSONL, são anonimizados e citados no chat com número e status; sem fonte, o chat abre um chamado no seu sistema por um webhook assinado. Ainda não há canvas de pipelines nem canais externos.

> Vai contribuir ou continuar o desenvolvimento (humano ou agente de IA)? Leia primeiro [AGENTS.md](AGENTS.md).

## Como subir

Com Docker e Compose v2, da raiz do repositório:

```bash
docker compose -f deploy/docker-compose.yml up -d --build --wait
```

Passo a passo, portas e solução de problemas em [docs/guias/subir-ambiente.md](docs/guias/subir-ambiente.md). Depois, abra <http://localhost:5173> e siga [docs/guias/primeiro-acesso.md](docs/guias/primeiro-acesso.md): configuração inicial, primeiro workspace, provedor `fake` (sem chave real) e assistente, com os e-mails lidos no Mailpit (<http://localhost:8025>). Para o assistente responder com citações, indexe uma pasta ou um repositório seguindo [docs/guias/indexar-uma-fonte.md](docs/guias/indexar-uma-fonte.md). Para gerar conhecimento do código com o Claude Code ou o Codex na sua máquina, instale o runner seguindo [docs/guias/mapear-codigo-com-runner.md](docs/guias/mapear-codigo-com-runner.md). Para trazer chamados do seu sistema de chamados e abrir chamados a partir do chat, siga [docs/guias/receber-chamados-por-api.md](docs/guias/receber-chamados-por-api.md).

## Como testar

Cada pacote tem os seus gates (cobertura mínima de 95% de linhas e branches). No Windows, exporte `PYTHONUTF8=1`.

```bash
# backend/ (Python, uv; os testes de integração exigem Docker)
cd backend && uv sync && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest

# frontend/ (Node 24, pnpm)
cd frontend && pnpm install --frozen-lockfile && pnpm lint && pnpm format:check && pnpm typecheck && pnpm test && pnpm build

# runner/ (knobridge-runner, uv; sem rede nem CLI real)
cd runner && uv sync && uv run ruff check . && uv run ruff format --check . && uv run pyright && uv run pytest

# scripts/ (checagens do repositório)
cd scripts && uv sync && uv run ruff check . && uv run pyright && uv run pytest

# hooks de pre-commit (da raiz; instale uma vez com `uvx pre-commit install`)
uvx pre-commit run --all-files
```

Detalhes em [backend/README.md](backend/README.md), [frontend/README.md](frontend/README.md), [runner/README.md](runner/README.md) e [scripts/AGENTS.md](scripts/AGENTS.md). A CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) roda tudo isso, mais Playwright, varredura de segredos e validação do compose.

## Onde ler mais

- [docs/01-visao-do-projeto.md](docs/01-visao-do-projeto.md): visão, arquitetura, stack, decisões e roadmap.
- [AGENTS.md](AGENTS.md): regras de trabalho, testes, estrutura do monorepo e fluxo de planos.
- [docs/specs/](docs/specs/): contratos ([autenticação e permissões](docs/specs/autenticacao.md), [chat](docs/specs/chat.md), [conectores](docs/specs/conectores.md), [indexação e busca](docs/specs/indexacao.md), [protocolo do runner](docs/specs/runner.md), [harness de código](docs/specs/harness.md), [chamados](docs/specs/chamados.md), [modelo de dados](docs/specs/modelo-de-dados.md), OpenAPI).
- [docs/adr/](docs/adr/): decisões de arquitetura.
- [docs/planos/](docs/planos/): planos de execução, com andamento e decisões.
- [CHANGELOG.md](CHANGELOG.md): o que mudou.
