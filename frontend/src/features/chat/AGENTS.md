# frontend/src/features/chat/

**Função**: o chat dos membros em `/w/:workspaceId/chat` e `/w/:workspaceId/chat/:conversationId` (todo membro, inclusive viewer). Lista das próprias conversas, início de conversa com um assistente ativo, thread com a resposta em streaming, citações, fallback "sem fonte" e avaliação.

**Entra aqui**:

- `ChatPage.tsx`: layout das duas rotas (lê o `:conversationId` com `useMatch`, porque é o elemento da rota-pai e continua montado quando a primeira pergunta move a URL para a conversa nova); dono do `useChatStream`, para a resposta da conversa que se deixa e abre o painel de citação.
- `ConversationList.tsx`: "Nova conversa", conversas pelo título (a primeira pergunta; sem título, "Conversa sem título"), "Carregar mais" e exclusão com `ConfirmDialog` (excluir a aberta volta para `/chat`).
- `NewConversation.tsx`: seletor de assistente (só os ativos; a API já filtra para viewer) e o composer; sem assistente ativo, estado vazio com link para `/assistants` só para editor ou acima.
- `ConversationView.tsx`: cabeçalho, `MessageList`, erro de envio (JSON antes do stream, pelo `code`) e `Composer`.
- `MessageList.tsx`: thread em `ol`; a resposta em andamento num `aria-live="polite"`; acompanha o fim só se o leitor já estiver no fim.
- `AssistantMessage.tsx`: Markdown, lista de fontes, `no_source` com "Abrir chamado" desabilitado e a dica, `failed`/`interrupted` com aviso e "Reenviar pergunta".
- `ChatMarkdown.tsx` + `citationMarkers.ts`: `react-markdown` sem HTML cru (`skipHtml`, sem `rehype-raw`), links em nova aba com `rel="noopener noreferrer"`, e o plugin que troca `[n]` de uma citação existente por botão.
- `CitationSheet.tsx` (painel lateral da fonte), `FeedbackControls.tsx` (👍/👎 com comentário opcional), `Composer.tsx` (Enter envia, Shift+Enter quebra linha, "Parar" durante o stream, foco devolvido), `chatForm.ts` (schemas zod e funções puras).

**Não entra aqui**: SSE, `fetch` e hooks de API (`lib/api/chatStream.ts`, `lib/api/conversations.ts`), visualização administrativa de conversas (área `conversations`), textos (`i18n/locales/`, chaves `chat.*`).

**Convenções locais**:

- O servidor é a fonte da verdade: ao fim de cada resposta (final, parada ou conexão perdida) a conversa é recarregada e o que aparece é a mensagem gravada, com o `status` dela.
- Sair de uma conversa com resposta em andamento a interrompe (o servidor grava `interrupted`).
- Nada de HTML vindo da resposta: só Markdown renderizado pelo `react-markdown`.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Pela árvore real (`renderWithProviders({ path: "/w/<id>/chat" })`) com `chatStore` (conversas e mensagens com estado, resposta por `reply`), `controlledStream()` para empurrar o SSE pedaço a pedaço sem timers e `answerFrames`/`exchangeIds` para os eventos. E2E em `e2e/chat.spec.ts`.

**Leia também**: [../AGENTS.md](../AGENTS.md); [docs/specs/chat-sse.md](../../../../docs/specs/chat-sse.md); [../../lib/api/AGENTS.md](../../lib/api/AGENTS.md).
