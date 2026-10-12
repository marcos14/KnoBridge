---
id: 0008
titulo: Telas para usar e administrar a plataforma — primeiro acesso com workspace, painéis, uso e custos, API pública com chaves e melhorias nas telas existentes
slug: telas-de-uso-e-administracao
solicitado_por: usuario
criado_em: 2026-10-12
atualizado_em: 2026-10-12
status: em_execucao
aprovado_em: 2026-10-12
aprovado_por: usuario
concluido_em: null
branch: plano/0005-chamados-por-api
fases:
  - id: F1
    titulo: Contrato e modelo de dados
    status: em_execucao
    subfases:
      - id: F1.1
        titulo: ADR 0007 e specs da API pública, de uso e custos, do primeiro acesso e do acesso de superadmin
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-12
        concluida_em: 2026-10-12
        commit: acbb83e
      - id: F1.2
        titulo: Migração 0017 (chaves de API, custo e canal por resposta) com RLS
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-12
        concluida_em: 2026-10-12
        commit: null
  - id: F2
    titulo: Servidor
    status: em_execucao
    subfases:
      - id: F2.1
        titulo: Setup que cria o primeiro workspace e superadmin entrando num workspace como admin auditado
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F2.2
        titulo: Preços de modelos de chat, custo por resposta e as consultas de uso e custos e dos painéis
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F2.3
        titulo: Chaves de API e a API REST de conversa autenticada por chave
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F2.4
        titulo: API compatível com OpenAI (/v1/models e /v1/chat/completions)
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F2.5
        titulo: Ações e listagens que faltam no backend (reindexar fonte, sincronizar a coleção, duplicar assistente, busca e ordenação)
        status: em_execucao
        agente: claude-code-worktree
        iniciada_em: 2026-10-12
        concluida_em: null
        commit: null
  - id: F3
    titulo: Painel
    status: pendente
    subfases:
      - id: F3.1
        titulo: Primeiro acesso com workspace, Início com painel e primeiros passos, painel da instância e entrar no workspace
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F3.2
        titulo: Tela de uso e custos
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F3.3
        titulo: Tela de chaves de API com exemplos
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F3.4
        titulo: Melhorias nas telas existentes (busca, filtros, paginação, ações novas e estados vazios)
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
  - id: F4
    titulo: Entrega
    status: pendente
    subfases:
      - id: F4.1
        titulo: E2E da stack, guias (primeiro acesso, usar a API), README, CHANGELOG e AGENTS raiz
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
decisoes:
  - id: D1
    data: 2026-10-12
    por: usuario
    decisao: "A configuração inicial pede também o nome do primeiro workspace e deixa o superadmin como owner dele; ao entrar, ele cai no Início do workspace"
    motivo: "no primeiro acesso o superadmin via só a Administração e precisava de convite pelo Mailpit para chegar ao workspace"
    alternativas: "manter o fluxo e só guiar na Administração"
    adr: null
  - id: D2
    data: 2026-10-12
    por: usuario
    decisao: "Entram neste lote: Início com painel e checklist de primeiros passos; uso e custos; melhorias nas telas existentes; acesso por API; painel da instância e entrar num workspace pela administração. Pipelines e Canais continuam como placeholders"
    motivo: "tornar o painel utilizável para administrar e usar a plataforma"
    alternativas: "esconder Pipelines e Canais; construir um canal agora"
    adr: null
  - id: D3
    data: 2026-10-12
    por: usuario
    decisao: "API pública com chaves por workspace (mostradas uma vez, escopo opcional por assistente): REST própria de conversa e compatível com OpenAI (/v1/models e /v1/chat/completions, cada assistente como modelo, streaming SSE, citações num campo extra)"
    motivo: "decisão D14 da visão; integrar o KnoBridge em outros sistemas e em clientes que falam o protocolo OpenAI"
    alternativas: "só OpenAI; só REST"
    adr: docs/adr/0007-chaves-e-api-publica.md
  - id: D4
    data: 2026-10-12
    por: usuario
    decisao: "Custo do chat em US$ estimado por uma tabela de preços de modelos de chat (com os principais e sobrescrevível por variável de ambiente, como a de embeddings), gravado por resposta; modelo sem preço aparece só com tokens"
    motivo: "uso e custos precisam do chat e dos embeddings no mesmo lugar"
    alternativas: "custo devolvido pelo provedor; só tokens"
    adr: null
  - id: D5
    data: 2026-10-12
    por: usuario
    decisao: "O superadmin entra em qualquer workspace pela administração com papel admin efetivo, sem virar membro, com faixa de acesso de superadmin no topo e auditoria no workspace e na instância"
    motivo: "administrar a instância sem precisar de convite"
    alternativas: "como owner; somente leitura"
    adr: null
  - id: D6
    data: 2026-10-12
    por: agente
    decisao: "Chaves de API no padrão já usado nos tokens de runner e de envio (kbk_<8>_<urlsafe32>, só o SHA-256 guardado, busca por prefixo, revogação imediata); criar e revogar exige owner ou admin; a API pública usa o escopo do workspace da chave (RLS) e nunca a sessão do painel"
    motivo: "mesmo padrão validado duas vezes; credencial tratada como credencial"
    alternativas: "OAuth client credentials; chave por usuário"
    adr: docs/adr/0007-chaves-e-api-publica.md
  - id: D7
    data: 2026-10-12
    por: agente
    decisao: "Cada resposta grava o canal de origem (panel ou api) e o custo estimado; uso e custos e os painéis são consultas agregadas sobre runs e messages, sem tabela de métricas nova"
    motivo: "os dados já existem; agregação no Postgres basta para o volume atual"
    alternativas: "tabela de métricas diárias materializada"
    adr: null
  - id: D8
    data: 2026-10-12
    por: agente
    decisao: "F1.1: contrato do lote em api-publica.md, uso-e-custos.md e nas specs de autenticação, chat, chat-sse, indexação e runner, com ADR 0007; a migração 0017 também traz conversations.user_id opcional, conversations.api_key_id e o canal api, e sessions.superadmin_workspace_id/superadmin_entered_at; acesso de superadmin por sessão, um workspace por vez, papel efetivo = maior entre o do membership e admin; conversas da API pertencem à chave; /v1/chat/completions aceita nome ou id do assistente, cria uma conversa por chamada, ignora system/developer, usa as 10 últimas mensagens como histórico e acrescenta Fontes ao texto por padrão (knobridge.append_sources desliga); reindexar zera cursor e content_hash e recusa fontes tickets (bruto apagado, 409 source_reindex_unsupported); duplicar assistente copia a URL do webhook mas não o segredo; listas ganham query, filtros e sort; preços de chat em USD por milhão (input/output), os da OpenAI conferidos na F2.2 pelo catálogo público do OpenRouter"
    motivo: "detalhes de contrato que o plano não fixava, revisados pelo orquestrador"
    alternativas: "chave com escopo obrigatório; conversa da API ligada a um usuário; reindexar tickets reenviando a caixa"
    adr: null
  - id: D9
    data: 2026-10-12
    por: agente
    decisao: "F1.2: chave com conversas não pode ser apagada (FK sem ação; chaves só são revogadas); conversations com CHECK de dono único (user_id ou api_key_id) e api_key_id só no canal api; assistant_ids uuid[] de 1 a 100 sem FK (ids do workspace pela aplicação, assistente excluído sai do escopo); messages.cost_usd numeric(12,6) só em respostas; messages.channel com padrão panel; sessions.superadmin_workspace_id ON DELETE SET NULL; downgrade da 0017 recusa com conversas da API; conversas da API ficam fora das leituras do painel (404 no detalhe, fora da lista administrativa) até a F2.3"
    motivo: "integridade do dono da conversa e do histórico"
    alternativas: "SET NULL ou CASCADE na chave"
    adr: null
pendencias_usuario: []
---

# Plano 0008 — Telas para usar e administrar a plataforma

## 1. Pedido original

> "Acessei a interface WEB e tinha poucos menus e ações disponiveis pelos menus, crie as telas necessarias para administrar e utilizar a plataforma de forma satisfatoria"

## 2. Entendimento (perguntas e respostas)

| # | Pergunta | Resposta | Data |
|---|---|---|---|
| 1 | O que você viu ao entrar? | Só a área de Administração (superadmin sem workspace) | 2026-10-12 |
| 2 | Quais áreas entram? | Início com painel e primeiros passos; uso e custos; melhorias nas telas existentes; acesso por API | 2026-10-12 |
| 3 | Pipelines e Canais (placeholders)? | Manter como estão | 2026-10-12 |
| 4 | Algo para o superadmin? | Painel da instância; entrar num workspace pela administração | 2026-10-12 |
| 5 | Primeiro acesso | O setup cria o primeiro workspace | 2026-10-12 |
| 6 | API | REST própria e compatível com OpenAI | 2026-10-12 |
| 7 | Custo do chat | Tokens e custo estimado por tabela de preços | 2026-10-12 |
| 8 | Superadmin entra no workspace como | Admin, auditado | 2026-10-12 |

**O que será feito**:
- **Primeiro acesso:** a configuração inicial cria o primeiro workspace, e o superadmin entra direto no **Início**.
- **Início:** painel com documentos, fontes, execuções com falha, conversas, feedback e custo do mês, e um checklist de primeiros passos (provedor → coleção → fonte → assistente → chat), cada item levando à tela certa.
- **Uso e custos:** tokens e US$ de embeddings, por fonte e coleção, e de chat, por assistente e canal, no período, com exportação CSV.
- **Chaves de API:** criar, escopo por assistente e revogar, com exemplos para a API REST e para o SDK da OpenAI.
- **API pública:** REST de conversa e compatível com OpenAI.
- **Administração da instância:** painel com workspaces, usuários ativos, falhas recentes, saúde dos serviços e uso total, e um atalho "Entrar" em cada workspace, como admin auditado.
- **Telas existentes:**
  - busca, filtros, ordenação e paginação nas listas;
  - ações novas: reindexar fonte, sincronizar todas as fontes de uma coleção, duplicar assistente, sair de todas as sessões;
  - estados vazios que orientam o próximo passo.

**Fora do escopo**: canvas de pipelines e canais (Slack, Google Chat, widget, MCP), que continuam como placeholders (D2); limite de requisições por chave, cotas e cobrança; métricas materializadas (D7).

## 3. Critérios de aceite

- [ ] Instância nova: a configuração inicial pede o nome do workspace, e o superadmin entra direto no Início, com o checklist e todos os menus do seu papel. Sem convite pelo Mailpit.
- [ ] O Início mostra os números do workspace e o checklist reflete o que já existe; o superadmin vê o painel da instância e entra em qualquer workspace como admin, com faixa no topo e auditoria.
- [ ] Uso e custos mostra tokens e custo de embeddings e de chat no período, com filtros e CSV; respostas guardam custo estimado e canal.
- [ ] Com uma chave criada no painel, o SDK oficial da OpenAI conversa com um assistente (com e sem streaming) e recebe as citações num campo extra; a API REST cria conversa e pergunta; sem fonte, a resposta segue a regra 8.
- [ ] As listas principais têm busca, filtros e paginação; as ações novas funcionam e são auditadas quando mudam algo.
- [ ] E2E da stack cobre o primeiro acesso, o checklist, a chave de API com o SDK da OpenAI (provedor `fake`) e o uso e custos; guias, README (início rápido sem convite), CHANGELOG e `AGENTS.md` atualizados.
- [ ] Cobertura ≥ 95% em cada pacote tocado; isolamento entre workspaces testado em toda consulta nova.

## 4. Fases e subfases

Convenções para todas as subfases: código em inglês, docs em pt-BR; regras 1 a 10 do `AGENTS.md` raiz; a suíte padrão não chama LLM nem rede externa (provedor `fake`). Os agentes não editam `backend/AGENTS.md`, `backend/src/knobridge/AGENTS.md` nem o `AGENTS.md` raiz: relatam o texto e o orquestrador insere (exceto F4.1, que edita o raiz). Backend, frontend e E2E rodam um de cada vez, porque a máquina tem pouca memória. Telas seguem os padrões existentes (shadcn/ui, TanStack Query, cliente gerado do OpenAPI, i18n pt-BR, datas e números pelos utilitários existentes).

### F1 — Contrato e modelo de dados

#### F1.1 — ADR 0007 e specs

- **Objetivo**: decidir a autenticação da API pública e escrever os contratos do lote.
- **Entregáveis**:
  - `docs/adr/0007-chaves-e-api-publica.md` (D3, D6); linha na tabela da seção 9 da visão (ajustando a D14).
  - `docs/specs/api-publica.md`:
    - chaves `kbk_` e escopo por assistente;
    - REST de conversa (criar conversa, perguntar com resposta JSON ou SSE, ler conversa);
    - `/v1/models` e `/v1/chat/completions` (mapeamento de mensagens, histórico, streaming, campo extra de citações, regra 8, erros no formato OpenAI);
    - limites e auditoria.
  - Nas specs existentes:
    - `autenticacao.md`: setup com workspace e acesso de superadmin;
    - `chat.md`: custo e canal por resposta;
    - nova seção de uso e custos (consultas, agregações, CSV, painel do workspace e da instância) no lugar que couber (`indexacao.md`/`chat.md`, ou uma spec curta `uso-e-custos.md`).
- **Contexto necessário**: `AGENTS.md` raiz (seções 2, 7 e 9) e `docs/AGENTS.md`; visão (seções 6 a 9); `docs/adr/0006-chamados-por-push.md` (formato); `docs/specs/autenticacao.md`, `chat.md`, `chat-sse.md`, `indexacao.md`, `runner.md` (padrão de token) e `modelo-de-dados.md`.
- **Critérios de aceite**: contratos completos para as subfases seguintes (rotas, schemas, códigos de erro, papéis); links válidos; checagens de `AGENTS.md` e de planos verdes.
- **Depende de**: nenhuma.
- **Tamanho**: médio.

#### F1.2 — Migração 0017

- **Objetivo**: dados do lote com RLS.
- **Entregáveis**:
  - tabela `api_keys` (workspace, nome, prefixo único na instância, hash, `assistant_ids` opcional, criada por, `last_used_at`, `revoked_at`);
  - em `messages`: `cost_usd` e `channel` (`panel`, `api`);
  - em `conversations`: `user_id` opcional, `api_key_id` e o canal `api` (conversa feita pela API pertence à chave);
  - em `sessions`: `superadmin_workspace_id` e `superadmin_entered_at` (acesso de superadmin marcado na sessão; D8);
  - modelos, migração `0017` e `modelo-de-dados.md` v0.9.
- **Contexto necessário**: `backend/AGENTS.md`; AGENTS de `migrations/`, `conversations/`, `tickets/` (padrão de token) e `tests/`; migrações `0016`; `docs/specs/api-publica.md` (F1.1).
- **Critérios de aceite**: RLS como dono e não dono, prefixo único, `CHECK`s, `upgrade`/`downgrade` testados.
- **Depende de**: F1.1.
- **Tamanho**: pequeno.

### F2 — Servidor

#### F2.1 — Primeiro acesso com workspace e acesso de superadmin

- **Objetivo**: o superadmin cai num workspace e entra em qualquer outro.
- **Entregáveis**:
  - `POST /v1/setup` com o nome do workspace, que cria o workspace e o membership owner na mesma transação;
  - `POST /v1/admin/workspaces/{id}/enter` (ou equivalente da spec), que dá ao superadmin papel admin efetivo naquele workspace sem membership, com marca na sessão e auditoria no workspace e na instância;
  - `GET /v1/me` diz quando o acesso é de superadmin;
  - testes de RLS e de papéis.
- **Contexto necessário**: AGENTS de `tenancy/`, `security/`, `api/` e `audit/`; `tenancy/setup.py`, `api/deps.py` (`workspace_context`, `require_role`); `docs/specs/autenticacao.md`.
- **Critérios de aceite**: setup cria o workspace; o superadmin entra, age como admin e sai; um não superadmin recebe 403; tudo auditado; o isolamento continua testado.
- **Depende de**: F1.1.
- **Tamanho**: médio.

#### F2.2 — Custos do chat, uso e custos e painéis

- **Objetivo**: números para o Início, para Uso e custos e para o painel da instância.
- **Entregáveis**:
  - `llm/chat_pricing.py`, com os preços dos principais modelos e `KNOBRIDGE_CHAT_PRICES` para sobrescrever;
  - custo e canal gravados em cada resposta;
  - rotas de uso e custos (período, agrupamentos, CSV) e de painel do workspace;
  - painel da instância para o superadmin: contagens, falhas recentes, uso total e saúde de API, worker, Temporal e banco.
- **Contexto necessário**: AGENTS de `llm/`, `conversations/`, `ingestion/` e `api/`; `llm/pricing.py`; `conversations/chat.py` e `stats.py`; `ingestion/index_queries.py`; spec de uso e custos (F1.1).
- **Critérios de aceite**: custo por resposta (modelo sem preço → `null`); agregações corretas por período e grupo; CSV; número constante de consultas; isolamento entre workspaces; papéis.
- **Depende de**: F1.2.
- **Tamanho**: médio.

#### F2.3 — Chaves de API e REST de conversa

- **Objetivo**: acesso programático.
- **Entregáveis**:
  - CRUD de chaves (owner/admin, mostrada uma vez, revogar, auditado);
  - autenticação `Authorization: Bearer kbk_...` em modo de sistema pelo prefixo, com 401 único;
  - rotas REST de conversa da spec, com resposta JSON ou SSE, reaproveitando a rodada de chat existente com `channel=api`, escopo por assistente e regra 8.
- **Contexto necessário**: AGENTS de `api/`, `conversations/`, `tickets/` e `audit/`; `tickets/tokens.py` e `api/ingest.py` (padrão de token); `conversations/chat.py` e `turn.py`; `docs/specs/api-publica.md`.
- **Critérios de aceite**: chave mostrada uma vez; revogada vale na hora; escopo por assistente; regra 8; 401/403/404 conforme a spec; chave nunca em log; isolamento entre workspaces.
- **Depende de**: F1.2.
- **Tamanho**: médio.

#### F2.4 — API compatível com OpenAI

- **Objetivo**: clientes OpenAI falando com os assistentes.
- **Entregáveis**:
  - `/v1/models` (assistentes ativos dentro do escopo da chave);
  - `/v1/chat/completions` com e sem `stream`: histórico das mensagens como contexto, recuperação pela última mensagem do usuário, citações num campo extra (`knobridge.citations`), regra 8, uso de tokens, erros no formato OpenAI;
  - testes com o SDK oficial `openai` apontado para o app de teste.
- **Contexto necessário**: os da F2.3 e `docs/specs/api-publica.md`.
- **Critérios de aceite**:
  - o SDK `openai` recebe resposta com e sem streaming;
  - citações aparecem no campo extra;
  - sem fonte, a resposta segue a regra 8;
  - modelo fora do escopo ou inexistente devolve o erro da spec.
- **Depende de**: F2.3.
- **Tamanho**: médio.

#### F2.5 — Ações e listagens

- **Objetivo**: o backend das melhorias de tela.
- **Entregáveis**:
  - **reindexar fonte**: zera cursor e hashes da fonte e dispara a sincronização, que reprocessa tudo;
  - **sincronizar todas as fontes de uma coleção**;
  - **duplicar assistente**;
  - busca por texto e ordenação nas listagens que ainda não têm (assistentes, provedores, fontes, coleções, membros, runners), com paginação onde faltar;
  - auditoria das ações.
- **Contexto necessário**: AGENTS de `api/`, `ingestion/` e `assistants/`; `ingestion/sync.py` e `sources.py`; `assistants/service.py`; rotas de listagem existentes.
- **Critérios de aceite**: reindexar reprocessa todos os documentos (com teste no workflow de ingestão); papéis; isolamento entre workspaces; número constante de consultas nas listagens.
- **Depende de**: F1.1.
- **Tamanho**: médio.

### F3 — Painel

#### F3.1 — Primeiro acesso, Início e administração

- **Entregáveis**:
  - campo do workspace na configuração inicial;
  - Início com os cartões do painel e o checklist de primeiros passos, que esconde os itens feitos e leva a cada tela;
  - painel da instância na Administração;
  - "Entrar" na lista de workspaces da administração e a faixa "acesso de superadmin" com "Sair".
- **Contexto necessário**: `frontend/AGENTS.md`; `app/HomePage.tsx`, `app/shell/`, `features/auth` (setup) e `features/admin`; tipos gerados.
- **Critérios de aceite**: testes do setup, do painel, do checklist (estados), do painel da instância, do entrar e sair e dos papéis; cobertura ≥ 95%.
- **Depende de**: F2.1, F2.2.
- **Tamanho**: médio.

#### F3.2 — Uso e custos

- **Entregáveis**: área **Uso e custos** (owner/admin) com período, agrupamentos, totais, tabela e gráfico simples, e exportação CSV.
- **Contexto necessário**: `frontend/AGENTS.md`; `app/shell/navItems.ts`; tipos gerados.
- **Critérios de aceite**: testes de filtros, totais, modelo sem preço, CSV e papéis.
- **Depende de**: F2.2.
- **Tamanho**: pequeno.

#### F3.3 — Chaves de API

- **Entregáveis**: área **Chaves de API** (owner/admin) para criar com escopo por assistente, ver o token uma vez, revogar e ver o último uso, com exemplos copiáveis (`curl` da REST, Python e JavaScript com o SDK da OpenAI, `base_url` com `window.location.origin`).
- **Contexto necessário**: `frontend/AGENTS.md`; `features/runners` e `features/sources/tickets` (padrão de token mostrado uma vez); tipos gerados.
- **Critérios de aceite**: testes de criar, token mostrado uma vez, revogar, escopo, exemplos sem o token embutido e papéis.
- **Depende de**: F2.3, F2.4.
- **Tamanho**: pequeno.

#### F3.4 — Melhorias nas telas existentes

- **Entregáveis**:
  - busca, filtros, ordenação e paginação nas listas de assistentes, provedores, fontes, coleções, membros e runners;
  - botões **Reindexar** na fonte, **Sincronizar todas** na coleção e **Duplicar** no assistente;
  - **Sair de todas as sessões** na Segurança da conta (`POST /v1/auth/logout-all`);
  - estados vazios com o próximo passo e link;
  - confirmações nas ações destrutivas que ainda não pedem.
- **Contexto necessário**: `frontend/AGENTS.md` e os AGENTS das features tocadas; tipos gerados.
- **Critérios de aceite**: testes de cada ação e de cada lista (busca, filtro, página); cobertura ≥ 95%.
- **Depende de**: F2.5.
- **Tamanho**: médio.

### F4 — Entrega

#### F4.1 — E2E, guias e documentação

- **Entregáveis**:
  - E2E da stack:
    - primeiro acesso sem convite, Início com o checklist;
    - chave de API criada no painel e usada pelo SDK `openai` (Node) contra o assistente com provedor `fake`, com e sem stream, vendo as citações;
    - uso e custos com a resposta contada.
  - `docs/guias/usar-a-api.md`;
  - atualizações em `primeiro-acesso.md`, no início rápido do README (sem convite), no CHANGELOG e nas seções 1 e 12 do `AGENTS.md` raiz;
  - nota em `.env.example` sobre `KNOBRIDGE_CHAT_PRICES`.
- **Contexto necessário**: `frontend/e2e/stack/`; guias existentes; README.
- **Critérios de aceite**: E2E verde duas vezes seguidas; guia revisado pelo orquestrador; checagens verdes.
- **Depende de**: F3.1 a F3.4.
- **Tamanho**: médio.

## 5. Decisões

D1 a D5 vêm das respostas do usuário; D6 e D7 são do agente.

## 6. Pendências do usuário

Nenhuma.

## 7. Registro de andamento

- 2026-10-12 — plano criado; aguardando aprovação.
- 2026-10-12 — plano aprovado pelo usuário ("Aprovado"); F1.1 iniciada (agente em worktree).
- 2026-10-12 — F1.1 concluída: ADR 0007, specs api-publica.md e uso-e-custos.md e atualizações em autenticação, chat, chat-sse, indexação, runner e visão v0.5; links e checagens verdes
- 2026-10-12 — F1.2 iniciada (agente em worktree).
- 2026-10-12 — F2.5 iniciada (agente em worktree).
- 2026-10-12 — F1.2 concluída: migração 0017 com api_keys, dono do tipo chave em conversations, custo e canal por resposta e acesso de superadmin em sessions, RLS e testes; gates do agente: backend 2130 passed com 99,87%, frontend 1240; orquestrador: ruff, pyright e AGENTS na integração

## 8. Encerramento

A preencher ao concluir.
