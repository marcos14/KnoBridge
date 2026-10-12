---
id: 0006
titulo: Docker Compose e .env na raiz do repositório
slug: compose-na-raiz
solicitado_por: usuario
criado_em: 2026-10-12
atualizado_em: 2026-10-12
status: concluido
aprovado_em: 2026-10-12
aprovado_por: usuario
concluido_em: 2026-10-12
branch: plano/0005-chamados-por-api
fases:
  - id: F1
    titulo: Mudança
    status: concluida
    subfases:
      - id: F1.1
        titulo: Mover os composes e o .env para a raiz e atualizar caminhos, CI, guias e AGENTS.md
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-12
        concluida_em: 2026-10-12
        commit: 7c29916
decisoes:
  - id: D1
    data: 2026-10-12
    por: usuario
    decisao: "docker-compose.yml e docker-compose.e2e.yml vão para a raiz; deploy/postgres e deploy/sources ficam em deploy/; .env.example e o .env local vão para a raiz; a mudança entra na branch plano/0005-chamados-por-api"
    motivo: "subir a stack a partir da raiz, sem -f, e com o .env no lugar padrão do Compose"
    alternativas: "só o compose principal; mover também postgres/ e sources/; branch nova"
    adr: null
  - id: D2
    data: 2026-10-12
    por: agente
    decisao: "Planos encerrados (0001 a 0005) e relatórios de pesquisa (0001 a 0003) não são editados: registram o que valia na data; guias, README, AGENTS.md, CI, E2E e specs vigentes passam a usar os caminhos novos"
    motivo: "documentos datados descrevem o passado; documentos de uso precisam estar certos hoje"
    alternativas: "reescrever os caminhos em todo o histórico"
    adr: null
  - id: D3
    data: 2026-10-12
    por: agente
    decisao: "Convenções do compose ficam no deploy/AGENTS.md (seção Arquivos do compose, na raiz), com a raiz apontando para lá; KNOBRIDGE_SOURCES_DIR padrão passa a ./deploy/sources (relativo à raiz); CHANGELOG com nota de migração em Changed; o .env local do usuário foi movido pelo orquestrador com KNOBRIDGE_SOURCES_DIR ajustado de ./sources para ./deploy/sources"
    motivo: "manter o AGENTS.md da raiz curto e os caminhos relativos certos depois da mudança"
    alternativas: "regras do compose no AGENTS.md raiz"
    adr: null
pendencias_usuario: []
---

# Plano 0006 — Docker Compose e .env na raiz

## 1. Pedido original

> "leve o .env e docker compose para a raiz"

## 2. Entendimento (perguntas e respostas)

| # | Pergunta | Resposta | Data |
|---|---|---|---|
| 1 | Quais composes vão para a raiz? | Os dois (`docker-compose.yml` e `docker-compose.e2e.yml`) | 2026-10-12 |
| 2 | E `deploy/postgres` e `deploy/sources`? | Ficam em `deploy/` | 2026-10-12 |
| 3 | O `.env`? | `.env.example` e o `.env` local vão para a raiz | 2026-10-12 |
| 4 | Onde fazer? | Na branch atual (`plano/0005-chamados-por-api`) | 2026-10-12 |

**O que será feito**: `git mv` dos dois composes e do `.env.example` para a raiz, com os caminhos internos ajustados (`build: ./backend`, `./frontend`, `./deploy/postgres`, `./deploy/sources`, `./frontend/e2e/stack/fixtures`, `./scripts/webhook_sink.py`). O `.env` local é movido sem entrar no git. Os nomes de projeto (`knobridge` e `knobridge-e2e`) não mudam, então os volumes e os dados das stacks existentes continuam valendo. Todo comando `docker compose -f deploy/docker-compose.yml ...` vira `docker compose ...` (ou `-f docker-compose.yml -f docker-compose.e2e.yml`) em README, guias, CI (`ci.yml`), configuração do Playwright de stack, specs de E2E, testes e `AGENTS.md`. O `deploy/AGENTS.md` passa a descrever só o que ficou em `deploy/`.

**Fora do escopo**: mover `deploy/postgres` e `deploy/sources`; editar planos encerrados e relatórios de pesquisa (D2).

## 3. Critérios de aceite

- [ ] `docker compose config` e `docker compose -f docker-compose.yml -f docker-compose.e2e.yml config` válidos a partir da raiz, lendo o `.env` da raiz.
- [ ] Nenhuma referência a `deploy/docker-compose` ou `deploy/.env` fora dos planos encerrados e relatórios de pesquisa.
- [ ] CI (`ci.yml`) com os caminhos novos e validação do compose; checagens de `AGENTS.md` e de planos verdes.
- [ ] E2E da stack verde a partir dos composes da raiz; gates do frontend (inclui a configuração do Playwright) e testes do runner (`test_excerpt.py` cita o caminho) verdes.
- [ ] O `.env` local continua fora do git, agora na raiz.

## 4. Fases e subfases

### F1 — Mudança

#### F1.1 — Mover e atualizar referências

- **Objetivo**: compose e `.env` na raiz, com tudo apontando para o lugar novo.
- **Entregáveis**: `docker-compose.yml`, `docker-compose.e2e.yml` e `.env.example` na raiz; `.env` local movido; `.github/workflows/ci.yml` e `.github/workflows/AGENTS.md`; `README.md`; `AGENTS.md` raiz (seção 4 e trechos de comandos); `deploy/AGENTS.md`, `deploy/postgres/AGENTS.md`, `deploy/sources/AGENTS.md`; `docs/guias/subir-ambiente.md`, `primeiro-acesso.md`, `indexar-uma-fonte.md` e os demais guias que citem o caminho; `frontend/playwright.stack.config.ts`, `frontend/e2e/stack/` (spec e `AGENTS.md`), `frontend/AGENTS.md`, `frontend/README.md`; `scripts/AGENTS.md`; `runner/tests/test_excerpt.py`; `.gitignore` se precisar.
- **Contexto necessário**: os arquivos acima.
- **Critérios de aceite**: os da seção 3.
- **Depende de**: nenhuma.
- **Tamanho**: pequeno.

## 5. Decisões

D1 vem das respostas do usuário; D2 é do agente.

## 6. Pendências do usuário

Nenhuma.

## 7. Registro de andamento

- 2026-10-12 — plano criado; aguardando aprovação.
- 2026-10-12 — plano aprovado pelo usuário ("aprovado"); F1.1 iniciada (agente em worktree).
- 2026-10-12 — F1.1 concluída: composes e .env.example na raiz com caminhos ajustados, .env do usuário movido, referências vigentes atualizadas; compose config, scripts 98, runner 436, frontend 1240 e E2E da stack 3/3 a partir da raiz
- 2026-10-12 — Plano concluído; encerramento na seção 8.

## 8. Encerramento

**Entregue**: `docker-compose.yml`, `docker-compose.e2e.yml` e `.env.example` na raiz (com `git mv`), caminhos internos relativos à raiz, `.env` local do usuário movido para a raiz (fora do git) com `KNOBRIDGE_SOURCES_DIR=./deploy/sources`, e todas as referências vigentes atualizadas (README, `AGENTS.md`, guias, CI, E2E, um teste do runner). `deploy/` mantém `postgres/` e `sources/`. Planos encerrados e relatórios de pesquisa não foram editados (D2).

**Validação**: `docker compose config` na raiz (com e sem o overlay de E2E), `scripts` (98 testes), `runner` (436), frontend (1240 e build) e o E2E da stack a partir dos composes da raiz (3 de 3).

**Como usar**: na raiz, `docker compose up -d --build --wait`; E2E: `docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d --build --wait` (guia [subir-ambiente.md](../guias/subir-ambiente.md)).
