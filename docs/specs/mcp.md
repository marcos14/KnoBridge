# Servidor MCP

> Rascunho v0.1 · 2026-10-14 · Plano 0010 (F1.1; implementação nas F2.1 e F2.2)

Contrato do servidor MCP do KnoBridge: transporte, autenticação, as cinco ferramentas (`list_products`, `search_knowledge`, `get_document`, `ask` e `open_ticket`) com entrada, saída, erros e limites, o formato das citações, como o nível é escolhido e a configuração nos clientes. A decisão de arquitetura está no [ADR 0009](../adr/0009-canais-mcp-e-widget.md); as escolhas do usuário, no [plano 0010](../planos/0010-canais-mcp-e-widget.md) (D2 e D6).

O MCP reaproveita o que já existe: a chave `kbk_` e o escopo dela ([api-publica.md](api-publica.md#chave-de-api)), produtos e níveis ([produtos-e-niveis.md](produtos-e-niveis.md)), a busca híbrida com o filtro de nível ([indexacao.md](indexacao.md), [chat.md](chat.md#recuperação-de-fontes)), a rodada de chat ([chat.md](chat.md#orquestração-em-duas-fases)), as citações ([chat-sse.md](chat-sse.md#citations)) e o pedido de chamado ([chamados.md](chamados.md#abrir-chamado-webhook-de-saída)).

Código: `backend/src/knobridge/mcp/` (servidor, invólucro de autenticação, ferramentas e esquemas; F2.1; `ask` e `open_ticket` em `mcp/answers.py`, F2.2), a montagem em `backend/src/knobridge/api/mcp_channel.py` e o lifespan em `api/app.py`. Tela: a seção MCP da tela de Chaves de API (`frontend/src/features/apikeys/`, F4.3).

## Transporte

| Item | Valor |
|---|---|
| Endpoint | `POST https://<instância>/v1/mcp` (com e sem barra final, **sem redirecionamento**: muitos clientes não repetem um `POST` depois de um 307). |
| Transporte | [Streamable HTTP](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports#streamable-http) **sem estado**: sem `Mcp-Session-Id`, cada requisição é independente, qualquer réplica da API atende. |
| Resposta | JSON (`application/json`), sem stream SSE. `GET /v1/mcp` (stream de notificações do servidor) responde 405. |
| SDK | Pacote oficial [`mcp`](https://pypi.org/project/mcp/) para Python, **versão alvo 2.x** (`mcp>=2.2,<3` no `pyproject.toml`; 2.3.0 era a mais recente em 2026-10-14, publicada em 2026-10-02). Na v2, o antigo `FastMCP` se chama `MCPServer` (`from mcp.server.mcpserver import MCPServer, Context`). Quem implementa confere a API na versão que entrar no `uv.lock`. |
| Protocolo | O que o SDK negocia: a revisão 2026-07-28 (sem handshake) e os clientes da era 2025 (com `initialize`), no mesmo endpoint. |
| Servidor | `MCPServer("knobridge", instructions=…)` (nome explícito; a v2 mudou o padrão), versão = `knobridge.__version__`. Só ferramentas: sem resources, prompts, sampling nem elicitation. |

**Montagem** (F2.1):

- `streamable_http_app(stateless_http=True, json_response=True, streamable_http_path="/")`, montado em `/v1/mcp`. Na v2, essas opções ficam no `streamable_http_app()`, não no construtor.
- O `lifespan` da API entra em `mcp_server.session_manager.run()` (um sub-app montado não roda o próprio lifespan; sem isso, a primeira chamada falha com "Task group is not initialized").
- **Proteção de host do SDK** (`TransportSecuritySettings`): por padrão o SDK só aceita `Host` localhost e responde 421 atrás de um nome real. `allowed_hosts` vem de `KNOBRIDGE_MCP_ALLOWED_HOSTS` (lista separada por vírgula); vazia (padrão), vale o host de `KNOBRIDGE_PUBLIC_BASE_URL` com e sem porta, mais `localhost:*` e `127.0.0.1:*`. `allowed_origins` vem de `KNOBRIDGE_MCP_ALLOWED_ORIGINS` (abaixo).
- **Corpo**: o `BodyLimitMiddleware` limita `/v1/mcp` a **64 KiB** (413 `payload_too_large` no formato do KnoBridge), antes do limite de 4 MiB do SDK.
- `/v1/mcp` fica **fora do OpenAPI** (`include_in_schema=False`): o contrato é este documento.

## Autenticação

Um invólucro ASGI na frente do app do SDK (`mcp/auth.py`) roda **antes** de qualquer mensagem MCP:

1. **`Origin`**: requisição com header `Origin` só segue se a origem (esquema, host e porta, comparados sem diferenciar maiúsculas) estiver em `KNOBRIDGE_MCP_ALLOWED_ORIGINS` (lista separada por vírgula, **vazia por padrão**); senão, 403 `origin_not_allowed`. Sem `Origin` (o caso dos clientes de IDE e CLI), segue. É a proteção contra DNS rebinding pedida pela especificação do MCP.
2. **Chave**: `Authorization: Bearer kbk_…`, verificada por `apikeys.auth.authenticate_api_key`, exatamente como na API pública ([api-publica.md](api-publica.md#autenticação)): chave ausente, malformada, desconhecida ou revogada → 401 `invalid_api_key` com `WWW-Authenticate: Bearer`; workspace suspenso → 403 `workspace_suspended`. Erros no formato único do KnoBridge (`{"error": {"code", "message", "details"}}`), em HTTP, sem corpo JSON-RPC.
3. **`last_used_at`**: `apikeys.auth.touch_last_used`, como na API pública (no máximo uma escrita por minuto).
4. **Identidade para as ferramentas**: o invólucro guarda a `ApiKeyIdentity` numa `ContextVar` (`mcp/context.py: current_identity()`), lida pelas ferramentas. Um teste com o cliente HTTP do SDK prova que a identidade chega à ferramenta no modo sem estado e que duas chaves em requisições simultâneas não se misturam. As ferramentas abrem a própria sessão com `scoped_session(workspace_id=identidade.workspace_id)`, sem `app.user_id`, e toda consulta roda com a RLS do workspace da chave.

A sessão do painel (cookie) não abre o MCP; a chave não abre o painel ([ADR 0007](../adr/0007-chaves-e-api-publica.md), item 5). Sem OAuth nesta versão (D2): o MCP não entra como conector no claude.ai nem no ChatGPT.

## Produto e nível

- **Produto**: argumento `product` (texto, 1 a 200 caracteres) com o **id** (uuid) ou o **nome exato** do produto (diferencia maiúsculas). Se o valor é um uuid de um produto visível, o id vence; senão, o nome. É a mesma resolução da parte `<produto>` do `model` da API compatível com OpenAI (`apikeys/products.py`), sem o sufixo de nível. Produto inexistente, inativo ou fora do escopo da chave → `not_found` (nunca `forbidden`: a chave não descobre o que não pode usar).
- **Nível**: argumento opcional `level` (`end_user`, `support` ou `product_dev`). **Sem nível, vale o `max_level` da chave** (mesma regra da API pública; [Chaves: escopo e nível máximo](api-publica.md#chaves-escopo-e-nível-máximo)). Acima do `max_level` → `level_not_allowed` com `details: {requested_level, max_level, reason: "api_key"}`. O MCP não é canal público: o teto é o da chave.
- O nível decide as fontes **no SQL da busca** ([O filtro na busca](produtos-e-niveis.md#o-filtro-na-busca)): um trecho acima do nível nunca sai em `search_knowledge`, `get_document` nem `ask`.

## Ferramentas

Cada ferramenta declara `input_schema` e `output_schema` (JSON Schema gerados dos modelos Pydantic de `mcp/schemas.py`). O SDK devolve o resultado em `structured_content` e o mesmo JSON como texto em `content`. Campos desconhecidos na entrada são ignorados. Textos das descrições em pt-BR, como abaixo (as instruções do servidor também).

**Instruções do servidor** (`instructions`):

> KnoBridge responde dúvidas sobre os produtos da empresa a partir de fontes indexadas (documentação, código, chamados e cards). Use `list_products` para saber os produtos e níveis que esta chave alcança. Prefira `search_knowledge` (sem custo de LLM) e responda só com base nos trechos, citando cada afirmação com a fonte. Se nada for encontrado, diga que não sabe; não invente. Use `ask` para uma resposta pronta do KnoBridge e `open_ticket` para abrir um chamado a partir de uma resposta de `ask`.

### Erros das ferramentas

Erros de domínio (produto, nível, validação de regra, provedor) voltam como **resultado de erro da ferramenta**, para o modelo do cliente ver: `CallToolResult(is_error=True)`, com `structured_content` e o texto em `content` iguais a:

```json
{"error": {"code": "level_not_allowed", "message": "The level is above the maximum allowed.", "details": {"requested_level": "product_dev", "max_level": "support", "reason": "api_key"}}}
```

`code`, `message` (sempre nossa, em inglês, nunca o texto do provedor) e `details` seguem o formato único da API. Argumentos fora do esquema (tipo errado, tamanho fora do limite, campo obrigatório ausente) também viram resultado de erro com `code: "validation_error"` e `details` = `[{loc, problem}]`. Falha inesperada: `chat_failed` (em `ask`) ou `internal_error` (nas demais), com o log só pelo tipo da exceção. Erros de autenticação nunca chegam aqui: saem em HTTP, antes (seção anterior).

Códigos por ferramenta:

| `code` | Ferramentas | Quando |
|---|---|---|
| `validation_error` | todas | Argumento inválido. |
| `not_found` | todas menos `list_products` | Produto, documento, conversa ou mensagem que a chave não vê. |
| `level_not_allowed` | `search_knowledge`, `get_document`, `ask` | Nível acima do `max_level` da chave. |
| `level_not_configured` | `ask` | O nível não tem credencial e modelo no workspace (`details.level`). `search_knowledge` e `get_document` não exigem nível configurado: não chamam o LLM. |
| `product_inactive` | `ask`, `open_ticket` | Produto desativado depois de criada a conversa (conversa continuada ou pedido de chamado). |
| `provider_*`, `embedding_*` | `search_knowledge`, `ask` | Provedor de embedding ou de LLM falhou (códigos de `llm/errors.py`, `details: {provider, status}`; em `ask` com a mensagem já gravada, também `message_id` e `conversation_id`). |
| `ticket_webhook_not_configured`, `ticket_request_exists` | `open_ticket` | Como em [chamados.md](chamados.md#pedido-no-chat). |

### `list_products`

> Lista os produtos que esta chave pode consultar, com os níveis de resposta permitidos em cada um e o nível usado quando nenhum é informado.

Entrada: `{}` (sem argumentos).

Saída:

```json
{
  "max_level": "support",
  "products": [
    {
      "id": "6f1c…",
      "name": "ERP",
      "description": "Dúvidas do ERP",
      "levels": ["end_user", "support"],
      "default_level": "support",
      "ticket_enabled": true
    }
  ],
  "truncated": false
}
```

- Produtos **ativos** do escopo da chave, por nome (como `GET /v1/models`); até 200 (`truncated: true` se houver mais; sem paginação, o número de produtos de um workspace é pequeno).
- `levels`: de `end_user` até o `max_level` da chave, em ordem. `default_level` = `max_level`.
- `ticket_enabled`: o produto tem o webhook de chamados configurado (URL e segredo).
- Sem custo, sem embedding. Uma consulta para os produtos, uma para os webhooks (número constante de statements).

### `search_knowledge`

> Busca trechos das fontes de um produto (documentação, código, chamados, cards), só no nível permitido, sem gerar resposta. Responda a partir dos trechos e cite as fontes. Se `results` vier vazio, diga que não encontrou a informação.

Entrada:

| Campo | Tipo | Regras |
|---|---|---|
| `product` | texto | Obrigatório. Id ou nome ([Produto e nível](#produto-e-nível)). |
| `query` | texto | Obrigatório, 1 a 2000 caracteres depois de tirar os espaços das pontas. |
| `level` | `end_user`, `support`, `product_dev` | Opcional; padrão o `max_level` da chave. |
| `limit` | inteiro | Opcional, 1 a 20, padrão 8. |

Comportamento:

1. Resolve o produto e confere o nível (erros acima), **antes** de qualquer embedding.
2. Produto sem coleção: `results: []`, sem chamar o embedding (como o `HybridRetriever`).
3. `SearchService.search` nas coleções do produto, com o `min_similarity` do produto, o nível pedido e `limit`. Os dois braços filtram `chunks.min_level` no SQL.
4. Cada acerto vira uma fonte com `retrieval/context.py: source_from_hit` e uma citação com `conversations/retrieval.py: citation(index, source, with_evidence=level != end_user)`, a mesma função das respostas do chat. **Sem** o corte por orçamento de contexto do chat (`fit_to_budget`): o `limit` já limita.

Saída:

```json
{
  "product_id": "6f1c…",
  "product_name": "ERP",
  "level": "support",
  "results": [
    {
      "index": 1,
      "content": "Chamado 48213 · Resolvido · 2026-09-30 · seção Solução\nReinicie o serviço de caixa…",
      "content_truncated": false,
      "score": 0.0325,
      "citation": {"index": 1, "title": "Erro 4021 ao fechar o caixa", "uri": "ticket:48213", "snippet": "…", "document_id": "…", "kind": "ticket", "ticket_number": "48213", "ticket_status": "resolved", "…": "…"}
    }
  ],
  "note": null
}
```

- `content`: o corpo do trecho sem o cabeçalho de embedding (o `content` da fonte), precedido do `context_line` em chamado e card (a mesma linha que o LLM do chat recebe), cortado em **4000 caracteres** (`content_truncated`).
- `score`: o `fused_score` do RRF, só para ordenar; não é probabilidade.
- `citation`: exatamente o objeto de citação de [chat-sse.md](chat-sse.md#citations), com `index` igual ao do resultado. No nível `end_user`, `evidence` é `null`.
- `note`: com `results` vazio, o texto fixo "Nenhuma fonte encontrada para esta pergunta neste produto e nível. Não responda sem fonte; diga que não sabe e, se fizer sentido, use ask e open_ticket para abrir um chamado." (regra 8 do `AGENTS.md`, aplicada a quem usa a ferramenta); com resultados, `null`.
- **Não chama o LLM.** O custo é só o embedding da consulta, que não é gravado por consulta (como o "testar busca" do painel). Nada é gravado em `conversations` nem `messages`.

### `get_document`

> Lê o conteúdo de um documento citado por `search_knowledge` ou `ask` (pelo `document_id` da citação), só nas partes permitidas ao nível. Use `next_offset` para continuar documentos longos.

Entrada:

| Campo | Tipo | Regras |
|---|---|---|
| `product` | texto | Obrigatório. O documento tem de estar numa coleção do produto. |
| `document_id` | uuid | Obrigatório, o `document_id` de uma citação. |
| `level` | nível | Opcional; padrão o `max_level` da chave. |
| `offset` | inteiro | Opcional, ≥ 0, padrão 0: a posição do primeiro trecho a devolver (o `next_offset` da chamada anterior). |
| `max_chars` | inteiro | Opcional, 1000 a 50 000, padrão 20 000: soma máxima de `content` das partes devolvidas. |

Comportamento:

1. Resolve o produto e confere o nível.
2. O documento é visível se existe no workspace e **ao menos um trecho dele** está numa coleção do produto (`chunks.collection_id` ∈ coleções do produto) com `chunks.min_level` permitido ao nível (o mesmo `levels_up_to` da busca). Senão → `not_found` (documento acima do nível e documento inexistente respondem igual).
3. Lê os trechos permitidos do documento com `position >= offset`, por `position`, no SQL (o filtro de nível na consulta, nunca depois), até somar `max_chars`. Um trecho que sozinho passa de `max_chars` sai cortado (`truncated: true`); os seguintes ficam para a próxima chamada. Trechos acima do nível são pulados sem aviso.
4. `next_offset`: a `position` do próximo trecho permitido, ou `null` quando acabou. Número constante de statements (produto, documento com a checagem e trechos).

Saída:

```json
{
  "product_id": "6f1c…",
  "level": "end_user",
  "document": {"id": "…", "kind": "file", "title": "manual/caixa.md", "uri": "manual/caixa.md", "language": "markdown"},
  "citation": {"index": 1, "title": "manual/caixa.md", "uri": "manual/caixa.md#L1-L40", "…": "…"},
  "parts": [
    {"position": 0, "start_line": 1, "end_line": 40, "symbol": null, "content": "# Fechamento do caixa\n…", "truncated": false}
  ],
  "next_offset": 3
}
```

- `document`: `id`, `kind` (`file`, `commit`, `knowledge`, `ticket`, `card`), `title`, `uri` e `language` da tabela `documents`.
- `citation`: a citação do **primeiro trecho devolvido**, no formato de [chat-sse.md](chat-sse.md#citations) (`index` 1), para o cliente citar o documento com número, status e link de chamado e card. Sem partes (offset além do fim), `citation: null` e `parts: []`.
- `content` de cada parte: o corpo sem o cabeçalho de embedding (`chunks.meta.display`), como no chat. No nível `end_user`, a seção de evidências de um item de conhecimento (nível `support`) nunca aparece, porque o trecho dela é filtrado.
- Não chama o LLM nem o embedding.

### `ask`

> Faz uma pergunta ao KnoBridge sobre um produto e devolve a resposta pronta, com citações, no nível pedido. Tem custo de LLM. Sem fonte, a resposta diz que não sabe; nesse caso, ofereça open_ticket com o message_id.

Entrada:

| Campo | Tipo | Regras |
|---|---|---|
| `product` | texto | Obrigatório. |
| `question` | texto | Obrigatório, 1 a 8000 caracteres depois de tirar os espaços das pontas. |
| `level` | nível | Opcional; padrão o `max_level` da chave. Numa conversa continuada, se informado, tem de ser o nível da conversa (senão, `validation_error` com `details: [{loc: ["level"], problem: "conversation_level"}]`). |
| `conversation_id` | uuid | Opcional: continua uma conversa **desta chave com `channel = mcp`** e do mesmo produto (senão, `not_found`). Sem ele, cria uma conversa nova. |

Comportamento:

- Sem `conversation_id`: cria a conversa da chave como a REST própria ([api-publica.md](api-publica.md#post-v1conversations)), mas com **`channel = mcp`**, `api_key_id` = a chave e `user_id` nulo, título pela pergunta. Com `conversation_id`: usa a conversa existente, com o histórico das 10 mensagens mais recentes ([chat.md](chat.md#histórico-enviado-ao-llm)).
- A rodada é a do painel e da API (`ChatService` com o `ApiKeyReader` da chave, consumida inteira, como a REST com `stream: false`): checagens (`product_inactive`, `level_not_allowed`, `level_not_configured`), busca com o filtro de nível, regra 8 (sem fonte, sem LLM, a `no_source_message` do produto), gravação das mensagens com `channel = mcp`, `product_id`, `level` e `cost_usd`.
- Falha do provedor durante a geração: a mensagem fica `failed` (como no painel) e a ferramenta devolve erro com o código do provedor e `details` com `message_id` e `conversation_id`.

Saída:

```json
{
  "conversation_id": "…",
  "message_id": "…",
  "product_id": "6f1c…",
  "product_name": "ERP",
  "level": "support",
  "status": "completed",
  "answer": "Para fechar o caixa, … [1]",
  "citations": [{"index": 1, "title": "src/caixa/fechamento.ts", "uri": "src/caixa/fechamento.ts#L10-L42", "…": "…"}],
  "ticket_enabled": true,
  "model": "gpt-4.1-mini",
  "cost_usd": 0.000427
}
```

- `status`: `completed` ou `no_source`. Em `no_source`, `citations: []`, `answer` = a mensagem de "sem fonte" do produto, `model` e `cost_usd` nulos.
- `citations`: formato de [chat-sse.md](chat-sse.md#citations), as mesmas gravadas na mensagem.
- `ticket_enabled`: o produto oferece abrir chamado (o mesmo `ticket_requests_enabled` do chat).

### `open_ticket`

> Abre um chamado para a equipe do produto a partir de uma resposta de ask (pelo message_id), quando o KnoBridge não soube responder ou a resposta não resolveu. Informe um resumo do problema e o e-mail de quem pede.

Entrada:

| Campo | Tipo | Regras |
|---|---|---|
| `message_id` | uuid | Obrigatório: uma resposta de `ask` desta chave (mensagem `assistant` de uma conversa da chave com `channel = mcp`), com status `completed` ou `no_source`. Outra mensagem da chave: `validation_error`; mensagem que a chave não vê: `not_found`. |
| `summary` | texto | Obrigatório, 1 a 2000 caracteres: o resumo que o destino recebe. **O KnoBridge não gera o resumo** (sem LLM nesta ferramenta): quem chama escreve. |
| `requester_email` | texto | Obrigatório, e-mail válido, até 320 caracteres: para o destino responder a quem pediu. |
| `requester_name` | texto | Opcional, 1 a 200 caracteres. Ausente: o e-mail ocupa `requester.name` no payload. |

Comportamento: cria o pedido de chamado da mensagem como no painel ([Pedido no chat](chamados.md#pedido-no-chat)), com o mesmo payload, assinatura, workflow de entrega e retentativas, e as diferenças de [Pedidos vindos do MCP e do widget](chamados.md#pedidos-vindos-do-mcp-e-do-widget): `user_id` nulo no pedido, `channel: "mcp"` e `requester` com os dados informados e `verified: false`. Erros: `ticket_webhook_not_configured`, `ticket_request_exists` (`details.ticket_request_id`), `product_inactive`, `not_found`, `validation_error`.

Saída (o pedido fica `pending` e é entregue em segundo plano):

```json
{"ticket_request_id": "…", "status": "pending", "conversation_id": "…", "message_id": "…"}
```

Não há ferramenta para acompanhar o pedido nesta versão; owner e admin veem o pedido na conversa, em **Conversas**.

## Citações

Toda citação que sai do MCP (`search_knowledge`, `get_document`, `ask`) é o objeto de [chat-sse.md](chat-sse.md#citations), gerado pela mesma função do chat (`conversations/retrieval.py: citation`): `index`, `title`, `uri`, `snippet`, `document_id`, `kind`, localização (`path`, `symbol`, `start_line`, `end_line`, `language`, `sha`, `author`, `date`) e os campos de conhecimento, chamado e card. No nível `end_user`, `evidence` é `null`. A regra 8 vale para o MCP assim: `ask` nunca responde sem fonte (o LLM não é chamado), e `search_knowledge` sem resultado traz a `note` que manda não responder sem fonte.

## Conversas, uso e custos

- `ask` grava conversas e mensagens com `channel = mcp` e `api_key_id` da chave ([modelo-de-dados.md](modelo-de-dados.md#conversations)). Elas aparecem na visão administrativa (**Conversas**, filtro de canal "MCP", "MCP · <nome da chave>" no lugar do usuário) e em Uso e custos (`group_by=channel` com a linha `mcp`; `group_by=api_key` conta as respostas dos canais `api` e `mcp`) ([uso-e-custos.md](uso-e-custos.md), [chat.md](chat.md#visão-administrativa)).
- As conversas do MCP **não** aparecem em `GET /v1/conversations/{id}` da REST própria (404): cada canal lê as suas. Elas só são continuadas por `ask` com `conversation_id`.
- `search_knowledge`, `get_document` e `list_products` não gravam nada e não entram em Uso e custos.
- Sem limite de requisições por chave nesta versão (como a API pública).

## Logs e auditoria

- Cada chamada de ferramenta loga `mcp_tool_called` com `tool`, `workspace_id`, `api_key_id`, `outcome` (`ok` ou o `code` do erro), `latency_ms` e, em `ask`, `conversation_id`. **Nunca** os argumentos (pergunta, consulta, resumo, e-mail) nem o conteúdo devolvido.
- O uso da chave não é auditado por requisição ([ADR 0007](../adr/0007-chaves-e-api-publica.md), item 6). `open_ticket` audita `ticket_request.created` como o painel, com `actor_user_id` nulo e `details.channel = "mcp"` ([chamados.md](chamados.md#pedidos-vindos-do-mcp-e-do-widget)).

## Limites

| Item | Limite |
|---|---|
| Corpo da requisição em `/v1/mcp` | 64 KiB (`BodyLimitMiddleware`) |
| `product` | 1 a 200 caracteres |
| `query` (`search_knowledge`) | 1 a 2000 caracteres |
| `limit` (`search_knowledge`) | 1 a 20, padrão 8 |
| `content` por resultado | 4000 caracteres |
| `max_chars` (`get_document`) | 1000 a 50 000, padrão 20 000 |
| `question` (`ask`) | 1 a 8000 caracteres |
| `summary` (`open_ticket`) | 1 a 2000 caracteres |
| Produtos em `list_products` | 200 |

## Variáveis de ambiente

| Variável | Padrão | Uso |
|---|---|---|
| `KNOBRIDGE_MCP_ALLOWED_ORIGINS` | vazia | Origens de navegador aceitas em `/v1/mcp` (separadas por vírgula, `https://host[:porta]`). Vazia: toda requisição com `Origin` é recusada (403). |
| `KNOBRIDGE_MCP_ALLOWED_HOSTS` | vazia | Valores de `Host` aceitos pela proteção do SDK (separados por vírgula; `host:*` aceita qualquer porta). Vazia: o host de `KNOBRIDGE_PUBLIC_BASE_URL`, `localhost:*` e `127.0.0.1:*`. |

Entram no `settings.py` e no `.env.example` na F2.1.

## Configuração nos clientes

O painel (seção MCP da tela de Chaves de API, F4.3) mostra estes exemplos com a origem da instância e a variável `KNOBRIDGE_API_KEY`, nunca a chave. A F4.3 confere a sintaxe na documentação de cada cliente na data da implementação.

Claude Code:

```sh
claude mcp add --transport http knobridge https://kb.empresa.com/v1/mcp \
  --header "Authorization: Bearer $KNOBRIDGE_API_KEY"
```

Cursor (`.cursor/mcp.json` do projeto ou `~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "knobridge": {
      "url": "https://kb.empresa.com/v1/mcp",
      "headers": {"Authorization": "Bearer ${env:KNOBRIDGE_API_KEY}"}
    }
  }
}
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.knobridge]
url = "https://kb.empresa.com/v1/mcp"
bearer_token_env_var = "KNOBRIDGE_API_KEY"
```

Uma chave por pessoa ou por máquina, com `max_level` de quem vai usar (o painel pré-seleciona `end_user`; desenvolvimento costuma usar `product_dev`).

## Testes previstos

- F2.1: com o cliente do SDK sobre HTTP em processo (`streamable_http_client` com um cliente HTTP sobre o app ASGI): chave ausente, inválida e revogada (401), workspace suspenso (403), `Origin` não permitido (403); `list_products` com escopo e `max_level`; um trecho acima do nível não sai em `search_knowledge` nem em `get_document` (Postgres real, nos dois braços da busca); produto fora do escopo → `not_found`; nenhuma chamada ao LLM (provedor fake que falha se chamado); isolamento entre workspaces; identidade por requisição sem mistura.
- F2.2: `ask` grava as mensagens com `channel = mcp`, o nível e o custo; `ask` sem fonte não chama o LLM; nível acima recusado; `open_ticket` chega ao webhook falso com `channel: "mcp"`; isolamento.

## Referências

- Especificação do MCP, transporte Streamable HTTP e segurança (validação de `Origin`): <https://modelcontextprotocol.io/specification/2025-11-25/basic/transports>
- SDK oficial Python (`mcp`): <https://github.com/modelcontextprotocol/python-sdk> e <https://pypi.org/project/mcp/>
- Documentação do SDK v2: montar num app ASGI (<https://py.sdk.modelcontextprotocol.io/run/asgi/>), migração da v1 (<https://py.sdk.modelcontextprotocol.io/migration/>), novidades da v2 (<https://py.sdk.modelcontextprotocol.io/whats-new/>), testes (<https://py.sdk.modelcontextprotocol.io/get-started/testing/>) e transportes do cliente (<https://py.sdk.modelcontextprotocol.io/client/transports/>)
- Claude Code, MCP: <https://docs.claude.com/en/docs/claude-code/mcp>
- Cursor, MCP: <https://docs.cursor.com/context/model-context-protocol>
- Codex, MCP: <https://github.com/openai/codex/blob/main/docs/config.md>
