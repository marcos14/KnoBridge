# frontend/src/test/

**Função**: infraestrutura de testes do Vitest. Setup global, servidor MSW, handlers, fábricas de dados e helpers compartilhados entre os testes.

**Entra aqui**:

- `setup.ts`: matchers do jest-dom; troca o `getElementError` do testing-library pelo de `elementError.ts`; aquece o estilo do jsdom (`getComputedStyle` uma vez, que no primeiro uso de cada documento analisa a folha padrão e caía dentro do primeiro `findByRole` de cada arquivo); instala `matchMedia` e os stubs de `ResizeObserver`, `scrollIntoView` e pointer capture que os popovers do Radix pedem e o jsdom não tem; sobe o servidor MSW antes da suíte (`onUnhandledRequest: "error"`); após cada teste faz `cleanup`, `server.resetHandlers()` e limpa o estado fora do React (`localStorage`, `sessionStorage`, classe e estilo do `<html>`, cookie da sidebar, media queries); fecha o servidor no fim.
- `elementError.ts`: `lazyElementError`, mesmo erro do padrão do testing-library, mas o dump do DOM só é montado quando a mensagem é lida. `waitFor`/`findBy*` descartam o erro de cada tentativa falha (a cada mutação do DOM e a cada 50 ms); imprimir o documento inteiro em cada uma consumia boa parte do 1 s do `findBy*` no primeiro render de uma página com a suíte carregada.
- `matchMedia.ts`: `window.matchMedia` controlável (`setPrefersDark`, `setMobileViewport`, `resetMatchMedia`, `matchMediaListenerCount`), que notifica os ouvintes como uma mudança real.
- `server.ts`: `server` do `msw/node` com os handlers padrão.
- `handlers/`: handlers MSW por recurso (ver o `AGENTS.md` da pasta); `@/test/handlers` reexporta todos.
- `factories.ts`: dados sintéticos tipados pelo `schema.gen.ts` (`makeMe`, `makeWorkspace`, `makeInvitationPreview`, `makeSession`, `makeSessions`, `makeMember`, `makeMembers` (Ana owner, que é o usuário logado, Bruno admin, Carla editor, Davi viewer), `makeInvitation`, `makeInvitations` (Elisa editor válido, Fábio owner expirado), `makeAuditEvent`, `makeAuditEvents` (troca de papel por Ana, login de Bruno, evento sem autor, ação desconhecida de alguém fora da lista), `makeAdminWorkspace`, `makeAdminWorkspaces` (Acme ativo, Beta Help suspenso), `makeAdminUser`, `makeAdminUsers` (Ana superadmin logada, Bruno, Carla suspensa e não verificada), `makeProvider`, `makeProviders` (Anthropic `****wxyz` e OpenAI Produção `****1234`), `makeAssistant`, `makeAssistants` (Rascunho inativo na Anthropic, Suporte ERP ativo na OpenAI), `makeConversation`, `makeConversations` ("Como fecho o caixa?" e "Emissão de nota fiscal"), `makeCitation`, `makeMessage` (resposta concluída), `makeQuestion`, `makeThread` (pergunta e resposta com a citação [1]), `makeConversationDetail`), ids fixos (`PROVIDER_ID`, `OTHER_PROVIDER_ID`, `ASSISTANT_ID`, `OTHER_ASSISTANT_ID`, `CONVERSATION_ID`, `OTHER_CONVERSATION_ID`, `messageId(n)`, `WORKSPACE_ID`, `OTHER_WORKSPACE_ID`, `USER_ID`, `CURRENT_SESSION_ID`, `OTHER_SESSION_ID`, `INVITATION_ID`, `OTHER_INVITATION_ID`, `memberId(n)`, `auditEventId(n)`, `adminId(n)`) e `User-Agent` sintéticos.
- `renderWithProviders.tsx`: `renderWithProviders({ path, routes, now })` renderiza rotas com os providers reais e router em memória (relógio fixo em `TEST_NOW`, 2026-10-10T12:00:00Z, salvo `now`) e devolve também `router` e `queryClient`; `renderQueryHook(hook)` renderiza um hook com `QueryClient` novo; `createTestQueryClient()`.

**Não entra aqui**: os testes em si (ficam ao lado do arquivo testado, `*.test.tsx`), mocks manuais de `fetch` (use MSW), dados reais.

**Convenções locais**:

- Pasta fora da medição de cobertura (é infraestrutura de teste, não produto); a justificativa está em `vitest.config.ts`.
- Requisição sem handler falha o teste: endpoint novo ganha handler padrão em `handlers/` na mesma entrega.
- Helpers usam a mesma pilha de providers do app (`AppProviders`) para que o teste renderize a árvore real.
- Cada render cria um `QueryClient` novo, sem cache compartilhado entre testes e sem retentativa de query (falha aparece na hora, sem esperar o atraso do retry).
- Para afirmar redirecionamentos, use `router.state.location` devolvido por `renderWithProviders`.

**Como testar**: exercitada indiretamente por `pnpm test -- --coverage`, de `frontend/`.

**Leia também**: [handlers/AGENTS.md](handlers/AGENTS.md), [../AGENTS.md](../AGENTS.md); `AGENTS.md` da raiz, seção 5.
