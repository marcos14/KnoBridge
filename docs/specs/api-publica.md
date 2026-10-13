# API pública

> Rascunho v0.1 · 2026-10-12 · Plano 0008 (F1.1; implementação nas F2.3 e F2.4)

Contrato do acesso programático aos assistentes: chaves de API, a REST própria de conversa e a API compatível com OpenAI (`/v1/models` e `/v1/chat/completions`). A decisão de arquitetura está no [ADR 0007](../adr/0007-chaves-e-api-publica.md). O comportamento da rodada de chat (busca, regra de citações, histórico, estados) é o de [chat.md](chat.md); os eventos SSE da REST própria são os de [chat-sse.md](chat-sse.md). Os schemas JSON das rotas entram no [`openapi.json`](openapi.json) quando forem implementadas. Custos e uso, em [uso-e-custos.md](uso-e-custos.md).

Código previsto: `backend/src/knobridge/apikeys/` (chaves e autenticação), `backend/src/knobridge/api/api_keys.py` (CRUD no painel), `api/public_conversations.py` (REST própria) e `api/openai_compat.py` (rotas compatíveis com OpenAI, com o formato em `api/openai_wire.py` e os erros em `api/openai_errors.py`; modelos em `apikeys/assistants.py`). Tela: `frontend/src/features/apikeys/`.

## Visão geral

| Rota | Autenticação | Formato de erro |
|---|---|---|
| `GET`, `POST .../api-keys`, `PATCH .../api-keys/{id}`, `POST .../api-keys/{id}/revoke` | sessão + CSRF, owner ou admin | KnoBridge (`{"error": {"code", "message", "details"}}`) |
| `POST /v1/conversations`, `GET /v1/conversations/{id}`, `POST /v1/conversations/{id}/messages` | chave de API | KnoBridge |
| `GET /v1/models`, `POST /v1/chat/completions` | chave de API | OpenAI (`{"error": {"message", "type", "param", "code"}}`) |

`...` = `/v1/workspaces/{workspace_id}`.

## Chave de API

### Formato

- `kbk_<prefixo>_<segredo>`, validado por `^kbk_([a-z0-9]{8})_([A-Za-z0-9_-]{43})$`.
- `prefixo`: 8 caracteres aleatórios de `[a-z0-9]`, guardado em claro em `api_keys.key_prefix`, **único na instância** e mostrado no painel para identificar a chave.
- `segredo`: `secrets.token_urlsafe(32)` (43 caracteres).
- O servidor guarda só `key_hash` = SHA-256 hex da string inteira. A chave aparece **uma única vez**, na resposta da criação. Perdeu, cria outra e revoga a antiga.
- O prefixo fixo `kbk_` permite varredura de segredos (gitleaks).

### Escopo

- `assistant_ids: null` (padrão): a chave fala com todos os assistentes **ativos** do workspace, inclusive os criados depois.
- `assistant_ids: [..]` (1 a 100 ids, sem repetição): só com esses. Na criação e na edição, todo id tem de ser de um assistente do workspace (422 `api_key_assistant_invalid`, com `details.assistant_ids` dos inválidos). Um assistente excluído depois some do escopo sem erro; uma chave cujo escopo só tem assistentes excluídos não enxerga nenhum.
- Assistente inativo, excluído ou fora do escopo é tratado como inexistente (404), nunca como 403: a chave não revela o que não pode usar.

### Gestão no painel (owner ou admin)

Todas com sessão e, nas não seguras, header CSRF. Papel abaixo de admin: 403 `forbidden`.

**`GET .../api-keys`**: paginada (`limit` padrão 50, máximo 200; `offset`), ordem por nome, revogadas incluídas. Filtros: `query` (nome ou prefixo, sem diferenciar maiúsculas) e `status` (`active` ou `revoked`). Item `ApiKeyOut`:

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | uuid | |
| `name` | texto | 1 a 200 caracteres, único no workspace. |
| `key_prefix` | texto | Os 8 caracteres do prefixo; o painel mostra `kbk_<prefixo>_…`. |
| `assistant_ids` | lista de uuid ou `null` | Escopo (`null` = todos). |
| `created_by` | uuid ou `null` | Quem criou (`null` se o usuário foi excluído). |
| `created_by_name` | texto ou `null` | Nome de quem criou. |
| `created_at` | data | |
| `last_used_at` | data ou `null` | Última requisição autenticada (ver abaixo). |
| `revoked_at` | data ou `null` | Preenchido ao revogar (irreversível). |

**`POST .../api-keys`**: corpo `{"name": "...", "assistant_ids": null | [uuid]}`. Resposta 201 `ApiKeyCreated` = `{"api_key": ApiKeyOut, "key": "kbk_…"}`. Erros: 409 `api_key_name_taken`, 422 `api_key_assistant_invalid` ou `validation_error`.

**`PATCH .../api-keys/{api_key_id}`**: corpo com `name` e/ou `assistant_ids` (campo omitido fica; `assistant_ids: null` volta a "todos"; corpo vazio é 422). Resposta 200 `ApiKeyOut`. Erros: 404 `not_found`, 409 `api_key_name_taken` ou `api_key_revoked` (chave revogada não muda), 422 como na criação. O segredo nunca muda: para trocar, cria outra e revoga esta.

**`POST .../api-keys/{api_key_id}/revoke`**: grava `revoked_at` e responde 200 `ApiKeyOut`. Idempotente: revogar de novo responde a mesma chave, sem novo evento de auditoria. Vale na próxima requisição da chave. Não há exclusão: as conversas feitas pela chave continuam apontando para ela.

### Autenticação

Header `Authorization: Bearer kbk_…` (o esquema `Bearer` sem diferenciar maiúsculas). A dependência `current_api_key`:

1. header ausente, sem `Bearer` ou fora do formato → 401;
2. busca a chave por `key_prefix` em modo de sistema (índice único; o workspace ainda não é conhecido);
3. compara `SHA-256(chave)` com `key_hash` em tempo constante (`hmac.compare_digest`); prefixo desconhecido compara com um hash fictício, para custar o mesmo;
4. chave inexistente, hash diferente ou `revoked_at` preenchido → 401 (mesma resposta nos três casos);
5. workspace suspenso → 403;
6. abre a transação com `SET LOCAL app.workspace_id` da chave, sem `app.user_id`; toda consulta da requisição roda nesse escopo, com a RLS.

Respostas de falha:

| Caso | REST própria | Rotas compatíveis com OpenAI |
|---|---|---|
| Chave ausente, inválida ou revogada | 401 `invalid_api_key` | 401 `{"type": "invalid_request_error", "code": "invalid_api_key"}` |
| Workspace suspenso | 403 `workspace_suspended` | 403 `{"type": "permission_error", "code": "workspace_suspended"}` |

Toda resposta 401 leva `WWW-Authenticate: Bearer`.

Regras:

- **A chave só abre a API pública** (tabela da visão geral). Com a chave, rotas do painel respondem 401 como sem sessão; com o cookie de sessão e sem chave, a API pública responde 401. A API pública ignora cookies e não exige CSRF.
- **A chave nunca é logada nem auditada**, nem em erro. Logs da API pública levam `workspace_id`, `api_key_id` e `conversation_id`.
- **`last_used_at`**: gravado numa transação curta depois da autenticação, só quando está nulo ou tem mais de 60 s (`UPDATE … WHERE last_used_at IS NULL OR last_used_at < agora - 60 s`), para não escrever a cada requisição. Relógio injetado.
- **Uso não é auditado por requisição.** As conversas ficam gravadas (abaixo) e o custo, em [uso-e-custos.md](uso-e-custos.md).

## Conversas da API

- Toda conversa criada pela API (REST própria ou compatível com OpenAI) é gravada com `channel = api`, `api_key_id` = a chave e `user_id` nulo; cada resposta, com `messages.channel = api` e o custo estimado ([chat.md](chat.md#custo-e-canal-por-resposta)).
- **A chave é a dona**: só a chave que criou a conversa lê e pergunta nela (outra chave do mesmo workspace recebe 404). Pessoas não continuam conversas da API pelo painel; owner e admin as leem na visão administrativa (**Conversas**), que mostra o nome da chave no lugar do usuário e filtra por canal ([chat.md](chat.md#visão-administrativa)).
- Revogar a chave não apaga as conversas; excluir o assistente apaga, como no painel.
- Na busca, a `RetrievalQuery` vai com `user_id` nulo: o acesso é o do escopo da chave sobre as coleções do assistente.

## REST própria de conversa

Corpos e respostas em JSON (UTF-8). Erros no formato único do KnoBridge.

### `POST /v1/conversations`

Corpo `{"assistant_id": "uuid"}`. Resposta 201 `PublicConversationOut`:

```json
{"id": "…", "assistant_id": "…", "title": null, "channel": "api", "created_at": "…", "updated_at": "…"}
```

Erros: 404 `not_found` (assistente inexistente, inativo ou fora do escopo), 422 `validation_error`.

### `POST /v1/conversations/{conversation_id}/messages`

Corpo:

| Campo | Tipo | Descrição |
|---|---|---|
| `content` | texto | A pergunta, de 1 a 8000 caracteres, sem espaços nas pontas (como no painel). |
| `stream` | booleano | Padrão `false`. `true`: resposta em SSE. |

A rodada é a mesma do painel ([chat.md](chat.md#orquestração-em-duas-fases)): busca, regra 8, histórico das 10 mensagens mais recentes da conversa e as duas fases. Erros de acesso e de estado saem antes da resposta, como JSON: 404 `not_found` (conversa inexistente, de outra chave ou de outro workspace), 409 `assistant_inactive` (assistente desativado depois de criada a conversa; se ele saiu do escopo da chave, 404 `not_found`), 422 `validation_error` e os erros do provedor de embedding (422, 429, 502, 503 `provider_*`/`embedding_*`, como em [chat-sse.md](chat-sse.md#requisição)).

**Com `stream: true`**: 200 `text/event-stream` com exatamente os eventos de [chat-sse.md](chat-sse.md) (`citations`, `delta`…, `done` ou `error`), inclusive `cost_usd` no `done`.

**Com `stream: false`**: o servidor consome a rodada inteira e responde 200 `PublicAnswerOut`:

```json
{
  "user_message_id": "…",
  "message": {
    "id": "…", "role": "assistant", "content": "Para fechar o caixa… [1]",
    "citations": [{"index": 1, "title": "src/caixa/fechamento.ts", "uri": "src/caixa/fechamento.ts#L10-L42", "…": "…"}],
    "status": "completed", "error_code": null, "model": "gpt-4.1-mini",
    "input_tokens": 812, "output_tokens": 64, "cost_usd": 0.000427, "latency_ms": 2310,
    "channel": "api", "created_at": "…"
  }
}
```

`message` tem o formato de `MessageOut` do painel sem `feedback` e `ticket_request`; `citations` no formato de [chat-sse.md](chat-sse.md#citations). Uma falha do provedor durante a geração **não** muda o HTTP: a resposta é 200 com `status: failed`, `error_code` (`provider_*` ou `chat_failed`) e o conteúdo parcial, igual ao que fica gravado. Sem fonte, `status: no_source`, `citations: []` e `content` = mensagem de "sem fonte" do assistente.

### `GET /v1/conversations/{conversation_id}`

Resposta 200 `PublicConversationDetail` = `PublicConversationOut` + `messages` paginadas (`messages_limit` padrão 50, máximo 200; `messages_offset`; `{items, total, limit, offset}`), na ordem da conversa, no formato acima. Resposta `streaming` órfã aparece como `interrupted` ([chat.md](chat.md#estados-das-mensagens)). Erro: 404 `not_found`.

Fora desta versão: listar e excluir conversas pela API, feedback e pedido de chamado pela API.

## API compatível com OpenAI

Feita para os SDKs oficiais e clientes de chat que falam Chat Completions: o cliente aponta `base_url` para `https://<instância>/v1` e usa a chave como `api_key`. Referência do formato: [Chat Completions](https://platform.openai.com/docs/api-reference/chat) e [Models](https://platform.openai.com/docs/api-reference/models).

### Modelo = assistente

- Cada assistente ativo dentro do escopo da chave é um modelo.
- No pedido, `model` aceita o **nome exato** do assistente (diferencia maiúsculas; nomes são únicos no workspace) ou o **id** (uuid). Renomear um assistente quebra quem usa o nome; o id é estável.
- Inexistente, inativo ou fora do escopo: 404 `model_not_found` (`param: "model"`).

### `GET /v1/models`

Resposta 200, assistentes ativos do escopo, por nome (sem paginação; o número de assistentes de um workspace é pequeno):

```json
{
  "object": "list",
  "data": [
    {
      "id": "Suporte ERP",
      "object": "model",
      "created": 1791800000,
      "owned_by": "knobridge",
      "knobridge": {"assistant_id": "…", "description": "Dúvidas do ERP"}
    }
  ]
}
```

`created` é o `created_at` do assistente em segundos Unix. `GET /v1/models/{model}` responde o mesmo objeto de um modelo, ou 404 `model_not_found`.

### `POST /v1/chat/completions`

**Parâmetros usados**

| Parâmetro | Uso |
|---|---|
| `model` | Obrigatório. Assistente (acima). |
| `messages` | Obrigatório, 1 a 200 mensagens. Ver mapeamento. |
| `stream` | Padrão `false`. |
| `stream_options.include_usage` | Com `stream: true`, manda o chunk final de uso (abaixo). |
| `knobridge.append_sources` | Extensão, padrão `true`: acrescenta a lista de fontes ao fim do texto (abaixo). Pelo SDK Python, vai em `extra_body`. |

**Parâmetros aceitos e ignorados** (a configuração do assistente decide): `temperature`, `top_p`, `max_tokens`, `max_completion_tokens`, `presence_penalty`, `frequency_penalty`, `logit_bias`, `logprobs`, `top_logprobs`, `seed`, `stop`, `user`, `metadata`, `store`, `service_tier`, `reasoning_effort`, `parallel_tool_calls`, `tools`, `functions`, `tool_choice` (`none` ou `auto`), `response_format` com `type: "text"`, `n` igual a 1, e qualquer campo desconhecido. O assistente nunca chama ferramentas.

**Parâmetros recusados** (400, `param` com o nome): `n` maior que 1 (`unsupported_parameter`); `response_format` com `json_object` ou `json_schema` (`unsupported_parameter`); `tool_choice` `required` ou com uma função (`unsupported_parameter`); `modalities` com `audio` ou `audio` presente (`unsupported_parameter`).

**Mapeamento de `messages` para a rodada de chat**

1. Papéis aceitos: `system`, `developer`, `user` e `assistant`. `tool` e `function` dão 400 `unsupported_message_role` (`param: "messages"`).
2. `content` pode ser texto ou lista de partes; das partes, só `type: "text"` é usada (concatenadas com quebra de linha). Parte `image_url`, `input_audio` ou `file` dá 400 `unsupported_content`. Mensagem `assistant` com `content` nulo (só com `tool_calls`) é ignorada. `name` é ignorado.
3. **`system` e `developer` são ignorados**: as instruções são o prompt do assistente e as regras fixas de [chat.md](chat.md#regra-de-citações-regra-8-do-agentsmd), que o cliente não substitui.
4. **A pergunta é a última mensagem**, que tem de ser `user` com texto não vazio (senão, 400 `invalid_messages`). Até 8000 caracteres depois de tirar os espaços das pontas (senão, 400 `question_too_long`). A busca usa só ela.
5. **Histórico**: as mensagens `user` e `assistant` antes da pergunta, as 10 mais recentes (a mesma janela do painel), na ordem recebida, cada uma cortada em 8000 caracteres. Vão ao LLM depois das fontes, como o histórico do painel. Como o cliente pode mandar o que quiser como "resposta anterior", o histórico é contexto, não fonte: a regra das citações continua valendo só para as fontes.
6. **Gravação**: cada chamada cria uma conversa `channel = api` da chave, com título pela pergunta, e grava só a pergunta e a resposta. O histórico do cliente não é gravado.
7. **Regra 8**: sem fonte, o LLM não é chamado; a resposta é a `no_source_message` do assistente, com `finish_reason: "stop"` e `knobridge.status: "no_source"`.

**Resposta sem streaming** (200):

```json
{
  "id": "chatcmpl-<id da mensagem, hex sem hífens>",
  "object": "chat.completion",
  "created": 1791800000,
  "model": "Suporte ERP",
  "choices": [
    {
      "index": 0,
      "message": {"role": "assistant", "content": "Para fechar o caixa… [1]\n\nFontes:\n[1] src/caixa/fechamento.ts (src/caixa/fechamento.ts#L10-L42)", "refusal": null},
      "logprobs": null,
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 812, "completion_tokens": 64, "total_tokens": 876},
  "system_fingerprint": null,
  "knobridge": {
    "conversation_id": "…",
    "message_id": "…",
    "status": "completed",
    "citations": [{"index": 1, "title": "src/caixa/fechamento.ts", "uri": "src/caixa/fechamento.ts#L10-L42", "…": "…"}],
    "cost_usd": 0.000427
  }
}
```

- `model` ecoa o valor recebido. `created` é o instante da pergunta, em segundos Unix.
- `knobridge.citations`: a mesma lista do evento `citations` de [chat-sse.md](chat-sse.md#citations). `knobridge.status`: `completed` ou `no_source`.
- **Fontes no texto** (`append_sources`, padrão ligado; a visão manda as citações "no texto e num campo extra"): com citações, o conteúdo ganha `\n\nFontes:\n` e uma linha `[n] título (uri)` por citação (sem `(uri)` quando ela é nula). Desligado, o conteúdo é só o texto do LLM. A resposta gravada no KnoBridge nunca inclui esse rodapé.
- `usage`: os tokens informados pelo provedor; em `no_source`, `{"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}`; quando o provedor não informa, `usage: null`.
- Falha do provedor durante a geração: a mensagem é gravada `failed` e a resposta é o erro mapeado (tabela de erros), não um 200.

**Resposta com streaming** (200 `text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`). Linhas `data: <json>` separadas por linha em branco, sem `event:`, terminando em `data: [DONE]`:

1. Primeiro chunk: `choices[0].delta = {"role": "assistant", "content": ""}` e `knobridge = {"conversation_id", "message_id", "citations"}` (as citações chegam antes do texto, como no painel).
2. Um chunk por pedaço do LLM: `choices[0].delta = {"content": "…"}`, `finish_reason: null`. Em `no_source`, um chunk só, com a mensagem de "sem fonte".
3. Com `append_sources` e citações, um chunk com o rodapé de fontes.
4. Chunk final: `delta: {}`, `finish_reason: "stop"`, `knobridge = {"status", "cost_usd"}`.
5. Com `stream_options.include_usage: true`, mais um chunk com `choices: []` e `usage` (igual ao sem streaming).
6. `data: [DONE]`.

Todo chunk tem `id` (o mesmo `chatcmpl-…`), `object: "chat.completion.chunk"`, `created`, `model` e `system_fingerprint: null`.

```text
data: {"id":"chatcmpl-…","object":"chat.completion.chunk","created":1791800000,"model":"Suporte ERP","system_fingerprint":null,"choices":[{"index":0,"delta":{"role":"assistant","content":""},"logprobs":null,"finish_reason":null}],"knobridge":{"conversation_id":"…","message_id":"…","citations":[…]}}

data: {"id":"chatcmpl-…","object":"chat.completion.chunk","created":1791800000,"model":"Suporte ERP","system_fingerprint":null,"choices":[{"index":0,"delta":{"content":"Para fechar o caixa, "},"logprobs":null,"finish_reason":null}]}

data: {"id":"chatcmpl-…","object":"chat.completion.chunk","created":1791800000,"model":"Suporte ERP","system_fingerprint":null,"choices":[{"index":0,"delta":{},"logprobs":null,"finish_reason":"stop"}],"knobridge":{"status":"completed","cost_usd":0.000427}}

data: [DONE]
```

Erro do provedor depois de começar o stream (o HTTP já é 200): um `data: {"error": {…}}` no formato da tabela abaixo, e o stream fecha sem `[DONE]`. A mensagem fica gravada `failed` com o conteúdo parcial. Cliente que desconecta deixa a mensagem `interrupted`, como no painel.

### Erros no formato OpenAI

`GET /v1/models`, `GET /v1/models/{model}` e `POST /v1/chat/completions` respondem erros como `{"error": {"message": "…", "type": "…", "param": "…" | null, "code": "…"}}`. A mensagem é sempre nossa, em inglês, e nunca repete o texto do provedor. Erros de validação do FastAPI (422) viram 400 aqui.

| HTTP | `type` | `code` | Quando |
|---|---|---|---|
| 400 | `invalid_request_error` | `invalid_request` | Corpo que não é JSON ou campo com tipo errado (`param` = caminho do campo). |
| 400 | `invalid_request_error` | `invalid_messages`, `unsupported_message_role`, `unsupported_content`, `question_too_long` | Problemas em `messages` (mapeamento acima). |
| 400 | `invalid_request_error` | `unsupported_parameter` | Parâmetro recusado (lista acima). |
| 401 | `invalid_request_error` | `invalid_api_key` | Chave ausente, inválida ou revogada. |
| 403 | `permission_error` | `workspace_suspended` | Workspace da chave suspenso. |
| 404 | `invalid_request_error` | `model_not_found` | Assistente inexistente, inativo ou fora do escopo. |
| 413 | `invalid_request_error` | `payload_too_large` | Corpo acima do limite. |
| 429 | `rate_limit_error` | `provider_rate_limited` | Limite do provedor de LLM ou de embedding. |
| 502 | `api_error` | `provider_auth_failed`, `provider_request_failed`, `embedding_*` e demais `provider_*` | O provedor recusou a chave ou o pedido, ou o embedding da pergunta falhou (qualquer status original, inclusive 422). |
| 503 | `api_error` | `provider_unavailable` | Provedor fora do ar ou timeout. |
| 500 | `api_error` | `chat_failed` | Falha inesperada no servidor. |

Os SDKs da OpenAI repetem 429 e 5xx sozinhos; cada repetição vira uma conversa nova.

## Limites

| Rota | Corpo máximo |
|---|---|
| `POST /v1/chat/completions` | 1 MiB |
| `POST /v1/conversations/{id}/messages` | 64 KiB |
| `POST /v1/conversations` | 4 KiB |

Aplicados pelo `BodyLimitMiddleware` (413 `payload_too_large` com `details.max_bytes`; nas rotas compatíveis com OpenAI, no formato da OpenAI). Além disso: pergunta até 8000 caracteres, até 200 mensagens por pedido e as 10 mais recentes como histórico. Sem limite de requisições nem cota por chave nesta versão (fora do escopo do plano 0008); o custo de cada chave aparece em Uso e custos.

## Auditoria

| Evento | Quando | `details` |
|---|---|---|
| `api_key.created` | Criar | `name`, `key_prefix`, `assistant_ids` |
| `api_key.updated` | Editar | `name`, `fields` (os campos alterados) |
| `api_key.revoked` | Primeira revogação | `name`, `key_prefix` |

Na trilha do workspace, com `target_type = api_key` e o id. Nunca a chave nem o hash. As chaves de `details` não podem conter `api_key`, `token` ou `secret` (o `AuditService` recusa; por isso `key_prefix`). O uso da chave (cada requisição) não é auditado.

## Exemplos

`curl` da REST própria:

```sh
export KNOBRIDGE_API_KEY=kbk_…   # mostrada uma vez na criação
curl -s https://kb.empresa.com/v1/conversations \
  -H "Authorization: Bearer $KNOBRIDGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"assistant_id": "6f1c…"}'
curl -s https://kb.empresa.com/v1/conversations/<id>/messages \
  -H "Authorization: Bearer $KNOBRIDGE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"content": "Como fecho o caixa?", "stream": false}'
```

Python, SDK oficial da OpenAI:

```python
import os
from openai import OpenAI

client = OpenAI(base_url="https://kb.empresa.com/v1", api_key=os.environ["KNOBRIDGE_API_KEY"])
answer = client.chat.completions.create(
    model="Suporte ERP",
    messages=[{"role": "user", "content": "Como fecho o caixa?"}],
)
print(answer.choices[0].message.content)
print(answer.model_extra["knobridge"]["citations"])  # campo extra

for chunk in client.chat.completions.create(
    model="Suporte ERP",
    messages=[{"role": "user", "content": "Como fecho o caixa?"}],
    stream=True,
):
    if chunk.choices:
        print(chunk.choices[0].delta.content or "", end="")
```

JavaScript, SDK oficial da OpenAI:

```js
import OpenAI from "openai";

const client = new OpenAI({ baseURL: "https://kb.empresa.com/v1", apiKey: process.env.KNOBRIDGE_API_KEY });
const answer = await client.chat.completions.create({
  model: "Suporte ERP",
  messages: [{ role: "user", content: "Como fecho o caixa?" }],
});
console.log(answer.choices[0].message.content, answer.knobridge.citations);
```

No painel, os exemplos usam `window.location.origin` como base e nunca embutem a chave (só a variável `KNOBRIDGE_API_KEY`).

## Referências

- OpenAI, Chat Completions: <https://platform.openai.com/docs/api-reference/chat>
- OpenAI, objeto de chunk do streaming: <https://platform.openai.com/docs/api-reference/chat-streaming>
- OpenAI, Models: <https://platform.openai.com/docs/api-reference/models>
- OpenAI, formato de erro: <https://platform.openai.com/docs/guides/error-codes>
- SDK Python da OpenAI (`extra_body`, `model_extra`): <https://github.com/openai/openai-python>
