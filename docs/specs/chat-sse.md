# Chat em streaming (SSE)

> Rascunho v0.2 · 2026-10-10 · Plano 0002, F4.4 (v0.2, F4.5: resposta `streaming` órfã lida como `interrupted`)

Contrato da resposta de `POST /v1/workspaces/{workspace_id}/conversations/{conversation_id}/messages`, que manda uma pergunta ao assistente da conversa e devolve a resposta como [Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html). Os schemas das rotas JSON (conversas, mensagens, feedback) estão no [`openapi.json`](openapi.json); lá, esta rota aparece com `200` em `text/event-stream`, e os eventos são descritos aqui. O comportamento do chat além do fio (regra de citações, `Retriever`, fases da rodada, histórico, feedback e visão administrativa) está em [chat.md](chat.md). Implementação em [`backend/src/knobridge/conversations/`](../../backend/src/knobridge/conversations/AGENTS.md) e [`backend/src/knobridge/api/conversations.py`](../../backend/src/knobridge/api/AGENTS.md).

## Requisição

- Sessão do painel (cookie) e header CSRF, como toda rota não segura.
- Corpo JSON: `{"content": "pergunta"}` (1 a 8000 caracteres, sem espaços nas pontas).
- Só o dono da conversa envia mensagens. Owner e admin do workspace leem conversas de outros membros, mas recebem 403 `forbidden` ao tentar enviar; quem não pode ler recebe 404 `not_found`.

Antes do primeiro byte do stream, a pergunta e o ponto de partida da resposta já foram gravados e confirmados (commit). Por isso, erros de acesso e de estado saem como JSON comum, no formato único de erro, e não como evento:

| Status | `code` | Quando |
|---|---|---|
| 401 | `unauthenticated` | Sem sessão viva. |
| 403 | `forbidden`, `csrf_failed`, `workspace_suspended` | Não é o dono, CSRF ausente ou workspace suspenso. |
| 404 | `not_found` | Conversa inexistente, de outro workspace ou de outro membro (para quem não é owner/admin). |
| 409 | `assistant_inactive` | O assistente da conversa foi desativado. |
| 422 | `validation_error` | Corpo inválido (pergunta vazia ou longa demais). |

## Formato no fio

Resposta `200` com `Content-Type: text/event-stream`, `Cache-Control: no-cache` e `X-Accel-Buffering: no`. Cada evento tem uma linha `event:` com o nome e uma linha `data:` com um objeto JSON (UTF-8, numa linha só), seguidas de uma linha em branco:

```text
event: citations
data: {"message_id":"…","user_message_id":"…","citations":[…]}

event: delta
data: {"text":"Para fechar o caixa, "}

event: done
data: {"message_id":"…","status":"completed","model":"gpt-4.1-mini","input_tokens":812,"output_tokens":64,"latency_ms":2310}
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
| `citations` | lista | Fontes numeradas da resposta; vazia quando não há fonte. |

Cada citação: `index` (inteiro a partir de 1, o mesmo `[n]` que a resposta usa no texto), `title` (texto), `uri` (texto ou `null`), `snippet` (até 300 caracteres do trecho) e `document_id` (texto ou `null`). As mesmas citações ficam gravadas na mensagem (`citations` em `GET .../conversations/{id}`).

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
| `latency_ms` | inteiro | Do recebimento da pergunta ao fim da resposta (relógio do servidor). |

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

Quando a recuperação não encontra nenhuma fonte, o LLM **não é chamado**. A resposta é a mensagem de "sem fonte" configurada no assistente (por padrão, diz que não sabe e oferece abrir um chamado):

```text
event: citations
data: {"message_id":"…","user_message_id":"…","citations":[]}

event: delta
data: {"text":"Não encontrei essa informação nas fontes que tenho disponíveis, …"}

event: done
data: {"message_id":"…","status":"no_source","model":null,"input_tokens":null,"output_tokens":null,"latency_ms":3}
```

A mensagem fica gravada com `status: no_source` e `citations: []`. O painel usa esse status para mostrar a oferta de abrir chamado.

## Estados da mensagem do assistente

| `status` | Significado |
|---|---|
| `streaming` | O LLM está respondendo (só enquanto o stream está aberto). Se o processo do servidor morrer no meio do stream, a mensagem ficaria `streaming` para sempre: por isso, uma resposta `streaming` sem atualização há mais de 5 minutos é lida como `interrupted` em `GET .../conversations/{id}` (e nas rotas administrativas), e a próxima pergunta da conversa grava `interrupted` nela antes de seguir. |
| `completed` | Resposta completa, com citações. |
| `no_source` | Resposta de "sem fonte", sem chamar o LLM. |
| `failed` | Erro do provedor ou do servidor; `error_code` diz qual. |
| `interrupted` | O cliente desconectou antes do fim; o conteúdo é o que chegou a ser gerado. |

A mensagem do usuário é sempre `completed`. O histórico enviado ao LLM nas próximas perguntas (as 10 mensagens mais recentes) inclui só perguntas e respostas `completed` ou `no_source`.
