# AGENTS.md — KnoBridge

Instruções para qualquer agente de IA (Claude Code, Codex, Cursor, Copilot, Gemini CLI…) e para humanos que trabalham neste repositório. Leia este arquivo inteiro antes da primeira alteração, e leia o `AGENTS.md` da pasta onde for mexer antes de tocar nela. O `CLAUDE.md` da raiz só importa este arquivo: não duplique regras lá.

Se este arquivo e um `AGENTS.md` de pasta conflitarem, vale o mais específico (o da pasta), e o conflito deve ser resolvido na mesma entrega.

## 1. O projeto em três linhas

KnoBridge é uma plataforma open source (Apache 2.0) que conecta repositórios de código, sistemas de chamados e documentações, transforma tudo em índices para RAG por meio de pipelines visuais e incrementais, e entrega suporte em linguagem natural por API REST, API compatível com OpenAI, webhooks, MCP, Slack, Google Chat e widget embutível.

- **Fonte da verdade sobre o produto**: [docs/01-visao-do-projeto.md](docs/01-visao-do-projeto.md). Escopo, arquitetura (seção 6), módulos (7), stack (8), decisões (9), roadmap (11) e perguntas em aberto (13).
- **Status em 2026-10-11**: bootstrap ([0001](docs/planos/0001-bootstrap.md)) e plataforma navegável ([0002](docs/planos/0002-plataforma-navegavel.md)) concluídos; primeiro conhecimento ([0003](docs/planos/0003-primeiro-conhecimento.md)) entregue: fontes Git e pastas locais indexadas de forma incremental no Temporal, busca híbrida (pgvector + FTS) e chat com citações de arquivo, linhas e commit. Resumo e próximos passos na seção 12 deste arquivo.

## 2. Regras inegociáveis

1. **Todo código vem com testes, na mesma entrega.** Código sem teste é tarefa incompleta, não "fase seguinte".
2. **Cobertura mínima de 95%** (linhas e branches) em cada pacote tocado, com gate automático na suíte e na CI. Detalhes na seção 5.
3. **Toda pasta criada recebe um `AGENTS.md`** dizendo para que ela serve, o que entra e o que não entra nela. Regras na seção 4, template na seção 13.
4. **Toda documentação e todo plano ficam em `docs/`.** Fora de `docs/`, só `README.md`, `AGENTS.md`, `CLAUDE.md`, `LICENSE`, `CHANGELOG.md` e `CONTRIBUTING.md` na raiz, e um `README.md` curto por pacote quando ajudar a rodar.
5. **Monorepo**: nesta versão, backend, frontend, widget, infra e docs vivem neste repositório. Não crie repositórios separados nem submódulos.
6. **Não reabra decisão fechada** (tabela da seção 9 da visão) sem registrar o motivo num ADR (seção 7).
7. **Multi-tenant desde o primeiro modelo**: tudo que guarda dado tem `workspace_id`; nenhuma consulta sem filtro de workspace; isolamento coberto por teste.
8. **Citações obrigatórias**: resposta de assistente sem fonte não existe. Sem fonte, o assistente diz que não sabe e oferece abrir chamado.
9. **Nada de dados reais de clientes no repositório**: nem chamados, nem código de sistemas de terceiros, nem `.env`. Fixtures são sintéticas e pequenas.
10. **Sem framework pesado de LLM** (LangChain, LlamaIndex como framework): SDKs oficiais dos provedores + abstrações próprias e pequenas (decisão D6).

## 3. Fluxo obrigatório para qualquer pedido do usuário

Todo pedido, grande ou pequeno, segue estas etapas, nesta ordem. Pedidos pequenos (uma única subfase) usam o mesmo fluxo com um plano curto. O que nunca se pula: perguntar antes, aprovar antes, commit por subfase e andamento no frontmatter.

Antes de começar, leia este arquivo, o `AGENTS.md` de cada pasta que for tocar e confira se o pedido esbarra em alguma decisão da seção 9 da visão (se precisar mudar uma, primeiro o ADR, depois o código).

### 3.1 Entender: perguntar até não restar dúvida

- Antes de planejar, faça ao usuário todas as perguntas necessárias para saber exatamente o que precisa ser feito: objetivo, escopo (o que entra e o que fica de fora), critérios de aceite, restrições, prioridades, o que já existe e pode ser reaproveitado.
- Perguntas objetivas, agrupadas numa mensagem, com opções e recomendação quando couber. Repita a rodada até que não exista dúvida capaz de mudar o trabalho. Não comece a planejar com suposições sobre o que o usuário "provavelmente" quer.
- Registre perguntas e respostas na seção "Entendimento" do plano (3.2). Elas fazem parte do contrato.

### 3.2 Planejar e pedir aprovação

- Crie `docs/planos/NNNN-slug.md` a partir de [docs/planos/0000-modelo.md](docs/planos/0000-modelo.md) (NNNN sequencial). O plano descreve tudo que será executado para cumprir o pedido, organizado em **fases lógicas** e **subfases**.
- Tamanho de uma subfase: o que um agente isolado executa de ponta a ponta com um prompt de até uma página de contexto, deixando a suíte verde e a cobertura no gate. Referência: um módulo ou um punhado de arquivos, da ordem de 200 a 800 linhas somando código e testes, um único commit. Menor que isso, junte com a vizinha; maior, divida.
- Cada subfase tem: objetivo, entregáveis (arquivos e pastas), contexto necessário (quais arquivos, specs e seções de `AGENTS.md` o agente precisa ler, e nada além), critérios de aceite (incluindo os testes que devem existir) e dependências de outras subfases.
- Mude o `status` para `aguardando_aprovacao`, mostre ao usuário o caminho do arquivo e um resumo das fases, e peça que leia e responda de forma afirmativa se concordar. Qualquer resposta que não seja uma aprovação clara ("sim", "aprovado", "pode seguir") é pedido de revisão: ajuste o plano e peça de novo. **Nada é executado antes da aprovação.**
- Mudança de plano depois de aprovado (subfase nova, escopo diferente) volta para `aguardando_aprovacao` na parte alterada.

### 3.3 Executar: uma subfase por agente isolado

- Depois da aprovação, execute as subfases na ordem do plano, **cada uma num agente isolado** (subagente, nova sessão ou worktree), que recebe só: o trecho do plano da sua subfase, os `AGENTS.md` das pastas que vai tocar e os arquivos e specs listados no contexto necessário. Não repasse a conversa inteira nem subfases alheias.
- O agente da subfase entrega código, testes e docs tocadas, com lint, typecheck e cobertura no gate, e relata o que fez, o que ficou fora e as dúvidas encontradas.
- O agente orquestrador (quem conduz o plano) valida a entrega (roda a suíte, confere o checklist da seção 11), faz o commit (3.4), atualiza o frontmatter (3.5) e só então inicia a subfase seguinte.
- Se uma subfase revelar algo que muda o plano ou depende do usuário, pare, registre a pendência (3.6) e pergunte. Não improvise escopo nem reduza o escopo em silêncio.

### 3.4 Commit por subfase

- Cada subfase concluída vira um commit (Conventional Commits, seção 8) com o sufixo `[plano NNNN Fx.y]` na primeira linha, incluindo código, testes, docs e a atualização do plano.
- Branch: `plano/NNNN-slug`, salvo instrução do usuário para commitar em outro lugar. PR ao final do plano, se o usuário quiser.
- O hash do commit entra no frontmatter da subfase na atualização seguinte do plano (próxima subfase ou commit de encerramento).

### 3.5 Andamento no frontmatter

- O frontmatter do plano é a única fonte do andamento: `status` do plano, `status` de cada fase e subfase (`pendente`, `em_execucao`, `concluida`, `bloqueada`, `cancelada`), agente que executou, datas e commit.
- Atualize a cada transição de estado, não "no fim". Quem lê só o frontmatter precisa saber onde o plano está.
- O corpo do plano tem a seção "Registro de andamento" com uma linha datada por evento relevante (início e fim de subfase, bloqueio, mudança de plano).

### 3.6 Decisões e pendências

- `decisoes[]` no frontmatter: toda decisão tomada durante o planejamento ou a execução, com o quê, por quê, alternativas descartadas, data e quem decidiu (`agente` ou `usuario`).
- `pendencias_usuario[]`: tudo que depende de resposta do usuário, com status `aberta` ou `respondida` e a resposta quando vier. Pendência aberta que bloqueia uma subfase deixa a subfase `bloqueada`.
- Decisão de arquitetura (muda stack, modelo de dados, contrato ou algo da seção 9 da visão), além do registro no plano, ganha ADR (seção 7).

### 3.7 Encerrar

- Com todas as subfases `concluida`: `status: concluido`, `concluido_em`, resumo final no corpo (o que foi entregue, o que ficou de fora e por quê, como demonstrar) e commit de encerramento `docs(plano): close plan NNNN`.
- Antes de encerrar, passe pelo checklist de pronto (seção 11) e atualize na mesma entrega os `AGENTS.md` das pastas afetadas, o `README.md` do pacote se o modo de rodar mudou e a visão se o escopo mudou.

## 4. Estrutura do monorepo

| Pasta | Função | Estado |
|---|---|---|
| `docs/` | Toda documentação e planos: visão, plano, ADRs, especificações, guias, pesquisa | Existe |
| `backend/` | Python: API REST e compatível com OpenAI (FastAPI), workers e workflows (Temporal), conectores, engine de pipelines, harness de código, recuperação, assistentes, canais, servidor MCP, migrações | Existe |
| `frontend/` | Painel admin em React + TypeScript (canvas de pipelines, fontes, assistentes, canais, conversas) | Existe |
| `widget/` | Web Component do chat embutível (1 arquivo JS) | A criar |
| `deploy/` | Docker Compose, Helm chart, scripts de infra | Existe |
| `scripts/` | Automação do repositório (checagens de CI, geração de código) | Existe |
| `.github/` | Workflows de CI | Existe |

Regras:

- Pasta nova de primeiro nível só com justificativa no PR e linha nesta tabela.
- **Toda pasta, em qualquer nível, criada por nós tem `AGENTS.md`.** Exceções: pastas geradas ou vendorizadas (`node_modules/`, `.venv/`, `dist/`, `build/`, `__pycache__/`, `coverage/`, `htmlcov/`, `.pytest_cache/`), pastas de arquivos gerados por ferramenta (ex.: `migrations/versions/`) e pastas que contêm só dados de fixture, sem código.
- O `AGENTS.md` de uma pasta é curto (10 a 60 linhas) e específico: função, o que entra e o que não entra, convenções locais, como testar, para onde apontar. Não repete o que está aqui; linka.
- Quando a função de uma pasta muda, o `AGENTS.md` dela muda na mesma entrega.
- A CI falha se houver pasta sem `AGENTS.md` (`scripts/check_agents_md.py`, também rodado no pre-commit).
- Codex e outros agentes carregam `AGENTS.md` de subpastas sozinhos; o Claude Code só carrega o da raiz via `CLAUDE.md`. Por isso a regra explícita: leia o `AGENTS.md` da pasta antes de editar nela.

## 5. Testes

- **Quando**: junto com o código, na mesma entrega. Em correção de bug, primeiro o teste que reproduz, depois a correção.
- **Gate**: cobertura mínima de **95%** de linhas e branches por pacote. Backend: `pytest --cov --cov-branch --cov-fail-under=95`. Frontend: thresholds de 95 em `lines`, `branches`, `functions` e `statements` no Vitest. A CI bloqueia o merge abaixo disso.
- **Cobertura não se maquia**: `# pragma: no cover` e `/* v8 ignore */` só para `if TYPE_CHECKING`, blocos `__main__` e código de plataforma inacessível na CI, sempre com comentário dizendo por quê. Excluir arquivo da medição exige justificativa no PR.
- **Pirâmide**:
  - Unitários: rápidos, sem rede, sem disco quando possível. São a maioria.
  - Integração: Postgres (com pgvector) e Temporal **reais**, via testcontainers e ambiente de teste do SDK. Nunca mock de banco para testar consulta.
  - Contrato: todo conector passa pela mesma suíte de contrato (`list_changes`, `fetch`, `permissions`, `test_connection`) sobre uma fonte fake; todo canal passa pela suíte "mensagem → resposta com citações".
  - Isolamento: para cada consulta que toca dado de workspace, um teste de que o workspace B não vê o dado do A.
  - E2E: poucos e valiosos (Playwright no canvas: criar pipeline, rodar com amostra, ver saída; chat de teste com citações).
- **Fora do alcance dos testes**: LLM, embeddings, reranker e APIs externas nunca são chamados em teste. Use fakes atrás das interfaces (`LLMProvider`, `EmbeddingProvider`, `Reranker`, `Connector`, `Channel`) e executáveis fake para o harness (`claude`/`codex` falsos que emitem o JSONL esperado).
- **Determinísticos**: sem `sleep`, sem dependência de ordem, sem hora real (injete o relógio), sem aleatoriedade sem seed.
- **Fixtures**: pequenas e sintéticas, em `tests/fixtures/`. Nenhum repositório real, nenhum chamado real.
- **Nome e forma**: `test_<unidade>_<comportamento>` (ex.: `test_hybrid_search_filters_by_workspace`), estrutura arrange / act / assert, um comportamento por teste.
- **Falhou na CI?** Corrija a causa. Não marque como flaky, não aumente timeout, não pule.

## 6. Código

### 6.1 Em qualquer linguagem

- **Idioma**: código, identificadores, comentários, mensagens de commit e de log em **inglês**. Documentação em `docs/` e textos de interface em **português (pt-BR)**, com i18n preparada desde o início.
- **Vocabulário do domínio** (use estes nomes no código): `Workspace`, `Source`, `Connector`, `Pipeline`, `Run`, `Document`, `Chunk`, `Collection`, `Target`, `Assistant`, `Action`, `Channel`, `Conversation`, `Harness`. Definições na seção 5 da visão.
- Funções pequenas com um propósito; sem abstração para uso único; sem tratar erro impossível; validação nas fronteiras (API, CLI, tool MCP, conector, canal) e confiança no interior.
- Tipos explícitos em todo lugar (Python com type hints checados por pyright; TypeScript `strict`). Sem `Any`/`any` sem comentário justificando.
- Dependências externas (LLM, embeddings, reranker, conectores, canais, armazenamento de objetos, harness) atrás de interfaces pequenas, injetadas. Trocar provedor não pode exigir mexer em pipeline.
- Configuração só por variável de ambiente, lida num único módulo de settings; `.env.example` sempre atualizado; `.env` nunca commitado.
- Logs estruturados (JSON), sempre com `workspace_id` e `run_id` ou `conversation_id`. Nunca `print` fora de CLI. Nunca logar prompt completo, chunk completo ou dado pessoal em nível INFO.
- Idempotência: nós de pipeline e activities podem ser reexecutados sem efeito duplicado (hash por documento, upsert por chave natural).
- Erros: exceções específicas do domínio; na API, formato único de erro (`{"error": {"code", "message", "details"}}`) e códigos HTTP corretos.
- Comentários explicam "por quê", não "o quê". Docstring só onde o nome não basta.
- Sem código morto, sem `TODO` sem issue, sem arquivo gigante (acima de ~400 linhas, divida).
- Performance com medida: batch em embeddings e escrita no banco; sem N+1; paginação em toda listagem da API.

### 6.2 Backend (Python)

Resumo; detalhes e layout em [backend/AGENTS.md](backend/AGENTS.md).

- Python 3.12+, `uv`, `ruff` (lint + format), `pyright` em modo strict, `pytest` + `pytest-cov` + `testcontainers`.
- FastAPI, SQLAlchemy 2 (tipado, async), Alembic, Pydantic v2, SDK Python do Temporal, SDKs oficiais de OpenAI e Anthropic, MCP SDK.
- Postgres 17 + pgvector + FTS; RLS por `workspace_id`.

### 6.3 Frontend (TypeScript)

Resumo; detalhes e layout em [frontend/AGENTS.md](frontend/AGENTS.md).

- Node LTS, `pnpm`, Vite, React, TypeScript `strict`, ESLint + Prettier, Vitest + Testing Library, Playwright.
- shadcn/ui, React Flow (xyflow) para o canvas, TanStack Query para dados, cliente de API gerado do OpenAPI do backend.

## 7. Documentação e decisões

- Tudo em `docs/`, em Markdown, pt-BR. Convenções da pasta em [docs/AGENTS.md](docs/AGENTS.md).
- Documentos numerados por ordem de leitura: `01-visao-do-projeto.md`, `02-...`. Planos de execução, um por pedido do usuário, em `docs/planos/NNNN-slug.md` (seção 3), com andamento, decisões e pendências no frontmatter.
- **ADR** (decisão de arquitetura): `docs/adr/NNNN-titulo-curto.md` com contexto, decisão, alternativas, consequências e status. Toda decisão nova ou revertida ganha um ADR e uma linha na tabela da seção 9 da visão apontando para ele.
- Especificações (contratos de API, modelo de dados, formato do `.md` de conhecimento e seu frontmatter, protocolo dos conectores, schema JSON do harness) em `docs/specs/`. Guias de operação em `docs/guias/`. Notas de pesquisa em `docs/pesquisa/`.
- Documentação muda **na mesma entrega** que o comportamento. PR que muda comportamento sem tocar docs está incompleto.
- `README.md` da raiz: o que é, como subir, onde ler mais. Curto.

## 8. Git, PRs e CI

- `main` protegida; trabalho em branch por tarefa: `feat/<escopo>-<resumo>`, `fix/...`, `docs/...`, `chore/...`.
- Commits pequenos e atômicos, **Conventional Commits** em inglês, no imperativo: `feat(connectors): add git connector with incremental sync by sha`. O corpo explica o porquê quando não for óbvio.
- Nunca `--no-verify`, nunca `push --force` em `main`, nunca reescrever histórico compartilhado.
- PR descreve: o que mudou, por quê, como testar (comando), docs e `AGENTS.md` tocados, decisões envolvidas.
- CI obrigatória para merge: lint, format check, typecheck, testes, cobertura ≥ 95%, build do frontend, checagem de `AGENTS.md` por pasta, varredura de segredos.
- Agentes de IA commitam ao fim de cada subfase de um plano aprovado (seção 3.4); fora disso, só quando a tarefa pede. Nunca em `main` sem instrução explícita do usuário.

## 9. Segurança e privacidade (LGPD)

- Isolamento entre workspaces é requisito de segurança, não de produto: RLS no Postgres, filtro na aplicação e testes.
- Permissão herdada da fonte: o chunk carrega a ACL; a recuperação filtra pelo usuário antes de montar o contexto.
- Segredos (chaves de API, tokens de conectores e canais) cifrados em repouso, nunca em log, nunca em resposta de API.
- Harness de código roda **somente leitura**, com cwd no checkout, sem permissão de escrita nem shell (Claude Code: `--tools Read,Grep,Glob` + `--disallowedTools Edit,Write,Bash`; Codex: `--sandbox read-only`), com orçamento e timeout por job. Item sem evidência `arquivo:linhas` verificada é rejeitado, nunca gravado.
- Dados pessoais em chamados: nó de anonimização disponível no pipeline; retenção configurável; logs de conversa opcionais por workspace.
- Dependências com versões fixadas por lockfile (`uv.lock`, `pnpm-lock.yaml`); atualizações em PR próprio.

## 10. O que não fazer

- Entregar código sem teste "para testar depois".
- Baixar o gate de cobertura, excluir arquivos da medição ou espalhar `no cover` para passar na CI.
- Criar pasta sem `AGENTS.md`; deixar `AGENTS.md` desatualizado quando a função da pasta mudou.
- Colocar documento ou plano fora de `docs/`.
- Adicionar LangChain/LlamaIndex como framework, WhatsApp/Telegram/Chatwoot como canal, ou qualquer item marcado como fora de escopo na visão, sem ADR.
- Consultar banco sem filtro de workspace; aceitar `workspace_id` vindo do cliente da API pública (ele vem da autenticação).
- Chamar LLM, embeddings ou API externa em teste.
- Usar dados reais de clientes (chamados, código de ERP) em fixtures, exemplos ou docs.
- Deixar o harness escrever no checkout ou aceitar item sem fonte verificada.
- Commitar `.env`, chaves, tokens, dumps.

## 11. Checklist de pronto (Definition of Done)

- [ ] Testes escritos junto com o código; suíte verde local.
- [ ] Cobertura ≥ 95% (linhas e branches) no(s) pacote(s) tocado(s).
- [ ] Lint, format e typecheck limpos.
- [ ] Toda pasta nova tem `AGENTS.md`; `AGENTS.md` das pastas alteradas revisados.
- [ ] `docs/` atualizada: plano do pedido com frontmatter em dia (subfase, commit, decisões, pendências), ADR se houve decisão de arquitetura, visão se houve mudança de escopo, spec se houve mudança de contrato.
- [ ] `.env.example`, `README` do pacote e migrações atualizados quando aplicável.
- [ ] Nenhum segredo, nenhum dado real, nenhum `print`/`console.log` esquecido.
- [ ] Há um comando que demonstra o resultado, descrito na entrega.

## 12. Estado atual

### 12.1 Bootstrap (plano 0001)

O bootstrap (plano [0001](docs/planos/0001-bootstrap.md)) montou o esqueleto e os gates desta página, ainda sem funcionalidades de produto:

1. Raiz: `.gitignore`, `.gitattributes`, `.editorconfig`, `CHANGELOG.md` e `.pre-commit-config.yaml` (higiene de arquivos, ruff, prettier, gitleaks, `check_agents_md.py` e `check_plans.py`).
2. `backend/`: projeto `uv` com ruff, pyright strict e pytest com gate de 95%; pacote `knobridge` com settings, logging JSON, erros, engine async do banco, `GET /v1/health/live` e `/v1/health/ready`, exportação do OpenAPI para `docs/specs/openapi.json`, migrações Alembic (pgvector), worker Temporal com workflow de saúde e `Dockerfile`.
3. `frontend/`: Vite + React + TypeScript strict, ESLint/Prettier, Vitest com thresholds de 95, Tailwind + shadcn/ui, i18n pt-BR, cliente gerado do OpenAPI, MSW, smoke E2E com Playwright e `Dockerfile`.
4. `deploy/docker-compose.yml`: Postgres 17 + pgvector, Temporal (server + UI), MinIO, `migrate`, `api`, `worker` e `frontend`. Como subir: [docs/guias/subir-ambiente.md](docs/guias/subir-ambiente.md).
5. `scripts/check_agents_md.py` e `scripts/check_plans.py` (valida o frontmatter de `docs/planos/`), com testes.
6. `.github/workflows/ci.yml`: gates de `scripts/`, `backend/` e `frontend/` (incluindo contrato OpenAPI e Playwright), varredura de segredos com gitleaks e validação do compose.

### 12.2 Plataforma navegável (plano 0002)

O plano [0002](docs/planos/0002-plataforma-navegavel.md) entregou a base navegável do produto, ainda sem RAG:

1. Multi-tenant com RLS forçada por `SET LOCAL`, usuários em N workspaces, papéis owner/admin/editor/viewer e superadmin da instância ([ADR 0001](docs/adr/0001-tenancy-e-rls.md)).
2. Autenticação por e-mail e senha com sessão server-side, CSRF double-submit assinado, tokens de uso único por e-mail (redefinição de senha, verificação, convite), limitação de login e configuração inicial ([ADR 0002](docs/adr/0002-sessao-server-side.md); contrato em [docs/specs/autenticacao.md](docs/specs/autenticacao.md)). E-mails transacionais via SMTP, com Mailpit em dev.
3. Trilha de auditoria por workspace e da instância; administração da instância (workspaces, usuários).
4. Credenciais de provedores de LLM (OpenAI, Anthropic, OpenRouter e `fake` para dev e testes) cifradas com AES-256-GCM ([ADR 0003](docs/adr/0003-segredos-cifrados.md)), assistentes configuráveis e chat em streaming (SSE) com citações, feedback e visão administrativa das conversas ([docs/specs/chat.md](docs/specs/chat.md)). Até o plano 0003, sem indexação, o `Retriever` de produção não encontrava fonte e toda resposta era a de "sem fonte" (regra 8).
5. Painel admin em React com shell por papel, seletor de workspace, telas de conta, membros e convites, provedores, assistentes, chat, conversas e auditoria; E2E da stack inteira contra o compose na CI.

Modelo de dados em [docs/specs/modelo-de-dados.md](docs/specs/modelo-de-dados.md); primeiro uso em [docs/guias/primeiro-acesso.md](docs/guias/primeiro-acesso.md).

### 12.3 Primeiro conhecimento (plano 0003)

O plano [0003](docs/planos/0003-primeiro-conhecimento.md) levou o primeiro conhecimento de ponta a ponta:

1. Índice de conhecimento no Postgres: coleções (credencial e modelo de embedding), fontes, execuções, documentos e chunks com `vector(1536)` HNSW e `tsvector` gerado, todos com RLS ([ADR 0004](docs/adr/0004-indice-de-conhecimento.md)).
2. Conectores de pasta local e Git (`backend/src/knobridge/connectors/`), com seleção de arquivos compartilhada, cursores versionados e suíte de contrato ([docs/specs/conectores.md](docs/specs/conectores.md)).
3. Parsing para Markdown, chunking por títulos, AST (tree-sitter) e commit, embeddings em lote com cache por hash e o workflow `knobridge.ingestion.v1` no Temporal, manual ou por Temporal Schedule, com custo registrado por execução ([docs/specs/indexacao.md](docs/specs/indexacao.md)).
4. Busca híbrida com RRF e similaridade mínima, `HybridRetriever` no chat com coleções por assistente e citações de arquivo, linhas e commit ([docs/specs/chat.md](docs/specs/chat.md)).
5. Telas de coleções (com "testar busca") e fontes no painel, pasta de fontes `/sources` no compose e E2E de indexação contra a stack. Passo a passo em [docs/guias/indexar-uma-fonte.md](docs/guias/indexar-uma-fonte.md).

### 12.4 Próximos passos

Siga o roadmap da visão. Da Fase 0 ainda faltam: conector de chamados, harness de código em 2 ou 3 módulos reais com Claude Code e com Codex, e a comparação OpenAI x Gemini embedding em pt-BR.

## 13. Template de `AGENTS.md` de pasta

````markdown
# <caminho/da/pasta>

**Função**: uma ou duas frases sobre o que vive aqui e por quê.

**Entra aqui**: lista curta.
**Não entra aqui**: lista curta, com o lugar certo de cada coisa.

**Convenções locais**: só o que difere ou detalha o `AGENTS.md` da raiz (nomes de arquivo, padrões de módulo, limites).

**Como testar**: comando(s) que rodam os testes desta pasta e o gate de cobertura.

**Leia também**: links para specs, ADRs e docs relevantes.
````
