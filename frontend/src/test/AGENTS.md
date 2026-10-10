# frontend/src/test/

**Função**: infraestrutura de testes do Vitest. Setup global, servidor MSW, handlers, fábricas de dados e helpers compartilhados entre os testes.

**Entra aqui**:

- `setup.ts`: matchers do jest-dom; instala `matchMedia` e os stubs de `ResizeObserver`, `scrollIntoView` e pointer capture que os popovers do Radix pedem e o jsdom não tem; sobe o servidor MSW antes da suíte (`onUnhandledRequest: "error"`); após cada teste faz `cleanup`, `server.resetHandlers()` e limpa o estado fora do React (`localStorage`, `sessionStorage`, classe e estilo do `<html>`, cookie da sidebar, media queries); fecha o servidor no fim.
- `matchMedia.ts`: `window.matchMedia` controlável (`setPrefersDark`, `setMobileViewport`, `resetMatchMedia`, `matchMediaListenerCount`), que notifica os ouvintes como uma mudança real.
- `server.ts`: `server` do `msw/node` com os handlers padrão.
- `handlers/`: handlers MSW por recurso (ver o `AGENTS.md` da pasta); `@/test/handlers` reexporta todos.
- `factories.ts`: dados sintéticos tipados pelo `schema.gen.ts` (`makeMe`, `makeWorkspace`, `makeInvitationPreview`, `makeSession`, `makeSessions`, `makeMember`, `makeMembers` (Ana owner, que é o usuário logado, Bruno admin, Carla editor, Davi viewer), `makeInvitation`, `makeInvitations` (Elisa editor válido, Fábio owner expirado)), ids fixos (`WORKSPACE_ID`, `OTHER_WORKSPACE_ID`, `USER_ID`, `CURRENT_SESSION_ID`, `OTHER_SESSION_ID`, `INVITATION_ID`, `OTHER_INVITATION_ID`, `memberId(n)`) e `User-Agent` sintéticos.
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
