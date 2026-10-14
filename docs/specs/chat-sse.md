# Chat em streaming (SSE)

> Rascunho v0.10 · 2026-10-14 · Plano 0002, F4.4 (v0.1; v0.2, F4.5: resposta `streaming` órfã lida como `interrupted`; v0.3, plano 0003 F4.2: campos de localização nas citações e erros do provedor de embedding antes do stream; v0.4, plano 0003 F6.1: autor e data nas citações de commit; v0.5, plano 0004 F2.4: citação de item de conhecimento com confiança e evidências; v0.6, plano 0005 F1.1: citação de chamado, implementada na F2.3; v0.7, plano 0005 F3.2: `ticket_requests_enabled` no `done`; v0.8, plano 0008 F1.1: `cost_usd` no `done`; v0.9, plano 0009 F1.1: produto e nível no `citations`, citação de card; v0.10, plano 0010 F1.1: os mesmos eventos no widget)
>
> **Mudanças da v0.10** (plano 0010, F1.1; implementação na F3.2): os mesmos eventos servem à conversa do **widget** (`POST /v1/widget/{public_key}/conversations/{id}/messages`, [widget.md](widget.md)), com o `done` sem modelo, tokens e custo e o `ticket_requests_enabled` do widget ([No canal widget](#no-canal-widget)). O MCP não usa SSE: `ask` devolve a resposta inteira, com as mesmas citações ([mcp.md](mcp.md#ask)).
>
> **Mudanças da v0.9** (plano 0009, F1.1; implementada nas F2.2 e F2.3): a conversa é de um **produto** num **nível** ([produtos-e-niveis.md](produtos-e-niveis.md)). O evento `citations` traz `product_id` e `level`; citação `kind: card` com `card_number`, `card_type`, `card_status`, `card_sprint` e `card_date_kind` (`null` fora de `card`; [cards.md](cards.md#citação-kind-card)); citação `kind: knowledge` no nível `end_user` vai com `evidence: null`; erros antes do stream: 403 `level_not_allowed`, 409 `level_not_configured` e 409 `product_inactive` (no lugar de `assistant_inactive`). Campos aditivos; respostas gravadas antes vêm com os campos de card `null`. `ticket_requests_enabled` passa a vir do webhook do produto.
>
> **Mudanças da v0.8** (plano 0008, F1.1; implementada na F2.2): o evento `done` traz `cost_usd`, o custo estimado da resposta ([chat.md](chat.md#custo-e-canal-por-resposta)). Campo aditivo. Os mesmos eventos servem à REST própria da API pública com `stream: true` ([api-publica.md](api-publica.md#post-v1conversationsconversation_idmessages)).
>
> **Mudanças da v0.7** (plano 0005, F3.2): o evento `done` traz `ticket_requests_enabled`, que diz se o assistente oferece abrir chamado ([chamados.md](chamados.md#pedido-no-chat)). Campo aditivo.
>
> **Mudanças da v0.6** (plano 0005, F1.1; implementada na F2.3): citação `kind: ticket` com número, status, data e link do chamado ([chamados.md](chamados.md#citação-kind-ticket)). Toda citação passa a trazer `ticket_number`, `ticket_status`, `ticket_date_kind` e `url` (`null` fora de `ticket`); respostas gravadas antes vêm sem eles, lidos como `null`.

Contrato da resposta de `POST /v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages`, que manda uma pergunta sobre o produto da conversa, no nível dela, e devolve a resposta como [Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html). Os schemas das rotas JSON (conversas, mensagens, feedback) estão no [`openapi.json`](openapi.json); lá, esta rota aparece com `200` em `text/event-stream`, e os eventos são descritos aqui. O comportamento do chat além do fio (regra de citações, `Retriever`, fases da rodada, histórico, feedback e visão administrativa) está em [chat.md](chat.md). Implementação em [`backend/src/knobridge/conversations/`](../../backend/src/knobridge/conversations/AGENTS.md) e [`backend/src/knobridge/api/conversations.py`](../../backend/src/knobridge/api/AGENTS.md).

## Requisição

- Sessão do painel (cookie) e header CSRF, como toda rota não segura.
- Corpo JSON: `{"content": "pergunta"}` (1 a 8000 caracteres, sem espaços nas pontas).
- Só o dono da conversa envia mensagens. Owner e admin do workspace leem conversas de outros membros, mas recebem 403 `forbidden` ao tentar enviar; quem não pode ler recebe 404 `not_found`.

Antes do primeiro byte do stream, a pergunta e o ponto de partida da resposta já foram gravados e confirmados (commit). Por isso, erros de acesso e de estado saem como JSON comum, no formato único de erro, e não como evento:

| Status | `code` | Quando |
|---|---|---|
| 401 | `unauthenticated` | Sem sessão viva. |
| 403 | `forbidden`, `csrf_failed`, `workspace_suspended` | Não é o dono, CSRF ausente ou workspace suspenso. |
| 403 | `level_not_allowed` | O nível da conversa ficou acima do máximo atual de quem pergunta no produto (v0.9; `details: {requested_level, max_level, reason}`). |
| 404 | `not_found` | Conversa inexistente, de outro workspace ou de outro membro (para quem não é owner/admin). |
| 409 | `product_inactive` | O produto da conversa foi desativado (v0.9; até a v0.8, `assistant_inactive`). |
| 409 | `level_not_configured` | O nível da conversa não tem credencial e modelo no workspace (v0.9; `details: {level}`). |
| 422 | `validation_error` | Corpo inválido (pergunta vazia ou longa demais). |
| 422, 429, 502, 503 | `provider_*`, `embedding_*` | O provedor de embedding da coleção falhou ao vetorizar a pergunta (desde a v0.3; códigos de `llm/errors.py`, `details: {provider, status}`). Nada é gravado: a pergunta pode ser reenviada. |

## Formato no fio

Resposta `200` com `Content-Type: text/event-stream`, `Cache-Control: no-cache` e `X-Accel-Buffering: no`. Cada evento tem uma linha `event:` com o nome e uma linha `data:` com um objeto JSON (UTF-8, numa linha só), seguidas de uma linha em branco:

```text
event: citations
data: {"message_id":"…","user_message_id":"…","product_id":"…","level":"support","citations":[…]}

event: delta
data: {"text":"Para fechar o caixa, "}

event: done
data: {"message_id":"…","status":"completed","model":"gpt-4.1-mini","input_tokens":812,"output_tokens":64,"cost_usd":0.000427,"latency_ms":2310,"ticket_requests_enabled":false}
```

Como a rota é `POST`, o cliente lê o corpo com `fetch` e um leitor de stream (o `EventSource` do navegador só faz `GET`). O servidor não manda `id:` nem `retry:`; não há retomada: se a conexão cair, o cliente recarrega a conversa por `GET .../conversations/{id}`.

## Sequência

Sempre nesta ordem:

1. Um `citations`.
2. Zero ou mais `delta`.
3. Exatamente um evento final: `done` ou `error`. Depois dele o stream termina.

## Eventos

### `citations`

| Campo | Tipo | Descrição |
|---|---|---|
| `message_id` | uuid | Id da mensagem do assistente desta resposta. |
| `user_message_id` | uuid | Id da mensagem com a pergunta. |
| `product_id` | uuid | Produto da conversa (v0.9). |
| `level` | `end_user`, `support` ou `product_dev` | Nível da conversa, que decidiu as fontes, as instruções e o modelo desta resposta (v0.9). |
| `citations` | lista | Fontes numeradas da resposta; vazia quando não há fonte. |

Cada citação:

| Campo | Tipo | Descrição |
|---|---|---|
| `index` | inteiro | A partir de 1, o mesmo `[n]` que a resposta usa no texto. |
| `title` | texto | Caminho do arquivo (`src/caixa/fechamento.ts`), título do commit, título do item de conhecimento ou título do chamado (v0.6, anonimizado). |
| `uri` | texto ou `null` | `<caminho>#L<início>-L<fim>` para texto e código com linhas, `<caminho>` sem linhas (documentos convertidos: PDF, DOCX…), `commit:<sha>`, `knowledge:<chave-do-item>` (v0.5), `ticket:<external_id>` (v0.6) ou `card:<external_id>` (v0.9). |
| `snippet` | texto | Até 300 caracteres do trecho, sem o cabeçalho de contexto usado no embedding. |
| `document_id` | texto ou `null` | Id do documento no índice. |
| `kind` | `file`, `commit`, `knowledge`, `ticket`, `card` ou `null` | Tipo do documento (v0.3; `knowledge` na v0.5: item de conhecimento de uma fonte `runner`, [harness.md](harness.md#no-índice-e-no-chat); `ticket` na v0.6: chamado de uma fonte `tickets`, [chamados.md](chamados.md#citação-kind-ticket); `card` na v0.9: card de uma fonte `cards`, [cards.md](cards.md#citação-kind-card)). |
| `path` | texto ou `null` | Caminho do arquivo; `null` em commit (v0.3). |
| `symbol` | texto ou `null` | Função, classe ou tipo do trecho de código, quando conhecido (v0.3). |
| `start_line`, `end_line` | inteiro ou `null` | Linhas do trecho, a partir de 1, inclusivas; `null` sem linhas (v0.3). |
| `language` | texto ou `null` | Linguagem detectada (ex.: `typescript`, `markdown`) (v0.3). |
| `sha` | texto ou `null` | SHA do commit; `null` em arquivo (v0.3). |
| `author` | texto ou `null` | Nome do autor do commit (nunca o e-mail); `null` em arquivo (v0.4). |
| `date` | texto ou `null` | Data de autoria do commit em ISO 8601, como o repositório informou (ex.: `2026-10-01T10:00:00-03:00`); `null` em arquivo (v0.4). Em `ticket` (v0.6): `resolved_at` do chamado, se houver, senão `updated_at`, em ISO 8601 UTC com `Z`; `ticket_date_kind` diz qual. |
| `confidence` | `inferido`, `revisado` ou `null` | Selo de confiança do item de conhecimento (`revisado` depois de aprovado na revisão); `null` fora de `knowledge` (v0.5). |
| `evidence` | lista ou `null` | Só em `knowledge` (v0.5): onde o item foi verificado no código, `[{path, start_line, end_line, symbol, excerpt}]` (linhas a partir de 1; `symbol` e `excerpt` podem ser `null`, o excerto quando desligado na fonte ou omitido por arquivo sensível). São as evidências que o trecho citado usa (até 10). `null` nos demais tipos. Desde a v0.9, também `null` em toda resposta no nível `end_user`, porque as evidências trazem caminhos e excertos de código. |
| `ticket_number` | texto ou `null` | Só em `ticket` (v0.6): número do chamado no sistema de origem (`number`), ou o `external_id` quando ele não tem número. `null` nos demais tipos. |
| `ticket_status` | `open`, `pending`, `resolved`, `closed` ou `null` | Só em `ticket` (v0.6): status normalizado do chamado. O painel mostra em pt-BR (Aberto, Pendente, Resolvido, Fechado). `null` nos demais tipos. |
| `ticket_date_kind` | `resolved`, `updated` ou `null` | Só em `ticket` (v0.6): `resolved` quando `date` é a data de resolução, `updated` quando é a última atualização. `null` nos demais tipos. |
| `url` | texto ou `null` | Em `ticket` (v0.6) e `card` (v0.9): link do chamado ou do card no sistema de origem, quando a fonte enviou. O painel só o mostra como link se for `http` ou `https`. `null` nos demais tipos e sem link. |
| `card_number` | texto ou `null` | Só em `card` (v0.9): número do card (`number`), ou o `external_id` sem ele. |
| `card_type` | `feature`, `bug`, `task`, `story`, `epic`, `other` ou `null` | Só em `card` (v0.9): tipo normalizado. O painel mostra em pt-BR. |
| `card_status` | `backlog`, `in_progress`, `done`, `cancelled` ou `null` | Só em `card` (v0.9): status normalizado. O painel mostra em pt-BR (Backlog, Em andamento, Concluído, Cancelado). |
| `card_sprint` | texto ou `null` | Só em `card` (v0.9): nome da sprint, quando o card tem. |
| `card_date_kind` | `done`, `updated` ou `null` | Só em `card` (v0.9): `done` quando `date` é a data de conclusão, `updated` quando é a última atualização. |

Em `card`, `date` é `done_at` se houver, senão `updated_at`, em ISO 8601 UTC com `Z`.

Os campos marcados com v0.3, v0.4, v0.5, v0.6 e v0.9 são aditivos e compatíveis: respostas gravadas antes vêm com eles `null` em `GET .../conversations/{id}`, e commits indexados antes da v0.4 vêm sem `author` e `date` até serem reindexados. As mesmas citações ficam gravadas na mensagem (`citations` em `GET .../conversations/{id}`).

### `delta`

| Campo | Tipo | Descrição |
|---|---|---|
| `text` | texto | Próximo pedaço da resposta. Concatenar os `delta` na ordem dá o conteúdo completo. |

### `done`

| Campo | Tipo | Descrição |
|---|---|---|
| `message_id` | uuid | Id da mensagem do assistente. |
| `status` | `completed` ou `no_source` | `completed`: o LLM respondeu com base nas fontes. `no_source`: veja abaixo. |
| `model` | texto ou `null` | Modelo que respondeu; `null` em `no_source`. |
| `input_tokens`, `output_tokens` | inteiro ou `null` | Uso informado pelo provedor; `null` quando ele não informa e em `no_source`. |
| `cost_usd` | número ou `null` | Custo estimado em US$ (6 casas) pela tabela de preços de chat; `null` em `no_source`, sem tokens ou com modelo sem preço (v0.8; [chat.md](chat.md#custo-e-canal-por-resposta)). |
| `latency_ms` | inteiro | Do recebimento da pergunta ao fim da resposta (relógio do servidor). |
| `ticket_requests_enabled` | booleano | O produto oferece abrir chamado: o webhook de chamados dele tem URL e segredo (v0.7; desde a v0.9, o do produto; o mesmo valor de `ticket_requests_enabled` em `GET .../conversations/{id}`). O painel oferece o pedido nas respostas `no_source` ([chamados.md](chamados.md#pedido-no-chat)). |

### `error`

| Campo | Tipo | Descrição |
|---|---|---|
| `message_id` | uuid | Id da mensagem do assistente, gravada com `status: failed` e o `error_code`. |
| `status` | `failed` | |
| `error` | objeto | `{code, message, details}`, o mesmo formato dos erros da API. |

Códigos possíveis em `error.code`:

| `code` | Causa | `details` |
|---|---|---|
| `provider_auth_failed` | O provedor recusou a chave. | `{provider, status}` |
| `provider_rate_limited` | Limite de uso ou cota do provedor. | `{provider, status}` |
| `provider_unavailable` | Provedor fora do ar, timeout, erro 5xx ou erro no meio do stream sem tipo conhecido. | `{provider, status}` |
| `provider_request_failed` | O provedor recusou o pedido (modelo inexistente, parâmetro inválido). | `{provider, status}` |
| `chat_failed` | Falha inesperada no servidor. | `null` |

`status` em `details` é o HTTP do provedor, ou `null` quando o erro chegou no meio do stream (o HTTP já era 200) ou sem resposta. A mensagem é sempre nossa: nunca repete o texto do provedor, que pode ecoar parte da chave. Os `delta` enviados antes do erro ficam gravados como conteúdo parcial da mensagem.

## Sem fonte (regra 8)

Quando a recuperação não encontra nenhuma fonte (o produto não tem coleção, ou nenhum trecho permitido ao nível da conversa alcança a similaridade mínima do produto nem casa a busca textual), o LLM **não é chamado**. A resposta é a mensagem de "sem fonte" configurada no produto (por padrão, diz que não sabe e oferece abrir um chamado):

```text
event: citations
data: {"message_id":"…","user_message_id":"…","product_id":"…","level":"end_user","citations":[]}

event: delta
data: {"text":"Não encontrei essa informação nas fontes que tenho disponíveis, …"}

event: done
data: {"message_id":"…","status":"no_source","model":null,"input_tokens":null,"output_tokens":null,"cost_usd":null,"latency_ms":3,"ticket_requests_enabled":true}
```

A mensagem fica gravada com `status: no_source` e `citations: []`. O painel usa esse status para mostrar a oferta de abrir chamado, que usa o webhook de saída do produto quando ele está configurado ([chamados.md](chamados.md#abrir-chamado-webhook-de-saída)).

## No canal widget

Desde a v0.10, a rota de mensagens do widget ([widget.md](widget.md#post-conversationsconversation_idmessages)) devolve exatamente estes eventos, na mesma ordem, com estas diferenças:

- **Requisição**: sem sessão nem CSRF; `Authorization: Bearer kbv_…` (token da conversa do visitante) e `Origin` permitido. Os erros antes do stream são os da [tabela da requisição](#requisição) com os códigos do widget no lugar dos do painel: 401 `invalid_visitor_token`, 404 `not_found` ou `widget_unavailable` (no lugar de `product_inactive`), 429 `rate_limited`, além de `level_not_configured`, `validation_error` e os do provedor de embedding.
- **`citations`**: `level` é sempre `end_user`; citação de conhecimento com `evidence: null`.
- **`done`**: `model`, `input_tokens`, `output_tokens` e `cost_usd` vêm sempre `null` (o custo é gravado na mensagem, mas não vai ao visitante); `ticket_requests_enabled` é o do widget (o widget oferece chamado **e** o produto tem o webhook).
- **`error`**: igual; o widget mostra uma mensagem genérica, sem o código.

## Estados da mensagem do assistente

| `status` | Significado |
|---|---|
| `streaming` | O LLM está respondendo (só enquanto o stream está aberto). Se o processo do servidor morrer no meio do stream, a mensagem ficaria `streaming` para sempre: por isso, uma resposta `streaming` sem atualização há mais de 5 minutos é lida como `interrupted` em `GET .../conversations/{id}` (e nas rotas administrativas), e a próxima pergunta da conversa grava `interrupted` nela antes de seguir. |
| `completed` | Resposta completa, com citações. |
| `no_source` | Resposta de "sem fonte", sem chamar o LLM. |
| `failed` | Erro do provedor ou do servidor; `error_code` diz qual. |
| `interrupted` | O cliente desconectou antes do fim; o conteúdo é o que chegou a ser gerado. |

A mensagem do usuário é sempre `completed`. O histórico enviado ao LLM nas próximas perguntas (as 10 mensagens mais recentes) inclui só perguntas e respostas `completed` ou `no_source`.
