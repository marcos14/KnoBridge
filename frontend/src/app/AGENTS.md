# frontend/src/app/

**Função**: casca da aplicação. Providers, roteamento, layouts e as páginas estruturais (início do workspace, "não encontrada" e telas provisórias). A moldura autenticada (sidebar, topbar, menus) fica em `shell/`.

**Entra aqui**:

- `App.tsx`: cria router e `QueryClient` uma vez e monta `AppProviders`.
- `AppProviders.tsx`: pilha de providers (`QueryClientProvider`, `I18nextProvider`, `ClockContext` (relógio; o helper de teste passa um fixo), `RouterProvider`), compartilhada com o helper de teste.
- `router.tsx`: árvore de rotas (`routes`) e `createAppRouter()` (data router do React Router), com os guardas de `features/auth/`; as áreas do workspace usam `workspaceArea(area, element, subPaths?)`, que lê o papel mínimo e o caminho (`areaPath`) de `shell/navItems.ts`; com `subPaths` (ex.: `:conversationId` do chat), o elemento vira a rota-pai sem caminho das subrotas e continua montado quando a URL passa de uma para outra.
- `queryClient.ts`: `createQueryClient()` com os defaults do TanStack Query.
- `Layout.tsx` (raiz: só o `SessionExpiryHandler` e o `<Outlet />`), `PublicLayout.tsx` (cabeçalho com título e `ApiStatus` + `main`, para as páginas sem sessão), `HomePage.tsx` (Início do workspace: cartões do painel de `GET .../dashboard` (documentos, fontes ativas, execuções com falha em 7 dias, conversas e avaliações do mês; custo do mês com o detalhe e o aviso de custo parcial só quando a API manda, isto é, para owner e admin), com carregando e erro com "Tentar novamente"), `FirstSteps.tsx` (checklist de primeiros passos: só os pendentes, com o link da tela ou "peça a um administrador" conforme o papel, via `lib/firstSteps.ts`; some quando todos estão feitos), `NotFoundPage.tsx`.
- `lazyPage.tsx` + `PageLoading.tsx`: `lazyPage(load)` devolve o elemento de uma página carregada na primeira visita, num chunk próprio (`React.lazy` + `Suspense` com o status acessível "Carregando a página…"; o shell continua na tela); já carregada, a página renderiza direto. `preloadLazyPages()` carrega todas (usado pelo helper de teste). Todas as telas de `features/` entram assim no `router.tsx`; guardas e layouts ficam no chunk principal.
- `shell/`: moldura autenticada (ver [shell/AGENTS.md](shell/AGENTS.md)).

**Não entra aqui**: telas de produto (vão para `features/<area>/`), guardas e página 403 (`features/auth/`), componentes reutilizáveis (`components/`), chamadas de API (`lib/api/`), textos (`i18n/locales/`).

**Convenções locais**:

- URLs em inglês (plano 0002, D11). Árvore: `Layout` > `PublicLayout` > `/setup` (sob `RequireSetupPending`: setup feito → `/`); `RequireSetupDone` > (`PublicLayout` > `/login`, `/forgot-password`, `/reset-password`, `/verify-email`, `/accept-invitation`, telas de `features/auth/`) e `RequireAuth` > `AppShell` > `/` (`HomeRedirect`), `/account/{profile,security}` (telas de `features/account/`), `/admin` (índice: painel da instância) e `/admin/{workspaces,users,audit}` sob `RequireSuperadmin` (telas de `features/admin/` e `features/audit/`), `/w/:workspaceId` sob `RequireWorkspaceRole` > `WorkspaceLayout` > índice e `{chat,conversations,products,providers,sources,runners,api-keys,pipelines,collections,channels,members,settings,audit}`, cada uma com o papel do menu (`chat` com `chat/:conversationId`, `conversations` com `conversations/:conversationId` e `sources` com `sources/:sourceId`; `chat`, `conversations`, `products` (com `assistants`, o endereço antigo, redirecionando para `products`), `providers`, `sources`, `runners`, `api-keys`, `members`, `settings` e `audit` já com as telas de `features/chat/`, `features/conversations/`, `features/products/`, `features/providers/`, `features/sources/`, `features/runners/`, `features/apikeys/`, `features/members/`, `features/settings/` e `features/audit/`), e o `*` de "não encontrada" (dentro do shell; anônimo vai antes para o login).
- Tela nova substitui o `AreaSkeletonPage` da sua rota e entra por `lazyPage(() => import(...))`.
- Code splitting: nenhum chunk acima de 500 kB (o aviso do Vite no `pnpm build` é tratado como falha de revisão); dependência pesada usada por uma feature só chega com ela.
- Nenhum texto literal em componente: use `useTranslation()`.
- Landmarks semânticos (`header`, `nav` com `aria-label`, `main`) são parte do contrato dos layouts e têm teste.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Use `renderWithProviders({ path })` de `@/test/renderWithProviders` para renderizar uma rota com os providers reais; os guardas consultam a API, então espere com `findBy*`.

**Leia também**: [shell/AGENTS.md](shell/AGENTS.md), [../features/auth/AGENTS.md](../features/auth/AGENTS.md), [../AGENTS.md](../AGENTS.md), [../../AGENTS.md](../../AGENTS.md).
