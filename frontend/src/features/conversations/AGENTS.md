# frontend/src/features/conversations/

**Função**: acompanhamento do uso do chat por owner e admin em `/w/:workspaceId/conversations` (totais do período, conversas de todos os membros com filtros) e `/w/:workspaceId/conversations/:conversationId` (a conversa de qualquer membro, somente leitura). Editor e viewer não veem o item do menu e recebem 403 na rota (`minRole: "admin"` em `app/shell/navItems.ts`).

**Entra aqui**:

- `ConversationsPage.tsx`: elemento das duas rotas (lê o `:conversationId` com `useMatch`, como o chat): título e, conforme a URL, a visão geral ou a conversa.
- `ConversationsOverview.tsx`: cartões de totais, barra de filtros e tabela paginada pela API (`DataTable`, 20 por página), com carregando, erro com "Tentar novamente" e vazio (com ou sem filtro). O link de cada conversa leva a query string junto.
- `ConversationStatsCards.tsx`: conversas, mensagens, 👍, 👎, sem fonte, com falha e interrompidas do período dos filtros (sem período, os 30 dias padrão da API); mostra o período devolvido, com o fim exclusivo convertido no último dia.
- `ConversationFilterBar.tsx`: assistente, usuário (`FilterSelect` de `components/`), "De"/"Até" (dias inclusivos), "Só com 👎" e "Limpar filtros"; cada mudança vale na hora. Id de link compartilhado que não está na lista continua selecionável pelo id.
- `WorkspaceConversationView.tsx`: a conversa com perguntas, respostas renderizadas como no chat (`AssistantMessage` de `components/` em modo `readOnly`: Markdown seguro, fontes, status, sem "Abrir chamado" nem "Reenviar"), modelo e latência, painel da fonte (`CitationSheet`) e "Voltar para as conversas" com os mesmos filtros. 404 vira "Conversa não encontrada".
- `FeedbackList.tsx`: as avaliações de cada resposta, com autor e comentário.
- `useConversationSearch.ts`: filtros e página na query string (`?assistant=&user=&from=&to=&negative=1&offset=`); mudar filtro volta para a primeira página.

**Não entra aqui**: chamadas de API (`lib/api/workspaceConversations.ts`), leitura e escrita da query string e conversão do período (`lib/conversationFilters.ts`, `lib/days.ts`), o chat dos membros (`features/chat/`), textos (`i18n/locales/`, chaves `conversations.*`).

**Convenções locais**:

- A URL é a fonte dos filtros: link compartilhado abre a mesma visão; valor que a API recusaria (id ou dia malformado) é ignorado.
- O período vai para a API como `[início de "De", início do dia seguinte a "Até")` do fuso do navegador, em instantes UTC; vale para a lista e para os totais.
- Nada de ação sobre a conversa: a tela só lê. As avaliações exibidas são as dos membros.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Pela árvore real (`renderWithProviders({ path: "/w/<id>/conversations?..." })`) com MSW: `workspaceConversationsRecorder(rows, stats)` guarda a query string da lista e dos totais; `workspaceConversationAs(...details)`, `workspaceConversationsAs`, `conversationStatsAs` e os `*ServerError`. Datas com `fireEvent.change`; o esperado do período é calculado com `new Date(ano, mês, dia).toISOString()`, o que torna o teste determinístico em qualquer fuso.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../lib/api/AGENTS.md](../../lib/api/AGENTS.md); `docs/specs/openapi.json` (`/v1/workspaces/{workspace_id}/admin/conversations`, `/stats`, `/{conversation_id}`).
