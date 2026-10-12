# backend/src/knobridge/tickets/

**Função**: chamados de qualquer sistema como fonte do chat e o pedido de chamado que o chat envia quando não sabe responder ([ADR 0006](../../../../docs/adr/0006-chamados-por-push.md)). Contrato em [chamados.md](../../../../docs/specs/chamados.md). Hoje só o modelo de dados (plano 0005, F1.2); validação, caixa de entrada, conector interno `tickets`, anonimização, Markdown e o webhook vêm nas próximas subfases.

**Entra aqui**:
- `models.py`: `IngestToken` (`ingest_tokens`: um por fonte `tickets`, `token_prefix` único na instância, `token_hash` SHA-256 hex, `issued_at` do token atual, `created_by`), `TicketInboxItem` (`ticket_inbox`: uma entrada por `(source_id, external_id)`, `state`, `payload` só em `pending`, `content_hash` nulo em lápide, `ticket_updated_at` (o `updated_at` do chamado ou o `deleted_at` da lápide), `indexed_hash`, `received_at`, `processed_at`, `last_error`) e `TicketRequest` (`ticket_requests`: conversa, mensagem (única), assistente, usuário, `status`, `attempts`, `body` exato do webhook só em `pending`, `external_ticket_id`, `external_url`, `error_code`, `last_http_status`, `last_error`, `delivered_at`), com os enums `TicketInboxState` e `TicketRequestStatus`.
- `webhook_secret.py`: a cifra do segredo `kbw_` do webhook do assistente (`TICKET_WEBHOOK_KEY_INFO`, dados associados `assistant_ticket_webhook:<workspace_id>:<assistant_id>`), `seal_webhook_secret` e `open_webhook_secret`.

**Não entra aqui**: a fonte (`Source`, `SourceKind.TICKETS`, `TicketsSourceConfig`, `TicketStatus`), `RunTrigger.INGEST` e `DocumentKind.TICKET` (ficam em `ingestion/`); as colunas do webhook (em `Assistant`, `assistants/`); routers e schemas (`api/`); workflows (`workers/`); migrações (`backend/migrations/`).

**Convenções locais**:
- Este pacote pode importar `ingestion/`, `assistants/` e `conversations/`; nenhum deles importa este.
- Três tabelas com RLS forçada e a política padrão de workspace. A busca do token de envio roda em `system_session` (o workspace ainda não é conhecido) só por `token_prefix`; o resto da requisição roda no escopo do workspace da fonte.
- Referências compostas `(workspace_id, <pai>_id)`, todas `ON DELETE CASCADE`: excluir a fonte apaga o token e a caixa de entrada; excluir a conversa, a mensagem ou o assistente apaga os pedidos.
- O token de envio e o segredo do webhook nunca são gravados em claro nem logados; só `token_prefix` e o texto cifrado.
- `payload` usa `JSONB(none_as_null=True)`: `None` grava `NULL` de SQL, que os `CHECK`s de estado exigem.
- Mudou modelo: migração nova e [modelo de dados](../../../../docs/specs/modelo-de-dados.md) na mesma entrega.

**Como testar**: de `backend/`, `uv run pytest tests/tickets` (Postgres real; exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [ingestion/AGENTS.md](../ingestion/AGENTS.md); [assistants/AGENTS.md](../assistants/AGENTS.md); [tests/tickets/AGENTS.md](../../../tests/tickets/AGENTS.md).
