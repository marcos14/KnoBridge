# widget/src/api/

**Função**: o fio com a instância: cliente das rotas públicas `/v1/widget/{kbp_}/...` (`client.ts`), leitor de `text/event-stream` sobre `fetch` (`sse.ts`) e os tipos do fio (`types.ts`).

**Entra aqui**: chamadas HTTP, leitura do SSE, conversão de erros para `ApiError` (`code` da API ou `network_error`, `status` e `retryAfter` do `Retry-After`).
**Não entra aqui**: estado da conversa e regras de tela (`../chat/`), renderização (`../element/`).

**Convenções locais**:

- Nunca cookie (`credentials: "omit"`); a conversa é autorizada por `Authorization: Bearer kbv_…`.
- O SSE termina em `done` ou `error`; stream que acaba antes vira `network_error`. Abort (nova conversa, elemento removido) é repassado como `AbortError`, nunca como falha.
- `types.ts` acompanha `docs/specs/openapi.json` (schemas `WidgetPublicConfig`, `WidgetConversationCreated`, `WidgetConversationDetail`, `WidgetMessageOut`, `CitationOut`) e `docs/specs/chat-sse.md`: campo novo que o widget lê entra nos dois na mesma entrega.

**Como testar**: de `widget/`, `pnpm test` (com o `fetch` falso de `../test/fake-api.ts`).

**Leia também**: [docs/specs/widget.md](../../../docs/specs/widget.md), seção "Rotas públicas"; [docs/specs/chat-sse.md](../../../docs/specs/chat-sse.md).
