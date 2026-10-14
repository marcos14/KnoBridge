# Widget embutível

> Rascunho v0.1 · 2026-10-14 · Plano 0010 (F1.1; implementação nas F3.1, F3.2, F4.1, F4.2 e F4.3)

Contrato do widget do KnoBridge: a configuração no painel, a chave pública `kbp_` e o segredo de assinatura `kbs_`, domínios permitidos e CORS, limites de requisição, as rotas públicas `/v1/widget/*` (configuração, conversa com SSE, leitura, feedback e chamado), o token de conversa do visitante, a identidade assinada, o elemento `<knobridge-chat>` (atributos, métodos, eventos, aparência e comportamento), onde o JS é servido, a prévia no painel, privacidade e acessibilidade. A decisão de arquitetura está no [ADR 0009](../adr/0009-canais-mcp-e-widget.md); as escolhas do usuário, no [plano 0010](../planos/0010-canais-mcp-e-widget.md) (D3, D4, D5 e D6).

O widget é um **canal público** ([Canal público](produtos-e-niveis.md#canal-público)): responde **sempre no nível `end_user`**, com ou sem identidade assinada (D5). A rodada é a do chat ([chat.md](chat.md)), os eventos são os de [chat-sse.md](chat-sse.md), as citações seguem a regra 8 ([chat.md](chat.md#regra-de-citações-regra-8-do-agentsmd)) e o chamado usa o webhook do produto ([chamados.md](chamados.md#abrir-chamado-webhook-de-saída)). Tabelas em [modelo-de-dados.md](modelo-de-dados.md#widget-e-limite-de-requisições).

Código previsto: `backend/src/knobridge/widget/` (modelo, chaves, CRUD, CORS e `Origin`, limite de requisições, token de conversa, identidade, rodada do visitante; F3.1 e F3.2), as rotas em `backend/src/knobridge/api/widgets.py` (painel) e `api/widget_public.py` (públicas); o pacote `widget/` na raiz (Web Component; F4.1 e F4.2); a tela `frontend/src/features/widget/` (F4.3).

## Visão geral

```mermaid
sequenceDiagram
    participant H as Servidor do hospedeiro
    participant B as Navegador (site do hospedeiro)
    participant F as Instância: /widget/v1/knobridge-chat.js
    participant A as Instância: /v1/widget/{kbp_}/…
    H-->>B: página com script, elemento e (opcional) identidade v1.… assinada com kbs_
    B->>F: GET knobridge-chat.js (script clássico)
    B->>A: GET config (Origin do site)
    A-->>B: aparência, saudação, recursos ligados
    B->>A: POST conversations (identidade opcional), na primeira pergunta
    A-->>B: conversa + visitor_token kbv_ (uma vez; vai para o localStorage)
    B->>A: POST conversations/{id}/messages (Bearer kbv_)
    A-->>B: SSE: citations, delta…, done
    B->>A: feedback, ticket-requests (Bearer kbv_)
```

| Rota | Autenticação | Quem usa |
|---|---|---|
| `GET`, `POST .../widgets`, `GET`, `PATCH`, `DELETE .../widgets/{id}`, `POST`, `DELETE .../widgets/{id}/signing-secret` | sessão + CSRF, admin | Painel (`...` = `/v1/workspaces/{workspace_id}`) |
| `GET /v1/widget/{public_key}/config` | `Origin` permitido | Widget |
| `POST /v1/widget/{public_key}/conversations` | `Origin` permitido (+ identidade opcional) | Widget |
| `GET /v1/widget/{public_key}/conversations/{conversation_id}` | `Origin` + `Bearer kbv_…` | Widget |
| `POST /v1/widget/{public_key}/conversations/{conversation_id}/messages` | `Origin` + `Bearer kbv_…` | Widget (SSE) |
| `POST /v1/widget/{public_key}/conversations/{conversation_id}/messages/{message_id}/feedback` | `Origin` + `Bearer kbv_…` | Widget |
| `POST /v1/widget/{public_key}/conversations/{conversation_id}/ticket-requests`, `GET .../ticket-requests/{ticket_request_id}` | `Origin` + `Bearer kbv_…` | Widget |

Todas as rotas `/v1/widget/*` aceitam também `OPTIONS` (preflight). Erros no formato único do KnoBridge (`{"error": {"code", "message", "details"}}`).

## Configuração no painel

Um **widget** pertence a um produto. Um produto pode ter vários (o site público e o sistema logado, por exemplo), cada um com a sua chave pública, domínios, aparência e limites.

### Campos

| Campo | Tipo | Regras |
|---|---|---|
| `id` | uuid | |
| `product_id` | uuid | Produto do workspace (422 `widget_product_invalid`). **Não muda** depois de criado (no `PATCH`, 422 `validation_error`): para outro produto, crie outro widget. |
| `product_name` | texto | Só leitura. |
| `name` | texto | 1 a 200 caracteres, sem espaços nas pontas, único no workspace (409 `widget_name_taken`). Só no painel. |
| `public_key` | texto | Só leitura: `kbp_…` ([Chave pública](#chave-pública-kbp_)). |
| `allowed_origins` | lista de texto | 1 a 50 origens ([Domínios permitidos](#domínios-permitidos-e-cors)); inválidas: 422 `widget_origin_invalid` com `details: {origins: [{origin, reason}]}`. |
| `active` | booleano | Padrão `true`. Inativo: as rotas públicas respondem 404 `widget_unavailable`. |
| `mode` | `bubble` ou `inline` | Padrão `bubble` (balão flutuante). `inline`: o chat ocupa o lugar do elemento na página. |
| `position` | `bottom-right` ou `bottom-left` | Padrão `bottom-right`; só no modo `bubble`. |
| `theme` | `light`, `dark` ou `auto` | Padrão `auto` (segue `prefers-color-scheme`). |
| `primary_color` | texto | `#RRGGBB` (`^#[0-9a-fA-F]{6}$`), padrão `#2563eb`; gravado em minúsculas. |
| `title` | texto ou `null` | Cabeçalho do chat, até 80 caracteres; `null` ou vazio = o nome do produto. |
| `greeting` | texto | Primeira mensagem mostrada (não gravada na conversa), até 500 caracteres; padrão "Olá! Como posso ajudar?". Vazio = sem saudação. |
| `placeholder` | texto | Texto do campo de pergunta, até 120 caracteres; padrão "Escreva sua pergunta". |
| `feedback_enabled` | booleano | Padrão `true`: 👍/👎 nas respostas. |
| `ticket_enabled` | booleano | Padrão `true`: oferece abrir chamado. Só vale quando o produto tem o webhook configurado (`ticket_available`). |
| `ticket_available` | booleano | Só leitura: `ticket_enabled` e o produto com `ticket_webhook_configured`. |
| `messages_per_ip_per_hour` | inteiro | 1 a 1000, padrão 30 ([Limites](#limites-de-requisição)). |
| `messages_per_day` | inteiro | 1 a 100 000, padrão 1000: total de perguntas do widget por janela de 24 h. |
| `signing_secret_configured` | booleano | Só leitura: há segredo `kbs_`. |
| `signing_secret_created_at` | data ou `null` | Só leitura. Nunca o segredo. |
| `created_by`, `created_by_name` | uuid, texto ou `null` | Quem criou. |
| `created_at`, `updated_at` | data | |

### Rotas (owner ou admin)

Sob `/v1/workspaces/{workspace_id}/widgets` (`api/widgets.py`), com sessão e, nas não seguras, CSRF. Papel abaixo de admin: 403 `forbidden`. O widget expõe um produto ao público e gasta LLM do workspace, por isso é admin, como as chaves de API.

- **`GET ""`**: paginada (`limit` padrão 50, máximo 200; `offset`; `total`), ordem por nome e depois `id`. Filtros: `product_id`, `active` e `query` (nome, até 200 caracteres, sem diferenciar maiúsculas, `%`, `_` e `\` escapados). Itens `WidgetOut` (os campos acima). Número constante de statements.
- **`GET /{widget_id}`**: `WidgetOut`, ou 404 `not_found`.
- **`POST ""`**: corpo com `product_id`, `name`, `allowed_origins` (obrigatórios) e os campos de aparência, recursos e limites (opcionais, com os padrões). Resposta 201 `WidgetOut`. Gera a `public_key`. Erros: 409 `widget_name_taken`, 422 `widget_product_invalid`, `widget_origin_invalid` ou `validation_error`.
- **`PATCH /{widget_id}`**: campo omitido fica; `allowed_origins` substitui a lista; `title: null` volta ao nome do produto; corpo vazio é 422. Resposta 200 `WidgetOut`.
- **`DELETE /{widget_id}`**: 204. Apaga as conversas do widget (com mensagens, feedback e pedidos de chamado), como a exclusão de um produto. Para preservar o histórico, desative. A chave pública deixa de existir na hora.
- **`POST /{widget_id}/signing-secret`**: gera ou substitui o segredo de assinatura e responde 201 `{"secret": "kbs_…", "created_at": "…"}` **uma única vez**. Identidades assinadas com o segredo anterior passam a ser recusadas na hora.
- **`DELETE /{widget_id}/signing-secret`**: 204; apaga o segredo. Daí em diante, identidade enviada é recusada (401 `widget_identity_invalid`, `reason: not_configured`); visitantes anônimos continuam.

O painel monta o trecho para copiar a partir de `public_key` e da origem da instância ([Embutir](#embutir-o-elemento)).

### Auditoria

| Evento | Quando | `details` |
|---|---|---|
| `widget.created` | Criar | `name`, `product_id`, `public_key`, `allowed_origins` |
| `widget.updated` | Editar | `name`, `fields` (nomes dos campos alterados) |
| `widget.deleted` | Excluir | `name`, `conversation_count` |
| `widget.signing_secret_rotated` | Gerar ou substituir o segredo | `name` |
| `widget.signing_secret_removed` | Apagar o segredo | `name` |

Na trilha do workspace, `target_type = widget` e o id. Nunca o segredo. As chaves de `details` não contêm `api_key`, `token` nem `secret` (regra do `AuditService`). As rotas públicas não auditam por requisição; o pedido de chamado do visitante audita `ticket_request.created` ([chamados.md](chamados.md#pedidos-vindos-do-mcp-e-do-widget)).

## Chave pública `kbp_`

- Formato `kbp_<24 caracteres de [a-z0-9]>`, validado por `^kbp_[a-z0-9]{24}$`, gerado com `secrets.choice`; **único na instância** (`uq_widgets_public_key`).
- **Não é segredo**: vai no HTML do site e no caminho das rotas públicas. É gravada em claro e mostrada sempre no painel. Por isso o prefixo é diferente das credenciais (`kbk_`, `kbi_`, `kbr_`, `kbs_`, `kbv_`, `kbw_`).
- Na rota pública, a chave é buscada em modo de sistema (o workspace ainda não é conhecido), e o resto da requisição roda no escopo do workspace do widget, com a RLS ([ADR 0001](../adr/0001-tenancy-e-rls.md)), sem `app.user_id`.
- Chave fora do formato ou desconhecida: 404 `not_found` **sem** cabeçalhos CORS. Widget inativo, produto inativo ou workspace suspenso: 404 `widget_unavailable` (com CORS, se a origem é permitida), para o widget mostrar "Chat indisponível".
- Não há rotação da chave pública: para trocar, crie outro widget e desative este.

## Segredo de assinatura `kbs_`

- Formato `kbs_<secrets.token_urlsafe(32)>` (43 caracteres), validado por `^kbs_[A-Za-z0-9_-]{43}$`. Opcional: só para quem usa [identidade assinada](#identidade-assinada).
- Fica **no servidor do sistema hospedeiro**, nunca no navegador. O KnoBridge precisa dele para verificar, então o guarda cifrado com AES-256-GCM pelo `SecretBox` ([ADR 0003](../adr/0003-segredos-cifrados.md)): `info` `knobridge/widget-signing-secrets/v1`, dados associados `widget_signing_secret:<workspace_id>:<widget_id>`. Nunca volta pela API depois da criação, nunca vai para log nem auditoria.
- O prefixo fixo `kbs_` permite que varreduras de segredos o reconheçam.

## Domínios permitidos e CORS

### Origens permitidas

Cada item de `allowed_origins` é uma origem, sem caminho, consulta nem barra final:

- `https://app.cliente.com.br`, `http://intranet.cliente.local:8080`: esquema `http` ou `https`, host e porta opcional;
- `https://*.cliente.com.br`: curinga **só no primeiro rótulo**, casa qualquer subdomínio (de qualquer profundidade), não o domínio raiz;
- comparação sem diferenciar maiúsculas, com a porta padrão removida (`https://a.com:443` = `https://a.com`); gravadas normalizadas, sem repetição; até 255 caracteres cada.

Motivos de `widget_origin_invalid`: `malformed`, `scheme_not_allowed` (fora de `http`/`https`), `path_not_allowed`, `wildcard_not_allowed` (curinga fora do primeiro rótulo, ou `*` sozinho), `too_long`, `duplicate`.

A **origem da própria instância** (de `KNOBRIDGE_PUBLIC_BASE_URL`) é sempre permitida, para a [prévia do painel](#prévia-no-painel), sem estar na lista.

### Checagem de `Origin`

Toda requisição a `/v1/widget/{public_key}/…`, na ordem:

1. chave pública desconhecida ou fora do formato → 404 `not_found`, sem CORS;
2. header `Origin` **ausente** ou fora das origens permitidas → 403 `widget_origin_not_allowed`, sem CORS (o navegador sempre manda `Origin` em `fetch` de outra origem e em todo `POST`);
3. widget inativo, produto inativo ou workspace suspenso → 404 `widget_unavailable`;
4. limite geral de requisições ([Limites](#limites-de-requisição)) → 429;
5. a regra da rota.

A checagem de `Origin` **não é autenticação**: um programa fora do navegador forja o header. O que limita abuso é o limite de requisições, o limite diário de mensagens e o fato de só haver conteúdo de `end_user`.

### Respostas CORS

As rotas `/v1/widget/*` **saem do `CORSMiddleware` global** (que serve o painel com credenciais e a lista `KNOBRIDGE_CORS_ORIGINS`) e têm o seu tratamento, em `widget/cors.py`:

- **Preflight** (`OPTIONS`), com origem permitida e widget ativo: 204 com `Access-Control-Allow-Origin: <origem recebida>`, `Access-Control-Allow-Methods: GET, POST, OPTIONS`, `Access-Control-Allow-Headers: Authorization, Content-Type`, `Access-Control-Max-Age: 600` e `Vary: Origin`. Senão, as respostas dos passos 1 a 3 acima.
- **Demais respostas** (sucesso e erro depois do passo 2): `Access-Control-Allow-Origin: <origem recebida>`, `Vary: Origin` e `Access-Control-Expose-Headers: Retry-After`.
- **Nunca** `Access-Control-Allow-Credentials`: o widget não usa cookie. A sessão do painel não vale nessas rotas, e elas ignoram cookies.

## Limites de requisição

Janela fixa no Postgres, na tabela `rate_limit_counters` ([modelo-de-dados.md](modelo-de-dados.md#rate_limit_counters)), em `widget/rate_limit.py` (`RateLimiter`, com relógio injetado):

| Escopo (`limit`) | Conta | Janela | Limite | Onde se configura |
|---|---|---|---|---|
| `widget_request` | toda requisição pública (inclusive `OPTIONS`), por widget e IP | 60 s | 120 | `KNOBRIDGE_WIDGET_REQUESTS_PER_MINUTE` |
| `widget_conversation` | `POST .../conversations`, por widget e IP | 1 h | 20 | `KNOBRIDGE_WIDGET_CONVERSATIONS_PER_HOUR` |
| `widget_message_ip` | `POST .../messages`, por widget e IP | 1 h | 30 | `messages_per_ip_per_hour` do widget |
| `widget_message_day` | `POST .../messages`, por widget (todos os IPs) | 24 h | 1000 | `messages_per_day` do widget |
| `widget_ticket` | `POST .../ticket-requests`, por widget e IP | 1 h | 5 | `KNOBRIDGE_WIDGET_TICKETS_PER_HOUR` |

- **Janela fixa**: a primeira batida abre a janela (`window_ends_at = agora + janela`); dentro dela, cada batida soma 1; passou de `window_ends_at`, a próxima batida recomeça em 1. Uma instrução só, atômica: `INSERT … ON CONFLICT (key_hash) DO UPDATE … RETURNING hits, window_ends_at`, numa transação curta própria em modo de sistema (o contador fica gravado mesmo se a requisição falhar depois).
- **Estourou** (`hits > limite`): 429 `rate_limited`, `details: {limit: "<escopo>", retry_after: <segundos>}` e o header `Retry-After` com os segundos até `window_ends_at` (arredondado para cima, no mínimo 1). Batidas recusadas também contam (um flood continua barrado até a janela acabar).
- As mensagens conferem `widget_message_ip` e depois `widget_message_day`, **depois** de validar o corpo e o acesso à conversa e **antes** do embedding.
- **Chave do contador**: `HMAC-SHA256(chave derivada, "<escopo>|<widget_id>|<ip>")` em hex, com a chave derivada de `KNOBRIDGE_SECRET_KEY` por HKDF (`info` `knobridge/rate-limit/v1`). Sem HMAC, o SHA-256 de um IPv4 se reverte por força bruta. Em `widget_message_day`, o IP é vazio.
- **IP**: `request.client.host`, depois do tratamento dos cabeçalhos de proxy do uvicorn (`KNOBRIDGE_FORWARDED_ALLOW_IPS`; no compose, o nginx do frontend). IPv6 conta pelo prefixo `/64` (quem tem um `/64` troca de endereço à vontade).
- **Limpeza**: no máximo uma vez por hora por processo, o limitador apaga as linhas com `window_ends_at` de mais de 24 h atrás.
- Mudar o limite de um widget vale na próxima batida (a janela aberta continua).

## Rotas públicas

Todas sob `/v1/widget/{public_key}` (`api/widget_public.py`), com a [checagem de `Origin`](#checagem-de-origin) e o limite geral antes. Respostas com `Cache-Control: no-store`, exceto a configuração. Corpos em JSON (UTF-8). Fora do `CORSMiddleware` global e sem CSRF (não há cookie).

### Token de conversa (`kbv_`)

- Criar a conversa devolve `visitor_token` = `kbv_<secrets.token_urlsafe(32)>` (validado por `^kbv_[A-Za-z0-9_-]{43}$`) **uma única vez**. O servidor guarda só `conversations.visitor_token_hash` = SHA-256 hex do token inteiro.
- As rotas da conversa exigem `Authorization: Bearer kbv_…`. Ausente ou fora do formato: 401 `invalid_visitor_token` (com `WWW-Authenticate: Bearer`). Conversa inexistente, de outro widget, de outro workspace ou com hash diferente (comparado em tempo constante): 404 `not_found`, a mesma resposta nos quatro casos.
- O token não expira; vale enquanto a conversa existir. "Nova conversa" no widget só esquece o token no navegador. Não há rota para o visitante excluir a conversa nesta versão.
- O token nunca vai para log; logs das rotas públicas levam `workspace_id`, `widget_id` e `conversation_id`.

### `GET /config`

Lida pelo widget ao carregar. Resposta 200 `WidgetPublicConfig`, com `Cache-Control: private, max-age=60`:

```json
{
  "public_key": "kbp_3k9x2m4q7w8e1r5t6y0u2i4o",
  "product_name": "ERP",
  "language": "pt-BR",
  "title": "Ajuda do ERP",
  "greeting": "Olá! Como posso ajudar?",
  "placeholder": "Escreva sua pergunta",
  "mode": "bubble",
  "position": "bottom-right",
  "theme": "auto",
  "primary_color": "#2563eb",
  "feedback_enabled": true,
  "ticket_enabled": true,
  "identity_enabled": true,
  "level": "end_user",
  "question_max_chars": 8000
}
```

`title` já vem resolvido (o nome do produto quando o widget não tem título). `ticket_enabled` é o efetivo (`ticket_available`). `identity_enabled`: o widget tem segredo de assinatura. `language` é o do produto. Nada de coleções, modelo, limites nem custo.

### `POST /conversations`

Cria a conversa do visitante. O widget chama na **primeira pergunta**, não ao carregar. Corpo (até 8 KiB):

| Campo | Tipo | Regras |
|---|---|---|
| `identity` | texto ou `null` | Opcional: a [identidade assinada](#identidade-assinada). Inválida: 401 `widget_identity_invalid`. |
| `level` | texto | Opcional. Só `end_user` é aceito; `support` ou `product_dev`: 403 `level_not_allowed` com `details: {requested_level, max_level: "end_user", reason: "public_channel"}` (`levels/policy.py`); outro valor: 422. |

O servidor confere, nesta ordem: limite `widget_conversation`, identidade, nível pelo `check_turn` com o dono do widget (`product_inactive` vira 404 `widget_unavailable`; `level_not_configured`: 409, `details: {level: "end_user"}`). Grava a conversa com `channel = widget`, `widget_id`, `level = end_user`, `visitor_token_hash` e, com identidade válida, `visitor_external_id`, `visitor_name` e `visitor_email`.

Resposta 201:

```json
{
  "conversation": {
    "id": "…",
    "level": "end_user",
    "title": null,
    "visitor": {"name": "Ana Souza", "email": "ana@exemplo.com.br", "verified": true},
    "ticket_enabled": true,
    "created_at": "…"
  },
  "visitor_token": "kbv_…"
}
```

`visitor` é `null` sem identidade. Erros: 401 `widget_identity_invalid`, 403 `level_not_allowed`, 404 `widget_unavailable`, 409 `level_not_configured`, 422 `validation_error`, 429 `rate_limited`.

### `GET /conversations/{conversation_id}`

Para o widget reabrir o histórico ao recarregar a página. Parâmetros: `limit` (1 a 100, padrão 50) e `before` (opcional, uma `position`: só mensagens anteriores a ela). Resposta 200 (`WidgetConversationDetail`): os campos do objeto `conversation` acima (sem token), no mesmo nível de `messages` e `has_more`:

```json
{
  "messages": [
    {
      "id": "…", "position": 0, "role": "user", "content": "Como fecho o caixa?",
      "status": "completed", "citations": [], "created_at": "…", "feedback": null, "ticket_request": null
    },
    {
      "id": "…", "position": 1, "role": "assistant", "content": "Para fechar o caixa… [1]",
      "status": "completed", "citations": [{"index": 1, "title": "manual/caixa.md", "uri": "manual/caixa.md#L10-L42", "…": "…"}],
      "created_at": "…", "feedback": {"rating": "up", "comment": null}, "ticket_request": null
    }
  ],
  "has_more": false
}
```

- `messages`: as `limit` mensagens mais recentes (antes de `before`, se houver), **em ordem cronológica**; `has_more` diz se há anteriores.
- `status` é o efetivo (resposta `streaming` órfã aparece `interrupted`, [chat.md](chat.md#estados-das-mensagens)).
- **Sem** `model`, tokens, custo, latência, canal nem `error_code`: dados internos não vão ao visitante.
- `feedback`: o do visitante, `{rating, comment}` ou `null`. `ticket_request`: `WidgetTicketRequestOut` ou `null` ([Chamado](#post-conversationsconversation_idticket-requests)).
- `citations`: formato de [chat-sse.md](chat-sse.md#citations); no nível `end_user`, `evidence` é sempre `null`.

### `POST /conversations/{conversation_id}/messages`

Corpo `{"content": "…"}` (1 a 8000 caracteres sem os espaços das pontas; corpo até 64 KiB). Na ordem: token, conversa, limites `widget_message_ip` e `widget_message_day`, depois a rodada do chat ([chat.md](chat.md#orquestração-em-duas-fases)) com o **dono widget** (canal público, teto `end_user`), as coleções e a similaridade mínima do produto, o modelo, as instruções e o texto do nível `end_user`, e a regra 8.

Erros antes do stream, como JSON (com CORS): 401 `invalid_visitor_token`, 404 `not_found` ou `widget_unavailable` (widget ou produto desativado depois), 403 `level_not_allowed` (não acontece com `end_user`, mas a checagem roda), 409 `level_not_configured`, 422 `validation_error`, 429 `rate_limited` e os erros do provedor de embedding (422, 429, 502, 503 `provider_*`/`embedding_*`, como em [chat-sse.md](chat-sse.md#requisição)).

Resposta 200 `text/event-stream` com os eventos de [chat-sse.md](chat-sse.md) (`citations`, `delta`…, `done` ou `error`), com duas diferenças no canal `widget` ([chat-sse.md](chat-sse.md#no-canal-widget)):

- `done` traz `model`, `input_tokens`, `output_tokens` e `cost_usd` sempre `null` (o custo fica gravado; só não vai ao visitante);
- `ticket_requests_enabled` é o do widget (`ticket_available`), não só o do produto.

As mensagens ficam gravadas com `channel = widget`, `product_id`, `level = end_user` e `cost_usd`. Cliente que desconecta deixa a resposta `interrupted`, como no painel.

### `POST /conversations/{conversation_id}/messages/{message_id}/feedback`

Corpo `{"rating": "up" | "down", "comment": "…" | null}` (comentário até 2000 caracteres). Upsert: um feedback do visitante por mensagem (`feedback.user_id` nulo; [modelo-de-dados.md](modelo-de-dados.md#feedback)). Resposta 200 `{"rating", "comment"}`. Erros: 404 `not_found` (mensagem fora da conversa), 409 `feedback_disabled` (o widget desligou o feedback), 422 `feedback_target_invalid` (não é resposta do assistente) ou `validation_error`. O feedback aparece na visão administrativa como o do painel.

### `POST /conversations/{conversation_id}/ticket-requests`

Pede um chamado a partir de uma resposta, como no painel ([Pedido no chat](chamados.md#pedido-no-chat)), **sem preview e sem resumo gerado por LLM** (um visitante anônimo não dispara LLM fora da pergunta): o widget preenche o resumo com a pergunta e o visitante edita.

| Campo | Tipo | Regras |
|---|---|---|
| `message_id` | uuid | Resposta do assistente nesta conversa, com status `no_source` ou `completed` (senão, 422 `validation_error`). |
| `summary` | texto | 1 a 2000 caracteres. |
| `email` | texto ou `null` | Obrigatório quando a conversa não tem e-mail da identidade assinada (422 `validation_error`); e-mail válido, até 320 caracteres. Com e-mail da identidade, é ignorado. |
| `name` | texto ou `null` | Opcional, até 200 caracteres. Com nome da identidade, é ignorado. Sem nenhum, o e-mail ocupa `requester.name` no payload. |

Na ordem: token, conversa, limite `widget_ticket`, `ticket_available` (senão, 409 `ticket_webhook_not_configured`), mensagem, pedido único por mensagem (409 `ticket_request_exists`). Grava o pedido `pending` com `user_id` nulo e inicia a entrega, com o payload de [Pedidos vindos do MCP e do widget](chamados.md#pedidos-vindos-do-mcp-e-do-widget) (`channel: "widget"`, `requester.verified` = a conversa tem identidade assinada, `requester.external_id` = o `sub` dela). Resposta 202 `WidgetTicketRequestOut`:

```json
{"id": "…", "message_id": "…", "status": "pending", "external_ticket_id": null, "external_url": null, "created_at": "…", "delivered_at": null}
```

**`GET .../ticket-requests/{ticket_request_id}`**: 200 `WidgetTicketRequestOut`, para o widget mostrar o número e o link do chamado quando o destino os devolver; pedido de outra conversa: 404 `not_found`. Sem `attempts` nem `error_code` (o visitante vê só `pending`, `delivered` ou `failed`).

### Corpos e limites

| Rota | Corpo máximo |
|---|---|
| `POST .../conversations` | 8 KiB |
| `POST .../messages` | 64 KiB |
| `POST .../feedback` | 8 KiB |
| `POST .../ticket-requests` | 16 KiB |

Pelo `BodyLimitMiddleware` (413 `payload_too_large`, com CORS quando a origem é permitida).

### Erros novos

| `code` | HTTP | Quando |
|---|---|---|
| `widget_origin_not_allowed` | 403 | `Origin` ausente ou fora da lista (sem CORS). |
| `widget_unavailable` | 404 | Widget ou produto inativo, ou workspace suspenso. |
| `invalid_visitor_token` | 401 | Token ausente ou fora do formato. |
| `widget_identity_invalid` | 401 | Identidade recusada; `details.reason` ([Verificação](#verificação)). |
| `rate_limited` | 429 | Limite estourado; `details: {limit, retry_after}`, header `Retry-After`. |
| `feedback_disabled` | 409 | Feedback desligado no widget. |
| `widget_name_taken` | 409 | Painel: nome repetido. |
| `widget_product_invalid`, `widget_origin_invalid` | 422 | Painel: produto ou origens inválidos. |

## Nível: sempre `end_user`

- A conversa do widget tem `level = end_user`, fixo. O dono é o widget, num canal público: o teto vem de `levels/policy.py` com `public_channel=True` (`ceiling(end_user, …)`, `reason = public_channel`). A identidade assinada **não** muda o teto (D5).
- A busca filtra `chunks.min_level = end_user` no SQL; as instruções e o modelo são os do nível `end_user` do workspace; a citação de conhecimento vai sem evidências.
- Pedir outro nível na criação dá 403 `level_not_allowed` (`reason: public_channel`). As demais rotas não aceitam `level`.

## Identidade assinada

Opcional (D3). O **servidor** do sistema hospedeiro, que já sabe quem está logado, assina a identidade com o segredo `kbs_` e a entrega na página. O KnoBridge verifica e grava nome, e-mail e id externo na conversa e no chamado. Ela só identifica: não autoriza nada além do que o visitante anônimo já pode (D5).

### Formato

```text
v1.<payload>.<assinatura>
```

- `payload`: o JSON das reivindicações em UTF-8, codificado em **base64url sem `=`** (RFC 4648, seção 5).
- `assinatura`: `HMAC-SHA256(chave = segredo kbs_ inteiro em UTF-8, mensagem = "v1." + payload)` em **hexadecimal minúsculo** (64 caracteres). A mensagem é o texto exato enviado (o prefixo `v1.` e o payload codificado), então não há canonicalização de JSON: a ordem das chaves e os espaços são os do hospedeiro.
- Identidade inteira até 4096 caracteres; payload decodificado até 2048 bytes.

| Reivindicação | Tipo | Regras |
|---|---|---|
| `sub` | texto | **Obrigatório**, 1 a 200 caracteres: o id do usuário no sistema hospedeiro. |
| `name` | texto | Opcional, 1 a 200 caracteres. |
| `email` | texto | Opcional, e-mail válido, até 320 caracteres. |
| `iat` | inteiro | **Obrigatório**: emissão, em segundos Unix. |
| `exp` | inteiro | **Obrigatório**: validade, em segundos Unix; `exp > iat` e `exp - iat ≤ 86 400` (24 h). |

Reivindicações desconhecidas são ignoradas.

### Verificação

Em `widget/identity.py`, com relógio injetado, nesta ordem (a assinatura antes de ler as reivindicações):

1. o widget não tem segredo → `not_configured`;
2. três partes separadas por `.`, a primeira `v1`, payload base64url válido, assinatura com 64 caracteres `[0-9a-f]`, tamanhos dentro dos limites → senão `malformed`;
3. `hmac.compare_digest` da assinatura calculada com a recebida → senão `signature`;
4. o payload decodificado é um objeto JSON com as reivindicações nos tipos e tamanhos da tabela, `exp > iat` → senão `claims`;
5. `exp - iat ≤ 86 400` → senão `lifetime_too_long`;
6. `agora ≥ iat - tolerância` → senão `not_yet_valid`;
7. `agora ≤ exp + tolerância` → senão `expired`.

Tolerância de relógio: `KNOBRIDGE_WIDGET_IDENTITY_CLOCK_SKEW`, em segundos, padrão **60**. Falha: 401 `widget_identity_invalid` com `details: {reason}`. Log `widget_identity_rejected` com `widget_id` e `reason`, nunca a identidade.

A identidade é verificada **só na criação da conversa** e fica gravada nela. As perguntas seguintes usam só o token de conversa. Se o visitante trocar (outro `sub`), o widget abre outra conversa ([Histórico no navegador](#histórico-no-navegador)).

### Exemplo reproduzível

Valores **de teste**, usados também nos testes da F3.2 (nunca em produção):

| Item | Valor |
|---|---|
| Segredo | `kbs_teste-NAO-use-em-producao-0123456789abcdefg` |
| Payload (JSON, como enviado) | `{"sub":"cliente-42","name":"Ana Souza","email":"ana@exemplo.com.br","iat":1791800000,"exp":1791803600}` |
| `iat`, `exp` | 2026-10-12T10:13:20Z e 2026-10-12T11:13:20Z |
| Payload em base64url | `eyJzdWIiOiJjbGllbnRlLTQyIiwibmFtZSI6IkFuYSBTb3V6YSIsImVtYWlsIjoiYW5hQGV4ZW1wbG8uY29tLmJyIiwiaWF0IjoxNzkxODAwMDAwLCJleHAiOjE3OTE4MDM2MDB9` |
| Assinatura | `880cf2b97633c3f6e883162cbdb90e927e79642940f40d8f81f79a9e0b10bec2` |

Identidade completa:

```text
v1.eyJzdWIiOiJjbGllbnRlLTQyIiwibmFtZSI6IkFuYSBTb3V6YSIsImVtYWlsIjoiYW5hQGV4ZW1wbG8uY29tLmJyIiwiaWF0IjoxNzkxODAwMDAwLCJleHAiOjE3OTE4MDM2MDB9.880cf2b97633c3f6e883162cbdb90e927e79642940f40d8f81f79a9e0b10bec2
```

Com o relógio em 2026-10-12T10:30:00Z, ela é válida; em 2026-10-12T11:14:21Z (61 s depois de `exp`), `expired`; em 2026-10-12T10:12:19Z (61 s antes de `iat`), `not_yet_valid`. Trocar um caractere do payload dá `signature`. A assinatura acima foi calculada com os dois trechos abaixo (Python e Node), que dão o mesmo resultado.

No servidor do hospedeiro, Python:

```python
import base64, hashlib, hmac, json, os, time

def knobridge_identity(sub: str, name: str | None, email: str | None, ttl: int = 3600) -> str:
    now = int(time.time())
    claims = {"sub": sub, "name": name, "email": email, "iat": now, "exp": now + ttl}
    claims = {k: v for k, v in claims.items() if v is not None}
    raw = json.dumps(claims, separators=(",", ":"), ensure_ascii=False).encode()
    payload = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    key = os.environ["KNOBRIDGE_WIDGET_SIGNING_SECRET"].encode()  # kbs_…
    signature = hmac.new(key, f"v1.{payload}".encode(), hashlib.sha256).hexdigest()
    return f"v1.{payload}.{signature}"
```

Node:

```js
import { createHmac } from "node:crypto";

export function knobridgeIdentity({ sub, name, email }, ttl = 3600) {
  const iat = Math.floor(Date.now() / 1000);
  const payload = Buffer.from(JSON.stringify({ sub, name, email, iat, exp: iat + ttl })).toString("base64url");
  const signature = createHmac("sha256", process.env.KNOBRIDGE_WIDGET_SIGNING_SECRET).update(`v1.${payload}`).digest("hex");
  return `v1.${payload}.${signature}`;
}
```

(`JSON.stringify` omite campos `undefined`.) A identidade vai para a página no atributo `identity` do elemento, gerada a cada carregamento de página.

## Embutir o elemento

### Onde o JS é servido

- **Caminho estável**: `https://<instância>/widget/v1/knobridge-chat.js`. `v1` é a versão maior do contrato do elemento; mudanças compatíveis são publicadas no mesmo caminho. Uma versão incompatível ganharia `/widget/v2/…`, mantendo a `v1`.
- **Um único arquivo**, script clássico (IIFE) com Lit embutido, sem `import` dinâmico, sem CSS externo, sem fontes externas, sem `eval`. Registra `knobridge-chat` com `customElements.define` só se ainda não existir (carregar duas vezes não quebra). Orçamento: até 60 KiB com gzip (a F4.1 mede e relata).
- Servido pelo contêiner do frontend (nginx), a partir do build de `widget/` copiado para `/usr/share/nginx/html/widget/v1/` na imagem (F4.2; no compose, `additional_contexts` com `widget: ./widget` no serviço `frontend`). Bloco próprio no `nginx.conf`, **nunca** o fallback do SPA (`try_files $uri =404`), com:

| Header | Valor |
|---|---|
| `Content-Type` | `text/javascript; charset=utf-8` |
| `Cache-Control` | `public, max-age=300` (caminho estável, não imutável) |
| `Access-Control-Allow-Origin` | `*` |
| `Cross-Origin-Resource-Policy` | `cross-origin` |
| `X-Content-Type-Options` | `nosniff` |

- **Base da API**: o elemento usa a origem do próprio script (`new URL(document.currentScript.src).origin`, lida quando o script executa) e chama `<origem>/v1/widget/<chave>/…`. O atributo `api-base` sobrepõe (instância com a API noutro host).

### Trecho para copiar

Modo balão:

```html
<script src="https://kb.empresa.com/widget/v1/knobridge-chat.js" defer></script>
<knobridge-chat widget-key="kbp_3k9x2m4q7w8e1r5t6y0u2i4o"></knobridge-chat>
```

Modo embutido (o hospedeiro dá a altura):

```html
<knobridge-chat widget-key="kbp_3k9x2m4q7w8e1r5t6y0u2i4o" mode="inline" style="height: 600px"></knobridge-chat>
```

Com identidade assinada (gerada no servidor do hospedeiro a cada página):

```html
<knobridge-chat widget-key="kbp_3k9x2m4q7w8e1r5t6y0u2i4o" identity="v1.eyJ….880c…"></knobridge-chat>
```

Para uma CSP restritiva no site: `script-src` e `connect-src` com a origem da instância. O widget não usa estilos nem scripts inline no documento do hospedeiro (os estilos ficam no Shadow DOM, por folhas construídas do Lit).

### Atributos

Atributos de aparência **sobrepõem** a configuração do painel; sem eles, vale a do `GET /config`. Cada atributo tem a propriedade equivalente em camelCase.

| Atributo | Valores | Padrão |
|---|---|---|
| `widget-key` | `kbp_…` | **Obrigatório.** Sem ele (ou fora do formato), o elemento não renderiza nada e emite `knobridge-error` (`code: widget_key_missing`). |
| `api-base` | URL `http(s)` sem caminho | Origem do script. |
| `mode` | `bubble`, `inline` | O do painel. |
| `position` | `bottom-right`, `bottom-left` | O do painel. |
| `theme` | `light`, `dark`, `auto` | O do painel. |
| `primary-color` | `#RRGGBB` | O do painel. |
| `title` | texto | O do painel. |
| `greeting` | texto | O do painel. |
| `placeholder` | texto | O do painel. |
| `identity` | identidade `v1.…` | Nenhuma (visitante anônimo). |
| `open` | booleano (presença) | Ausente: o balão começa fechado. Reflete o estado (o elemento põe e tira o atributo). Ignorado no modo `inline`. |
| `storage` | `local`, `session`, `none` | `local` ([Histórico no navegador](#histórico-no-navegador)). |
| `lang` | `pt-BR` | `pt-BR` (único idioma nesta versão; textos em `widget/src/i18n/`, prontos para outros). |

Valor inválido num atributo é ignorado (vale o do painel), com um aviso no `console.warn` só em desenvolvimento (build de produção sem `console`).

### Métodos

| Método | Efeito |
|---|---|
| `open()`, `close()`, `toggle()` | Abre, fecha ou alterna o balão (sem efeito no modo `inline`). |
| `newConversation()` | Esquece a conversa atual no navegador e volta à saudação. |
| `setIdentity(identity: string \| null)` | Troca a identidade (igual a mudar o atributo). Com outro `sub`, a próxima pergunta abre conversa nova. |

### Eventos

`CustomEvent` com `bubbles: true` e `composed: true`, disparados no elemento. `detail` nunca traz o texto da pergunta, da resposta, nem a identidade.

| Evento | `detail` | Quando |
|---|---|---|
| `knobridge-ready` | `{mode, ticketEnabled, feedbackEnabled}` | Configuração carregada. |
| `knobridge-open`, `knobridge-close` | `{}` | Balão aberto ou fechado. |
| `knobridge-message-sent` | `{conversationId, messageId}` | Pergunta aceita (evento `citations` recebido). |
| `knobridge-answer` | `{conversationId, messageId, status, citations}` | Resposta terminou (`status` = `completed`, `no_source`, `failed` ou `interrupted`; `citations` = quantidade). |
| `knobridge-feedback` | `{messageId, rating}` | Feedback gravado. |
| `knobridge-ticket-requested` | `{ticketRequestId, messageId}` | Pedido de chamado aceito (202). |
| `knobridge-error` | `{code, status}` | Falha: `code` da API (`widget_unavailable`, `rate_limited`…) ou do cliente (`widget_key_missing`, `network_error`); `status` HTTP ou `null`. |

### Aparência

Shadow DOM aberto. Variáveis CSS lidas no elemento (o hospedeiro define em `knobridge-chat { … }`); elas vencem os atributos e o painel:

| Variável | Padrão |
|---|---|
| `--knobridge-primary` | `primary_color` |
| `--knobridge-primary-contrast` | branco ou preto, o de maior contraste com a primária |
| `--knobridge-background` | `#ffffff` (claro) / `#111827` (escuro) |
| `--knobridge-foreground` | `#111827` / `#f9fafb` |
| `--knobridge-muted` | `#6b7280` / `#9ca3af` |
| `--knobridge-border` | `#e5e7eb` / `#374151` |
| `--knobridge-radius` | `12px` |
| `--knobridge-font-family` | `inherit` (a fonte do site) |
| `--knobridge-font-size` | `14px` |
| `--knobridge-z-index` | `2147483000` (balão) |
| `--knobridge-panel-width` | `380px` (balão; em tela de até 480 px, a largura toda) |
| `--knobridge-panel-height` | `600px` (balão; limitado a `100dvh - 32px`) |

Partes estilizáveis com `::part()`: `launcher`, `panel`, `header`, `messages`, `message`, `citations`, `composer`, `input`, `send`, `ticket-form`.

Modos: **`bubble`**, botão redondo fixo no canto (`position`) que abre um painel sobre a página; **`inline`**, o painel inteiro no fluxo da página, com 100% da largura e da altura do elemento (mínimo de 360 px de altura), sem botão.

### Comportamento

- **Carregar**: lê `GET /config`. Falhou (404, 403, rede): no `bubble`, não mostra o botão; no `inline`, mostra "Chat indisponível no momento." Emite `knobridge-error`.
- **Primeira pergunta**: cria a conversa (com `identity`, se houver), guarda o token e envia a pergunta.
- **Resposta**: mostra a pergunta na hora, um indicador "Digitando…" até o primeiro `delta`, e o texto crescendo a cada `delta`. O campo fica desabilitado até `done` ou `error`. Pergunta acima de `question_max_chars` não é enviada (contador de caracteres).
- **Texto da resposta**: renderizado com um subconjunto seguro de Markdown (parágrafos, listas, negrito, itálico, código em linha e em bloco, links `http`/`https` com `target="_blank" rel="noopener noreferrer"`). **Nunca** HTML do servidor como HTML: todo texto vai escapado (sem `innerHTML` com conteúdo da API). Os marcadores `[n]` viram botões que levam à citação `n`.
- **Citações**: lista "Fontes" abaixo da resposta, `[n] título`; cada item abre um detalhe com o `snippet` e, quando `url` é `http(s)`, o link "Abrir" (nova aba). Sem `url`, só o detalhe. Toda resposta `completed` tem citações (regra 8).
- **Sem fonte** (`status: no_source`): a resposta é a mensagem de "sem fonte" do produto; com `ticket_enabled`, aparece logo abaixo o botão "Abrir chamado".
- **Feedback** (`feedback_enabled`): 👍/👎 em respostas `completed` e `no_source`; 👎 abre um campo opcional de comentário. O estado volta ao recarregar (`feedback` na leitura).
- **Abrir chamado** (`ticket_enabled`): botão em respostas `no_source` e no menu das `completed`. Formulário com o resumo (preenchido com a pergunta, editável), e-mail (obrigatório e oculto quando a identidade tem e-mail) e nome (opcional, oculto quando a identidade tem nome), e a frase "Vamos enviar sua pergunta, este resumo e a conversa para a equipe de suporte." Depois do 202: "Chamado solicitado". O widget consulta o pedido a cada 10 s, no máximo 6 vezes, e mostra o número e o link quando chegam.
- **Erros**: 429 mostra "Muitas mensagens em pouco tempo. Tente de novo em N minutos." (de `Retry-After`); evento `error` ou falha de rede: "Não consegui responder agora. Tente de novo." com o botão "Tentar de novo" (reenvia a pergunta).
- **Cabeçalho**: título, botão "Nova conversa" e, no `bubble`, "Fechar".

### Histórico no navegador

- Com `storage="local"` (padrão), o widget guarda em `localStorage`, na chave `knobridge:v1:<widget-key>`, só: `{"conversation_id", "visitor_token", "identity_sub", "saved_at"}`. Com `session`, em `sessionStorage` (some ao fechar a aba). Com `none`, em memória (some ao recarregar).
- **As mensagens não ficam no navegador**: ao carregar, com uma conversa guardada, o widget lê `GET /conversations/{id}` e mostra o histórico. 401 ou 404: esquece a conversa guardada e começa do zero.
- `identity_sub` é o `sub` da identidade atual (lido do payload, sem verificar; a verificação é do servidor) ou `null`. Se a identidade atual tem outro `sub` (ou passou de anônima para identificada, ou o contrário), o widget ignora a conversa guardada e abre outra na próxima pergunta, para uma pessoa nunca ver a conversa de outra no mesmo navegador.
- "Nova conversa" apaga a entrada. Todo acesso ao armazenamento fica em `try/catch`: bloqueado (modo privado, política do site), o widget funciona como `none`.

## Prévia no painel

A tela do widget (F4.3) mostra a prévia ao vivo carregando o mesmo `/widget/v1/knobridge-chat.js` da instância e um `<knobridge-chat>` com a chave do widget e os campos de aparência ainda não salvos como atributos (`mode="inline"` na área da prévia, para caber na tela). As requisições saem da origem da instância, sempre permitida. **A prévia conversa de verdade**: grava conversas com `channel = widget`, conta nos limites e no uso, e a tela avisa isso. Widget ainda não criado não tem prévia (falta a chave).

## Privacidade

- **No navegador**: só o ponteiro da conversa (id, token, `sub` da identidade, data), no armazenamento do próprio site; nenhum cookie, nenhum armazenamento de terceiro, nenhuma requisição além da instância, nenhuma métrica, nenhum identificador de dispositivo. A identidade assinada fica no atributo que o hospedeiro pôs na página.
- **No servidor**: as perguntas e respostas ficam gravadas como as dos outros canais (visíveis a owner e admin em **Conversas**). Nome, e-mail e id externo só existem com identidade assinada (na conversa) ou quando o visitante os digita para abrir chamado (no corpo do pedido, apagado depois da entrega, e no destino do webhook). O IP **não é gravado**: entra só no HMAC da chave do contador de limite, apagado até 24 h depois da janela.
- **Logs** das rotas públicas: `workspace_id`, `widget_id`, `conversation_id`, rota e status; nunca pergunta, resposta, token, identidade, e-mail nem IP. (Logs de acesso do proxy à frente da instância são responsabilidade de quem opera.)
- O hospedeiro informa aos seus usuários, na política de privacidade dele, que o chat é atendido pelo KnoBridge da empresa e o que é enviado.

## Acessibilidade

Meta: WCAG 2.2 nível AA.

- **Botão do balão**: `<button>` com `aria-label` "Abrir chat de ajuda" ou "Fechar chat de ajuda", `aria-expanded` e `aria-controls` apontando o painel.
- **Painel**: `role="dialog"`, `aria-modal="false"` (não prende a página), `aria-labelledby` no título. Ao abrir, o foco vai para o campo de pergunta; `Esc` fecha o balão e devolve o foco ao botão.
- **Mensagens**: contêiner com `role="log"` e `aria-live="polite"`; durante o stream, a resposta tem `aria-busy="true"` e é anunciada inteira quando termina (não a cada `delta`). Cada mensagem tem um rótulo de quem fala ("Você", "Assistente") para leitores de tela.
- **Campo de pergunta**: `<textarea>` com `<label>` (visualmente oculto) e o contador de caracteres ligado por `aria-describedby`. `Enter` envia; `Shift+Enter` quebra a linha.
- **Citações**: os `[n]` são `<button>` com `aria-label` "Fonte n: <título>"; a lista de fontes é navegável por teclado, e o detalhe usa `aria-expanded`.
- **Feedback**: botões com `aria-label` ("Resposta útil", "Resposta não útil") e `aria-pressed`.
- **Formulário de chamado**: rótulos, erros ligados por `aria-describedby` e anunciados, foco no primeiro campo com erro.
- **Teclado**: tudo alcançável por `Tab` em ordem lógica, foco sempre visível (contorno de 2 px com a cor primária ou a de contraste).
- **Contraste**: texto e controles com 4,5:1 (texto) e 3:1 (componentes) nos dois temas; `--knobridge-primary-contrast` é escolhido pelo contraste com a primária. A tela de configuração avisa quando a cor primária não alcança 3:1 contra o fundo.
- **Movimento**: animações desligadas com `prefers-reduced-motion: reduce`.
- **Alvos**: controles com pelo menos 24 × 24 px.
- Testes da F4.1 cobrem teclado, foco, ARIA e o anúncio do fim da resposta.

## Uso, custos e visão administrativa

- Conversas e mensagens do widget têm `channel = widget` e `widget_id`. **Conversas** mostra "Widget · <nome do widget>" e, com identidade assinada, o nome e o e-mail do visitante (senão, "Visitante"); filtros por canal (Widget) e por widget ([chat.md](chat.md#visão-administrativa)).
- **Uso e custos**: a linha `widget` em `group_by=channel` e o agrupamento `group_by=widget` (uma linha por widget com resposta no período) ([uso-e-custos.md](uso-e-custos.md#canais-mcp-e-widget)).

## Variáveis de ambiente

| Variável | Padrão | Uso |
|---|---|---|
| `KNOBRIDGE_WIDGET_REQUESTS_PER_MINUTE` | 120 | Limite `widget_request`. |
| `KNOBRIDGE_WIDGET_CONVERSATIONS_PER_HOUR` | 20 | Limite `widget_conversation`. |
| `KNOBRIDGE_WIDGET_TICKETS_PER_HOUR` | 5 | Limite `widget_ticket`. |
| `KNOBRIDGE_WIDGET_IDENTITY_CLOCK_SKEW` | 60 | Tolerância de relógio da identidade, em segundos (0 a 600). |

Inteiros ≥ 1 (a tolerância, ≥ 0); fora disso, erro de settings na subida. Entram no `settings.py` e no `.env.example` na F3.1 (os três limites) e na F3.2 (a tolerância).

## Testes previstos

- F3.1: CRUD com papéis (admin passa, editor recebe 403); segredo mostrado só na criação e nunca na leitura; origens válidas e inválidas com cada `reason`; `Origin` fora da lista recusado (403 sem CORS) e preflight com origem permitida; limite com relógio injetado (abre, soma, estoura com `Retry-After`, recomeça depois da janela); RLS e isolamento (o workspace B não vê nem usa o widget do A).
- F3.2: sempre `end_user` (pedido `support` dá 403 `public_channel`; trecho `support` nunca sai); outro token não lê a conversa; identidade com o exemplo desta spec (válida, `expired`, `not_yet_valid`, `signature`, `lifetime_too_long`, `not_configured`); o chamado leva nome e e-mail da identidade ou os digitados; limites nas mensagens; `done` sem modelo nem custo; isolamento.
- F4.1 e F4.2: render dos dois modos, streaming, citações, histórico (recarregar, outro `sub`, armazenamento bloqueado), feedback, chamado, erros e acessibilidade; build em um arquivo com o tamanho medido.

## Referências

- Custom Elements e Shadow DOM: <https://html.spec.whatwg.org/multipage/custom-elements.html> e <https://dom.spec.whatwg.org/#shadow-trees>
- Lit: <https://lit.dev/docs/>
- Vite, modo biblioteca: <https://vite.dev/guide/build#library-mode>
- CORS (Fetch Standard): <https://fetch.spec.whatwg.org/#http-cors-protocol>
- `document.currentScript`: <https://html.spec.whatwg.org/multipage/dom.html#dom-document-currentscript>
- HMAC (RFC 2104): <https://www.rfc-editor.org/rfc/rfc2104>
- Base64url (RFC 4648, seção 5): <https://www.rfc-editor.org/rfc/rfc4648#section-5>
- `Retry-After` (RFC 9110): <https://www.rfc-editor.org/rfc/rfc9110#field.retry-after>
- WCAG 2.2: <https://www.w3.org/TR/WCAG22/>
- WAI-ARIA, `log` e regiões vivas: <https://www.w3.org/TR/wai-aria-1.2/#log>
