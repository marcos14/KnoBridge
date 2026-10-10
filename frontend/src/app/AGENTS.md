# frontend/src/app/

**Função**: casca da aplicação. Providers, roteamento, layout e as páginas estruturais (início, "não encontrada" e telas provisórias).

**Entra aqui**:

- `App.tsx`: cria router e `QueryClient` uma vez e monta `AppProviders`.
- `AppProviders.tsx`: pilha de providers (`QueryClientProvider`, `I18nextProvider`, `RouterProvider`), compartilhada com o helper de teste.
- `router.tsx`: árvore de rotas (`routes`) e `createAppRouter()` (data router do React Router), com os guardas de `features/auth/`.
- `queryClient.ts`: `createQueryClient()` com os defaults do TanStack Query.
- `Layout.tsx` (monta também o `SessionExpiryHandler`), `HomePage.tsx`, `NotFoundPage.tsx`.
- `PlaceholderPage.tsx`: tela provisória (só o título, de `pages.*` no i18n) para rotas cujas telas ainda não existem.

**Não entra aqui**: telas de produto (vão para `features/<area>/`), guardas e página 403 (`features/auth/`), componentes reutilizáveis (`components/`), chamadas de API (`lib/api/`), textos (`i18n/locales/`).

**Convenções locais**:

- URLs em inglês (plano 0002, D11). Árvore: `Layout` > `/setup` (livre) e `RequireSetupDone` > rotas públicas (`/login`, `/forgot-password`, `/reset-password`, `/verify-email`, `/accept-invitation`), `RequireAuth` > (`/`, `/account/*`, `/admin/*` sob `RequireSuperadmin`, `/w/:workspaceId/...` sob `RequireWorkspaceRole`) e o `*` de "não encontrada".
- Tela nova substitui o `PlaceholderPage` da sua rota; quando não restar nenhum, o componente e as chaves `pages.*` sem uso saem.
- Nenhum texto literal em componente: use `useTranslation()`.
- Landmarks semânticos (`header`, `nav` com `aria-label`, `main`) são parte do contrato do layout e têm teste.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Use `renderWithProviders({ path })` de `@/test/renderWithProviders` para renderizar uma rota com os providers reais; os guardas consultam a API, então espere com `findBy*`.

**Leia também**: [../features/auth/AGENTS.md](../features/auth/AGENTS.md), [../AGENTS.md](../AGENTS.md), [../../AGENTS.md](../../AGENTS.md).
