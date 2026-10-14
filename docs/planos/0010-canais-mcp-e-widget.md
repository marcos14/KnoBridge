---
id: 0010
titulo: Canais MCP e widget — o KnoBridge no IDE da equipe e dentro do sistema do cliente
slug: canais-mcp-e-widget
solicitado_por: usuario
criado_em: 2026-10-14
atualizado_em: 2026-10-14
status: em_execucao
aprovado_em: 2026-10-14
aprovado_por: usuario
concluido_em: null
branch: plano/0010-canais-mcp-e-widget
fases:
  - id: F1
    titulo: Contrato
    status: concluida
    subfases:
      - id: F1.1
        titulo: ADR e specs do servidor MCP e do widget
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-14
        concluida_em: 2026-10-13
        commit: 6fc101b
  - id: F2
    titulo: Servidor MCP
    status: concluida
    subfases:
      - id: F2.1
        titulo: Servidor MCP com list_products, search_knowledge e get_document
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-14
        concluida_em: 2026-10-13
        commit: f0e349b
      - id: F2.2
        titulo: Ferramentas ask e open_ticket no MCP, canal mcp no uso e nas conversas
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-14
        concluida_em: 2026-10-13
        commit: 55e79a0
  - id: F3
    titulo: Backend do widget
    status: em_execucao
    subfases:
      - id: F3.1
        titulo: Chaves do widget, domínios, aparência, limite de requisições e configuração pública
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-14
        concluida_em: 2026-10-13
        commit: dac08f5
      - id: F3.2
        titulo: Conversa do widget (SSE, histórico do visitante, identidade assinada, feedback e chamado)
        status: concluida
        agente: claude-code-worktree
        iniciada_em: 2026-10-14
        concluida_em: 2026-10-13
        commit: null
  - id: F4
    titulo: Widget e painel
    status: pendente
    subfases:
      - id: F4.1
        titulo: Pacote widget com balão, modo embutido, streaming e citações
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F4.2
        titulo: Feedback, chamado e identidade no widget; build servido pelo compose e gate na CI
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F4.3
        titulo: Tela do widget no painel com prévia, MCP nas chaves e canais em Conversas e Uso
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
  - id: F5
    titulo: Validação e documentação
    status: pendente
    subfases:
      - id: F5.1
        titulo: E2E da stack, guias e documentação
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
      - id: F5.2
        titulo: Ensaio real com Claude Code via MCP e o widget no Minski
        status: pendente
        agente: null
        iniciada_em: null
        concluida_em: null
        commit: null
decisoes:
  - id: D1
    data: 2026-10-14
    por: usuario
    decisao: o lote é MCP e widget; o Slack fica para um lote próprio, junto com o Google Chat
    motivo: levar as respostas a quem pergunta (equipe no IDE, cliente no sistema), com o plano num tamanho executável
    alternativas: Slack neste lote; Slack no lugar do widget
    adr: null
  - id: D2
    data: 2026-10-14
    por: usuario
    decisao: o MCP oferece search_knowledge, get_document e open_ticket (da visão) mais ask e list_products, autenticado pela chave kbk_ (que define os produtos e o nível máximo); sem OAuth neste lote
    motivo: search_knowledge sem custo de LLM no KnoBridge (o modelo do IDE responde); ask para a resposta pronta do nível; list_products para o cliente saber o que alcança
    alternativas: só as três da visão; as três mais ask com OAuth para conector do claude.ai e do ChatGPT
    adr: null
  - id: D3
    data: 2026-10-14
    por: usuario
    decisao: widget com chave pública por produto (domínios permitidos e limite de requisições), visitante anônimo com histórico no navegador e identidade assinada opcional (HMAC do sistema hospedeiro) que grava nome e e-mail na conversa e no chamado
    motivo: serve site público e sistema logado com o mesmo componente
    alternativas: só anônimo; só usuário assinado
    adr: docs/adr/0009-canais-mcp-e-widget.md
  - id: D4
    data: 2026-10-14
    por: usuario
    decisao: o widget tem abrir chamado, feedback, modo embutido além do balão e uma tela de configuração com prévia no painel
    motivo: escolhas do usuário
    alternativas: só conversa com citações
    adr: null
  - id: D5
    data: 2026-10-14
    por: usuario
    decisao: o widget responde sempre em Usuário final, mesmo com identidade assinada
    motivo: regra do canal público do plano 0009; a equipe interna usa o painel, o MCP ou a API com chave; um segredo vazado não abre o código
    alternativas: identidade assinada podendo subir até um máximo da chave do widget (exigiria ADR mudando a regra do canal público)
    adr: null
  - id: D6
    data: 2026-10-14
    por: agente
    decisao: "decisões técnicas a confirmar no ADR da F1.1: MCP em Streamable HTTP sem estado no mesmo processo da API (/v1/mcp, SDK oficial Python); widget em Lit, empacotado num único JS servido pelo contêiner do frontend; chave pública kbp_ e segredo de assinatura kbs_ cifrado (AES-GCM, ADR 0003); acesso do visitante à própria conversa por um token de conversa (hash SHA-256) guardado no navegador; limite de requisições por chave e IP numa janela fixa no Postgres; canais mcp e widget em messages.channel"
    motivo: reaproveitar a rodada de chat, as chaves e a cifra existentes, sem serviço novo nem Redis
    alternativas: processo MCP separado; widget em Preact ou React; iframe; limite em memória por processo; Redis
    adr: docs/adr/0009-canais-mcp-e-widget.md
  - id: D7
    data: 2026-10-13
    por: agente
    decisao: "F1.1 (ADR 0009): MCP no processo da API em /v1/mcp, Streamable HTTP sem estado com resposta JSON, SDK mcp>=2.2,<3 (MCPServer), chave kbk_ validada por invólucro ASGI e passada às ferramentas por ContextVar, hosts permitidos por KNOBRIDGE_MCP_ALLOWED_HOSTS; widget em Lit, um JS IIFE servido pelo nginx do frontend em /widget/v1/knobridge-chat.js; chave pública kbp_ no caminho da URL (o preflight CORS não leva headers), segredo kbs_ cifrado, token de conversa kbv_ só em hash; identidade v1.<base64url>.<hmac hex> com sub, name, email, iat, exp (até 24 h, tolerância de 60 s), sem mudar o nível; limite em janela fixa no Postgres com a chave do contador em HMAC (IP não gravado), padrões 30 mensagens por IP por hora e 1000 por dia por widget (no painel) e 120 req/min, 20 conversas/h, 5 chamados/h (ambiente); duas migrações: 0020 na F2.2 (canal mcp, ticket_requests.user_id opcional) e 0021 na F3.1 (widget, limites, feedback.user_id opcional); e-mail obrigatório no open_ticket do MCP; excluir widget apaga as conversas dele; a prévia do painel cria conversas reais"
    motivo: "contrato implementável pelas subfases sem perguntas"
    alternativas: "uma migração única 0020; chave pública em header; FastMCP da v1"
    adr: null
  - id: D8
    data: 2026-10-13
    por: agente
    decisao: "ordem das migrações trocada: a do widget (F3.1) vira 0020 e a do canal mcp (F2.2) vira 0021, porque a F3.1 roda antes da F2.2; a F3.1 ajusta os números nas specs"
    motivo: "F2.1 e F3.1 em paralelo"
    alternativas: "esperar a F2.2 para numerar"
    adr: null
  - id: D9
    data: 2026-10-13
    por: agente
    decisao: "F2.1: MCP montado como duas Route do Starlette (/v1/mcp e /v1/mcp/), fora do OpenAPI e sem 307, um MCPServer por app; invólucro confere Origin (403 origin_not_allowed), método (405 fora do POST) e chave antes do SDK; hosts padrão = host de PUBLIC_BASE_URL, localhost:* e 127.0.0.1:*; argumentos validados pelos modelos Pydantic de mcp/schemas.py (erro validation_error como resultado de ferramenta); sem evento de auditoria por chamada, só last_used_at; get_document responde igual a inexistente para documento acima do nível; SDK mcp 2.3.0"
    motivo: "spec mcp.md e SDK v2"
    alternativas: "Mount com redirect; auditoria por chamada"
    adr: null
  - id: D10
    data: 2026-10-13
    por: agente
    decisao: "F3.1: migração 0020 (widgets, rate_limit_counters, canal widget e colunas de visitante em conversations, feedback.user_id opcional) e renomeia o CHECK de canal ck_conversations_ck_conversations_channel (prefixo duplo da 0017) para ck_conversations_channel, que a 0021 da F2.2 deve usar; downgrade recusa se houver widget, conversa widget ou feedback sem usuário; CORS das rotas /v1/widget/* fora do CORSMiddleware global, ecoando a origem aceita e sem credenciais, com a origem da instância sempre aceita; limitador grava o contador numa transação própria e conta as recusadas; PATCH com extra=forbid"
    motivo: "contrato da F1.1"
    alternativas: "CORS global com lista dinâmica"
    adr: null
  - id: D11
    data: 2026-10-13
    por: agente
    decisao: "F2.2: migração 0021 (mcp nos CHECKs de canal, chave dona em api e mcp, ticket_requests.user_id opcional; downgrade recusa dados mcp); o canal fica num campo do ApiKeyReader (padrão api; o MCP usa channel=mcp) e get_key_conversation filtra por ele, então REST, OpenAI e MCP só leem as próprias conversas; ask gerencia as próprias sessões (a fase 1 é commitada antes do stream); open_ticket inicia a entrega depois do commit, como o painel; o payload do chamado ganhou channel e requester.verified/external_id também no painel"
    motivo: "spec mcp.md e chamados.md"
    alternativas: "tabela de conversas por canal; canal como parâmetro solto"
    adr: null
  - id: D12
    data: 2026-10-13
    por: agente
    decisao: "F3.2: GET da conversa do widget devolve os campos da conversa no mesmo nível de messages e has_more (spec ajustada); pedido de chamado do visitante montado em widget/tickets.py reaproveitando constantes e funções de tickets/requests.py (requester.verified só com e-mail da identidade assinada, external_id = sub); teto do WidgetReader pelo canal público (pedido acima dá 403 reason public_channel); produto inativo vira 404 widget_unavailable; done do SSE sem modelo, tokens e custo para o visitante (custo segue gravado); limites de mensagem contados depois de validar corpo e conversa; respostas com Cache-Control no-store"
    motivo: "contrato widget.md"
    alternativas: "mudar chat.py para o canal widget"
    adr: null
pendencias_usuario: []
---

# Plano 0010 — Canais MCP e widget

## 1. Pedido original

> Gostei! Implemente o Lote 1

O Lote 1 foi a sugestão de próximo lote dada na conversa: **canais**, com o servidor MCP (a equipe consulta o KnoBridge de dentro do Claude Code, Cursor ou Codex, com produto e nível pela chave de API) e o widget embutível (o usuário final pergunta dentro do sistema de vocês, sempre no nível Usuário final), deixando o Slack para depois.

## 2. Entendimento (perguntas e respostas)

| # | Pergunta | Resposta | Data |
|---|---|---|---|
| 1 | O Slack entra neste lote? | Fica para depois. | 2026-10-14 |
| 2 | Ferramentas do MCP além de `search_knowledge`, `get_document` e `open_ticket`? | As três, mais `ask` e `list_products`, com a chave `kbk_`; sem OAuth. | 2026-10-14 |
| 3 | Como o widget identifica quem conversa? | Anônimo, com identidade assinada opcional pelo sistema hospedeiro. | 2026-10-14 |
| 4 | O que o widget faz além de conversar com citações? | Abrir chamado, feedback 👍/👎, modo embutido além do balão e tela de configuração com prévia no painel. | 2026-10-14 |
| 5 | Com identidade assinada, o widget pode responder acima de Usuário final? | Não: sempre Usuário final. | 2026-10-14 |

O que já estava decidido na visão (seção 7 e tabela de stack): MCP em Streamable HTTP com o SDK oficial Python; widget como Web Component em um único JS, sem iframe obrigatório, temável, com citações clicáveis (Lit ou Preact).

**Será feito**:
- **Servidor MCP** em `/v1/mcp`, autenticado pela chave `kbk_`:
  - `list_products`: os produtos e níveis que a chave alcança;
  - `search_knowledge`: trechos com citações no nível pedido, sem chamar o LLM;
  - `get_document`: o documento citado, respeitando produto e nível;
  - `ask`: a resposta pronta do nível, com citações;
  - `open_ticket`: abre chamado pelo webhook do produto.
- **Widget** (`widget/`, Web Component em Lit, um arquivo JS):
  - balão flutuante e modo embutido;
  - streaming com citações clicáveis, feedback e abrir chamado;
  - histórico no navegador e identidade assinada opcional;
  - sempre no nível Usuário final;
  - chave pública por produto com domínios permitidos e limite de requisições.
- **Painel**:
  - tela do widget com chave, domínios, aparência, trecho para copiar e prévia ao vivo;
  - instruções do MCP nas chaves de API;
  - os canais `mcp` e `widget` em Conversas e Uso e custos.
- **Validação e documentação**: E2E da stack, guias, e um ensaio real com o Claude Code via MCP e o widget no Minski.

**Fica de fora**: Slack e Google Chat; OAuth no MCP (conector do claude.ai e do ChatGPT); widget acima de Usuário final; anexos e voz no widget.

## 3. Critérios de aceite

- [ ] Com uma chave `kbk_`, o Claude Code conecta em `/v1/mcp` e usa as cinco ferramentas. Cada ferramenta respeita os produtos e o nível máximo da chave: um nível acima é recusado, e um trecho acima do nível nunca sai, provado por teste.
- [ ] `search_knowledge` não chama o LLM e devolve trechos com citações (arquivo, linhas, commit, chamado, card).
- [ ] Um site de teste embute o widget com uma linha de `<script>` e um elemento.
  - O visitante conversa com streaming e citações, avalia e abre chamado.
  - O histórico volta ao recarregar a página.
  - A resposta é sempre do nível Usuário final.
- [ ] O widget só aceita os domínios permitidos e para no limite de requisições (429). Uma identidade assinada inválida é recusada e uma válida aparece na conversa e no chamado.
- [ ] O painel configura o widget com prévia ao vivo e mostra os canais `mcp` e `widget` em Conversas e em Uso e custos.
- [ ] O E2E da stack cobre MCP e widget. O ensaio real tem relatório. A cobertura fica em 95% ou mais, com isolamento entre workspaces testado.

## 4. Fases e subfases

Convenções para todas as subfases:
- **Idioma:** código em inglês, docs em pt-BR.
- **Regras:** valem as regras 1 a 10 do `AGENTS.md` raiz. A suíte padrão não chama LLM nem rede externa.
- **`AGENTS.md` protegidos:** os agentes não editam `backend/AGENTS.md`, `backend/src/knobridge/AGENTS.md` nem o `AGENTS.md` raiz. Eles relatam o texto e o orquestrador insere. A exceção é a F5.1, que edita o raiz.
- **Ordem das suítes:** backend, frontend, widget e E2E rodam um de cada vez, por limite de memória.
- **Branch:** antes de cada commit, o orquestrador confere que está na branch do plano.

### F1 — Contrato

#### F1.1 — ADR e specs do servidor MCP e do widget

- **Objetivo**: fechar o contrato antes do código.
- **Entregáveis**:
  - `docs/adr/0009-canais-mcp-e-widget.md`, com as decisões D2 a D6;
  - `docs/specs/mcp.md`:
    - transporte e autenticação;
    - as cinco ferramentas com o esquema de entrada e saída, os erros e os limites de tamanho;
    - o formato das citações no resultado;
    - como o nível é escolhido (padrão = máximo da chave);
  - `docs/specs/widget.md`:
    - a chave pública `kbp_` e o segredo `kbs_`;
    - domínios permitidos e CORS;
    - limite de requisições;
    - as rotas públicas `/v1/widget/*`, com SSE e o token de conversa;
    - o formato da identidade assinada (campos, HMAC-SHA256, validade, relógio);
    - os atributos e eventos do elemento, a aparência e a acessibilidade;
    - privacidade (o que fica no navegador);
  - atualizações em:
    - `api-publica.md`, `chat.md` e `chat-sse.md` (canais `mcp` e `widget`);
    - `chamados.md` (chamado vindo do MCP e do widget);
    - `uso-e-custos.md`, `modelo-de-dados.md` (tabelas novas) e `autenticacao.md`, se couber;
    - a visão (seção 9 com o ADR).
- **Contexto necessário**:
  - visão (seções 5, 7, 8 e 9);
  - ADRs 0003, 0006, 0007 e 0008;
  - specs `api-publica.md`, `chat.md`, `chat-sse.md`, `chamados.md`, `produtos-e-niveis.md`, `uso-e-custos.md` e `modelo-de-dados.md`;
  - `docs/AGENTS.md`.
- **Critérios de aceite**: specs que um agente implementa sem perguntar; os exemplos de identidade assinada são reproduzíveis (segredo e assinatura de teste).
- **Depende de**: nenhuma.
- **Tamanho**: médio.

### F2 — Servidor MCP

#### F2.1 — Servidor MCP com list_products, search_knowledge e get_document

- **Objetivo**: um cliente MCP consulta o conhecimento no nível da chave, sem custo de LLM.
- **Entregáveis**:
  - `backend/src/knobridge/mcp/`, com `AGENTS.md`;
  - montagem em `api/app.py` (Streamable HTTP sem estado);
  - autenticação pela chave `kbk_` reaproveitando `apikeys/`;
  - as três ferramentas sobre `retrieval/` com o filtro de nível;
  - auditoria e último uso da chave;
  - dependência `mcp` (SDK oficial) no `uv.lock`;
  - testes com o cliente MCP do SDK, em processo.
- **Contexto necessário**:
  - `docs/specs/mcp.md`;
  - AGENTS de `apikeys/`, `retrieval/`, `levels/`, `products/` e `api/`;
  - `apikeys/products.py`.
- **Critérios de aceite**:
  - um trecho acima do nível não sai em `search_knowledge` nem em `get_document`, testado no Postgres real;
  - um produto fora da chave é recusado;
  - não há chamada ao LLM;
  - o workspace B não vê o A;
  - chave revogada ou ausente é recusada.
- **Depende de**: F1.1.
- **Tamanho**: médio.

#### F2.2 — Ferramentas ask e open_ticket no MCP, canal mcp no uso e nas conversas

- **Objetivo**: resposta pronta e chamado pelo MCP, contados como canal `mcp`.
- **Entregáveis**:
  - `ask` reaproveitando a rodada de chat (conversa da chave, `channel = mcp`, custo);
  - `open_ticket`: o pedido de chamado da conversa, pelo webhook do produto;
  - migração se o `CHECK` de canal exigir;
  - Uso e custos e a visão administrativa com o canal `mcp`;
  - testes.
- **Contexto necessário**:
  - `docs/specs/mcp.md`, `chat.md` e `chamados.md`;
  - AGENTS de `mcp/`, `apikeys/`, `conversations/`, `tickets/` e `usage/`.
- **Critérios de aceite**:
  - `ask` grava a mensagem com o canal `mcp` e o custo;
  - `open_ticket` chega ao webhook falso;
  - nível acima recusado;
  - isolamento.
- **Depende de**: F2.1.
- **Tamanho**: médio.

### F3 — Backend do widget

#### F3.1 — Chaves do widget, domínios, aparência, limite de requisições e configuração pública

- **Objetivo**: o owner ou admin cria o widget de um produto e o navegador do visitante lê a configuração pública.
- **Entregáveis**:
  - migração das tabelas do widget e do limite de requisições;
  - `backend/src/knobridge/widget/`, com `AGENTS.md`;
  - CRUD no painel (`/v1/workspaces/{id}/widgets`), com o segredo de assinatura mostrado uma vez e rotacionável;
  - rota pública de configuração com CORS pelo domínio permitido;
  - limite por chave e IP (429 com `Retry-After`);
  - auditoria;
  - testes de RLS e isolamento.
- **Contexto necessário**:
  - `docs/specs/widget.md`;
  - ADR 0003 (cifra);
  - AGENTS de `apikeys/`, `security/`, `products/`, `migrations/` e `api/`.
- **Critérios de aceite**:
  - domínio fora da lista recusado;
  - limite testado com relógio injetado;
  - o segredo nunca volta da API depois da criação;
  - workspace B não vê o widget do A.
- **Depende de**: F1.1.
- **Tamanho**: médio.

#### F3.2 — Conversa do widget (SSE, histórico do visitante, identidade assinada, feedback e chamado)

- **Objetivo**: o visitante conversa no nível Usuário final e só acessa a própria conversa.
- **Entregáveis**:
  - rotas públicas de conversa, mensagem (SSE), leitura, feedback e chamado;
  - token de conversa (hash) para o visitante;
  - verificação da identidade assinada (HMAC, validade, relógio injetado), com nome e e-mail na conversa e no chamado;
  - `channel = widget`, com o teto `end_user` de `levels/policy.py`;
  - Uso e custos e visão administrativa com o canal `widget`;
  - testes.
- **Contexto necessário**:
  - `docs/specs/widget.md`, `chat.md`, `chat-sse.md` e `chamados.md`;
  - AGENTS de `widget/`, `conversations/`, `tickets/`, `levels/` e `usage/`.
- **Critérios de aceite**:
  - sempre `end_user` (um pedido acima é ignorado ou recusado conforme a spec);
  - outro token não lê a conversa;
  - assinatura inválida ou vencida recusada;
  - o chamado leva nome e e-mail;
  - limite aplicado nas mensagens;
  - isolamento.
- **Depende de**: F3.1.
- **Tamanho**: médio.

### F4 — Widget e painel

#### F4.1 — Pacote widget com balão, modo embutido, streaming e citações

- **Objetivo**: o Web Component em um único JS.
- **Entregáveis**:
  - `widget/` (projeto pnpm, Lit, Vite em modo biblioteca, TypeScript strict, ESLint e Prettier, Vitest com 95%, `AGENTS.md` em cada pasta);
  - elemento `<knobridge-chat>` com os modos balão e embutido;
  - aparência por atributos e variáveis CSS;
  - cliente SSE com histórico no navegador;
  - citações clicáveis;
  - textos em pt-BR com i18n preparada;
  - acessibilidade (teclado, foco e ARIA);
  - a linha `widget/` em "Existe" na tabela do `AGENTS.md` raiz, que fica para o orquestrador.
- **Contexto necessário**:
  - `docs/specs/widget.md` e `chat-sse.md`;
  - `frontend/AGENTS.md` (como referência de convenções);
  - a raiz do `AGENTS.md`, seções 4 a 6.
- **Critérios de aceite**:
  - testes de render, streaming, citações, histórico e modos;
  - build em um arquivo, com o tamanho medido no relatório.
- **Depende de**: F3.2.
- **Tamanho**: médio.

#### F4.2 — Feedback, chamado e identidade no widget; build servido pelo compose e gate na CI

- **Objetivo**: completar o widget e publicá-lo pela instância.
- **Entregáveis**:
  - feedback e abrir chamado (com e-mail quando anônimo);
  - atributo de identidade assinada;
  - o build do widget servido pelo contêiner do frontend (Dockerfile) num caminho estável;
  - job do widget na CI (lint, typecheck, testes com cobertura, build);
  - `.pre-commit-config.yaml` se couber.
- **Contexto necessário**:
  - `docs/specs/widget.md`;
  - `widget/AGENTS.md`;
  - `frontend/Dockerfile`, `.github/workflows/ci.yml` e `deploy/AGENTS.md`.
- **Critérios de aceite**: testes das telas de feedback e chamado; o compose serve o arquivo; a CI tem o gate.
- **Depende de**: F4.1.
- **Tamanho**: médio.

#### F4.3 — Tela do widget no painel com prévia, MCP nas chaves e canais em Conversas e Uso

- **Objetivo**: configurar sem ler a spec.
- **Entregáveis**:
  - `frontend/src/features/widget/` (lista por produto; criar e editar com domínios, aparência, saudação e modo; segredo mostrado uma vez e rotação; trecho para copiar; prévia ao vivo carregando o widget servido pela instância);
  - na tela de Chaves de API, a aba ou seção MCP com os comandos para Claude Code, Cursor e Codex;
  - Conversas e Uso e custos com os canais `mcp` e `widget`;
  - cliente gerado.
- **Contexto necessário**:
  - `frontend/AGENTS.md`;
  - `features/apikeys`, `features/conversations` e `features/usage`;
  - specs `widget.md` e `mcp.md`;
  - tipos gerados.
- **Critérios de aceite**: testes de cada tela e de cada papel; a prévia testada com o elemento simulado.
- **Depende de**: F2.2, F3.2, F4.2.
- **Tamanho**: médio.

### F5 — Validação e documentação

#### F5.1 — E2E da stack, guias e documentação

- **Entregáveis**:
  - **E2E da stack**:
    - MCP com o cliente oficial do SDK em TypeScript (`search_knowledge` sem custo, `ask` com citação, nível acima recusado);
    - widget numa página de teste (domínio permitido; conversa com citação; feedback; chamado no webhook falso; histórico ao recarregar; domínio não permitido recusado).
  - **Guias**: `docs/guias/conectar-pelo-mcp.md` e `docs/guias/embutir-o-widget.md`.
  - **Documentação geral**: README, CHANGELOG e as seções 1, 4 e 12 do `AGENTS.md` raiz.
- **Contexto necessário**: `frontend/e2e/stack/`, os guias e as specs do plano.
- **Critérios de aceite**: E2E verde duas vezes seguidas; guias revisados pelo orquestrador.
- **Depende de**: F4.3.
- **Tamanho**: médio.

#### F5.2 — Ensaio real com Claude Code via MCP e o widget no Minski

- **Entregáveis**:
  - na stack `knobridge-minski`, uma chave Desenvolvimento e produto conectada ao Claude Code por MCP:
    - os cenários da visão ("já tivemos chamado sobre…", "onde está a regra…") e perguntas dos ensaios anteriores;
    - comparação entre `search_knowledge` (o modelo do IDE responde) e `ask` (o KnoBridge responde) em qualidade, tempo e custo;
  - o widget numa página local no nível Usuário final;
  - correções com teste;
  - relatório `docs/pesquisa/0006-mcp-e-widget-no-minski.md`, só com métricas, perguntas e conclusões.
- **Contexto necessário**: orquestrador; `docs/pesquisa/0005`.
- **Critérios de aceite**: relatório com a comparação e o gasto; nada do Minski no repositório.
- **Depende de**: F5.1.
- **Tamanho**: médio.

## 5. Decisões

As decisões D1 a D5 são do usuário (seção 2). A D6 reúne as escolhas técnicas que o ADR 0009 da F1.1 confirma ou corrige.

## 6. Pendências do usuário

Nenhuma.

## 7. Registro de andamento

- 2026-10-14 — plano criado na branch `plano/0010-canais-mcp-e-widget` (a partir de `main`); aguardando aprovação.
- 2026-10-14 — plano aprovado pelo usuário ("Aprovado"); F1.1 iniciada (agente em worktree).
- 2026-10-13 — F1.1 concluída: ADR 0009, specs mcp.md e widget.md e atualizações em api-publica, chat, chat-sse, chamados, uso-e-custos, modelo-de-dados, autenticacao, produtos-e-niveis e visão; links e âncoras conferidos por script; assinatura de exemplo conferida em Python e Node
- 2026-10-14 — F2.1 iniciada (agente em worktree).
- 2026-10-14 — F3.1 iniciada (agente em worktree).
- 2026-10-13 — F2.1 concluída: servidor MCP em /v1/mcp com list_products, search_knowledge e get_document no nível da chave e sem LLM; gates do agente: backend 2775 passed com 99,89%; orquestrador: ruff, pyright e AGENTS na integração
- 2026-10-13 — F3.1 concluída: chaves do widget por produto, origens, aparência, limites, configuração pública com CORS próprio e limitador no Postgres, integrada sobre a F2.1; backend 2971 passed com 99%, frontend 1579
- 2026-10-14 — F2.2 iniciada (agente em worktree).
- 2026-10-14 — F3.2 iniciada (agente em worktree).
- 2026-10-13 — F2.2 concluída: ask e open_ticket no MCP, canal mcp em Uso e custos e na visão administrativa, migração 0021; gates do agente: backend 3005 passed com 99,87%, frontend 1579; orquestrador: ruff, pyright e AGENTS na integração
- 2026-10-13 — F3.2 concluída: conversa do widget (SSE, token kbv_, identidade assinada, sempre end_user, feedback e chamado, limites, 413 com CORS, canal widget no uso e na visão administrativa), integrada sobre a F2.2; backend 3098 passed + 1 teste ajustado ao canal mcp (34 passed na reexecução), cobertura 99%; frontend 1579

## 8. Encerramento

A preencher ao concluir.
