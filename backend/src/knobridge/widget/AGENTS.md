# backend/src/knobridge/widget/

**Função**: o widget embutível de um produto, canal público que responde sempre no nível `end_user` ([widget.md](../../../../docs/specs/widget.md), [ADR 0009](../../../../docs/adr/0009-canais-mcp-e-widget.md)). Plano 0010: a F3.1 entregou modelo, chaves, gestão no painel, origens e CORS, limite de requisições e a configuração pública; a F3.2 traz a conversa do visitante (token `kbv_`, identidade assinada, rodada, feedback e chamado).

**Entra aqui**:
- `models.py`: `Widget` (`widgets`: produto fixo, nome único no workspace, `public_key` `kbp_` única na instância e em claro, `allowed_origins` `text[]` de 1 a 50, aparência (`WidgetMode`, `WidgetPosition`, `WidgetTheme`, cor `#rrggbb` minúscula, título, saudação, placeholder), recursos, limites de mensagens e o segredo `kbs_` cifrado com `signing_secret_created_at`), com RLS forçada e a política padrão; `RateLimitCounter` (`rate_limit_counters`: `key_hash` HMAC, `hits`, `window_ends_at`; só modo de sistema); os padrões e limites da spec; `REFERENCED_MODELS`.
- `keys.py`: `generate_public_key`/`is_public_key` (`^kbp_[a-z0-9]{24}$`), `generate_signing_secret` (`kbs_` + `token_urlsafe(32)`), `seal_signing_secret`/`open_signing_secret` (`SecretBox` com `SIGNING_SECRET_KEY_INFO`, dados associados `widget_signing_secret:<workspace_id>:<id>`).
- `origins.py`: `normalize_origins` (minúsculas, sem porta padrão, sem repetição; 422 `widget_origin_invalid` com `details.origins[{origin, reason}]`: `malformed`, `scheme_not_allowed`, `path_not_allowed`, `wildcard_not_allowed`, `too_long`, `duplicate`), `request_origin` (o header `Origin`), `instance_origin` (de `KNOBRIDGE_PUBLIC_BASE_URL`) e `origin_allowed` (exata, curinga `*.` no primeiro rótulo para qualquer subdomínio e nunca o domínio raiz, e a origem da instância sempre).
- `service.py`: `WidgetService(clock, box)`: listar (por nome; `product_id`, `active`, `query`; duas consultas), `get`, `create`, `update` (`EDITABLE_FIELDS`; `product_id` não muda; título vazio vira `None`; audita só o que mudou), `delete` (conta as conversas; elas saem em cascata), `rotate_signing_secret` (devolve o segredo uma vez) e `remove_signing_secret` (idempotente); erros `widget_name_taken` (409) e `widget_product_invalid` (422); auditoria `widget.*` sem segredo.
- `rate_limit.py`: `RateLimiter(clock, secret_key=)` com `hit` (um `INSERT … ON CONFLICT … RETURNING` atômico em janela fixa; recusadas também contam), `check` (o `hit` numa transação própria em modo de sistema, confirmada mesmo quando recusa) e a limpeza de janelas vencidas há mais de 24 h no máximo uma vez por hora; `RateLimitScope`, `RateLimit`, `widget_request_limit`, `client_bucket` (IPv6 pelo `/64`) e `RateLimitedError` (429 `rate_limited`, `details {limit, retry_after}`, `Retry-After`). A F3.2 usa o mesmo limitador para conversas, mensagens e chamados.
- `public.py`: os passos de toda rota pública (`resolve_public_widget` em modo de sistema, 404 `not_found`; `accepted_origin`, 403 `widget_origin_not_allowed`; `ensure_available`, 404 `widget_unavailable`), `PublicWidget` (widget, produto, estado do workspace, `ticket_available`) e `QUESTION_MAX_CHARS`.
- `cors.py`: `PanelCORSMiddleware` (o CORS global do painel, fora de `/v1/widget/*`), `WidgetCORSMiddleware` (cabeçalhos CORS só depois de `allow_origin`, nunca credenciais) e `PREFLIGHT_HEADERS`.

**Não entra aqui**: rotas e schemas (`api/widgets.py` no painel, `api/widget_public.py` públicas), o motor do chat (`conversations/`), o Web Component (`widget/` na raiz do repositório), migrações (`backend/migrations/`).

**Convenções locais**:
- A chave pública é buscada só em modo de sistema; o resto da requisição pública roda no workspace do widget. Chave desconhecida e origem recusada respondem sem CORS; daí em diante, com CORS para a origem recebida.
- O segredo `kbs_` nunca é gravado em claro, logado, auditado nem devolvido depois da criação; o IP nunca é gravado (entra só no HMAC da chave do contador).
- `conversations/` não importa este pacote: `conversations.widget_id` aponta para `widgets` pelo nome, e `api/conversations.py` carrega `Widget` (`REFERENCED_MODELS`).
- Relógio sempre injetado (`Clock`); mudou modelo: migração nova e [modelo de dados](../../../../docs/specs/modelo-de-dados.md#widget-e-limite-de-requisições) na mesma entrega.

**Como testar**: de `backend/`, `uv run pytest tests/widget tests/api/test_widgets.py tests/api/test_widget_public.py` (exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [tests/widget/AGENTS.md](../../../tests/widget/AGENTS.md); [api/AGENTS.md](../api/AGENTS.md); [ADR 0003](../../../../docs/adr/0003-segredos-cifrados.md).
