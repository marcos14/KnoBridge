# frontend/src/app/

**Função**: casca da aplicação. Providers, roteamento, layouts e as páginas estruturais (início do workspace, "não encontrada" e telas provisórias). A moldura autenticada (sidebar, topbar, menus) fica em `shell/`.

**Entra aqui**:

- `App.tsx`: cria router e `QueryClient` uma vez e monta `AppProviders`.
- `AppProviders.tsx`: pilha de providers (`QueryClientProvider`, `I18nextProvider`, `RouterProvider`), compartilhada com o helper de teste.
- `router.tsx`: árvore de rotas (`routes`) e `createAppRouter()` (data router do React Router), com os guardas de `features/auth/`; as áreas do workspace usam `workspaceArea(...)`, que lê o papel mínimo de `shell/navItems.ts`.
- `queryClient.ts`: `createQueryClient()` com os defaults do TanStack Query.
- `Layout.tsx` (raiz: só o `SessionExpiryHandler` e o `<Outlet />`), `PublicLayout.tsx` (cabeçalho com título e `ApiStatus` + `main`, para as páginas sem sessão), `HomePage.tsx` (início do workspace), `NotFoundPage.tsx`.
- `PlaceholderPage.tsx`: tela provisória (só o título, de `pages.*` no i18n) para rotas cujas telas ainda não existem.
- `shell/`: moldura autenticada (ver [shell/AGENTS.md](shell/AGENTS.md)).

**Não entra aqui**: telas de produto (vão para `features/<area>/`), guardas e página 403 (`features/auth/`), componentes reutilizáveis (`components/`), chamadas de API (`lib/api/`), textos (`i18n/locales/`).

**Convenções locais**:

- URLs em inglês (plano 0002, D11). Árvore: `Layout` > `PublicLayout` > `/setup` (sob `RequireSetupPending`: setup feito → `/`); `RequireSetupDone` > (`PublicLayout` > `/login`, `/forgot-password`, `/reset-password`, `/verify-email`, `/accept-invitation`) e `RequireAuth` > `AppShell` > `/` (`HomeRedirect`), `/account/{profile,security}`, `/admin/{workspaces,users,audit}` sob `RequireSuperadmin`, `/w/:workspaceId` sob `RequireWorkspaceRole` > `WorkspaceLayout` > índice e `{chat,conversations,assistants,providers,sources,pipelines,collections,channels,members,settings,audit}`, cada uma com o papel do menu, e o `*` de "não encontrada" (dentro do shell; anônimo vai antes para o login).
- Tela nova substitui o `PlaceholderPage` ou o `AreaSkeletonPage` da sua rota; quando não restar nenhum, o componente e as chaves `pages.*` sem uso saem.
- Nenhum texto literal em componente: use `useTranslation()`.
- Landmarks semânticos (`header`, `nav` com `aria-label`, `main`) são parte do contrato dos layouts e têm teste.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Use `renderWithProviders({ path })` de `@/test/renderWithProviders` para renderizar uma rota com os providers reais; os guardas consultam a API, então espere com `findBy*`.

**Leia também**: [shell/AGENTS.md](shell/AGENTS.md), [../features/auth/AGENTS.md](../features/auth/AGENTS.md), [../AGENTS.md](../AGENTS.md), [../../AGENTS.md](../../AGENTS.md).
