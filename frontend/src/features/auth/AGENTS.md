# frontend/src/features/auth/

**Função**: controle de acesso do painel no navegador. Guardas de rota, página 403, reação à sessão expirada e utilitários de papel e de workspace atual. As telas de autenticação (login, setup, recuperação) entram aqui nas próximas subfases.

**Entra aqui**:

- Guardas (elementos de rota de layout, renderizam `<Outlet />` quando liberam): `RequireSetupDone` (instância sem usuário → `/setup`), `RequireSetupPending` (o inverso, só em `/setup`: setup já feito → `/`), `RequireAuth` (anônimo → `/login?next=<destino>`; logo após um logout explícito, `useLoggedOutByUser()`, → `/login` limpo), `RequireWorkspaceRole({ minRole })` (sem membership no `:workspaceId` ou papel abaixo de `minRole` → 403), `RequireSuperadmin` (não superadmin → 403).
- `ForbiddenPage.tsx`: 403 renderizado no lugar, sem trocar a URL (nas rotas autenticadas, dentro do shell).
- `GuardStatus.tsx`: carregando e falha com "Tentar novamente", usados pelos guardas que consultam a API.
- `SessionExpiryHandler.tsx`: registra o handler de 401 do cliente; marca `me` como `null` e leva ao login preservando o destino.
- `roles.ts` (`hasRole`, `findWorkspace`), `redirect.ts` (`loginPath`, `safeNextPath`, `LOGIN_PATH`, `SETUP_PATH`), `useCurrentWorkspace.ts`.

**Não entra aqui**: chamadas de API e hooks de sessão (`lib/api/auth.ts`, `lib/api/setup.ts`), árvore de rotas (`app/router.tsx`), textos (`i18n/locales/`).

**Convenções locais**:

- Guardas são só conveniência de navegação: quem autoriza é o backend. O `:workspaceId` da URL só seleciona o workspace; o acesso vem da membership em `useMe()`.
- `RequireWorkspaceRole` e `RequireSuperadmin` ficam sob `RequireAuth`, que carrega a sessão antes.
- Todo `next` lido da URL passa por `safeNextPath` antes de navegar (evita redirecionamento para outro site).
- Ordem dos papéis espelha o backend: `owner` > `admin` > `editor` > `viewer`.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Guardas testados pela árvore real (`renderWithProviders({ path })`) com MSW (`meAs`, `meUnauthenticated`, `setupStatusNeeded`…), conferindo `router.state.location`.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../lib/api/AGENTS.md](../../lib/api/AGENTS.md); `docs/specs/openapi.json` (`/v1/me`, `/v1/setup/status`).
