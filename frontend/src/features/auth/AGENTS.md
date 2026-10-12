# frontend/src/features/auth/

**Função**: autenticação e controle de acesso do painel no navegador. Telas públicas (fora da sessão), guardas de rota, página 403, reação à sessão expirada e utilitários de papel e de workspace atual.

**Entra aqui**:

- Telas públicas (dentro do `PublicLayout`): `SetupPage` (`/setup`: nome, e-mail, senha e confirmação → shell), `LoginPage` (`/login`: vai ao `?next=` validado ou a `/`; link "Esqueci minha senha"), `ForgotPasswordPage` (`/forgot-password`: confirmação genérica, igual exista a conta ou não), `ResetPasswordPage` (`/reset-password?token=`), `VerifyEmailPage` (`/verify-email?token=`: verifica ao abrir, uma vez só), `AcceptInvitationPage` (`/accept-invitation?token=`: mostra o convite e cria a conta, manda ao login ou aceita com a conta logada; outra conta logada → explica e oferece sair; depois vai para `/w/<workspace>`). `InvitationSignupForm` e `invitationStep.ts` (`signup`/`login`/`accept`/`mismatch`) apoiam a tela de convite.
- Peças das telas: `AuthCard` (coluna com o `h1`), `useUrlToken` (lê `?token=` uma vez e o tira da barra de endereço com `replace`). Campo, alerta e schemas de formulário são compartilhados com `features/account/`: `components/TextField.tsx`, `components/FormAlert.tsx` e `lib/schemas.ts`.
- Guardas (elementos de rota de layout, renderizam `<Outlet />` quando liberam): `RequireSetupDone` (instância sem usuário → `/setup`), `RequireSetupPending` (o inverso, só em `/setup`: setup já feito → `/`), `RequireAuth` (anônimo → `/login?next=<destino>`; logo após um logout explícito, `useLoggedOutByUser()`, → `/login` limpo), `RequireWorkspaceRole({ minRole })` (sem membership no `:workspaceId` ou papel abaixo de `minRole` → 403), `RequireSuperadmin` (não superadmin → 403).
- `ForbiddenPage.tsx`: 403 renderizado no lugar, sem trocar a URL (nas rotas autenticadas, dentro do shell).
- `GuardStatus.tsx`: carregando e falha com "Tentar novamente", usados pelos guardas e pela tela de convite.
- `SessionExpiryHandler.tsx`: registra o handler de 401 do cliente; marca `me` como `null` e leva ao login preservando o destino.
- `redirect.ts` (`loginPath`, `safeNextPath`, `LOGIN_PATH`, `SETUP_PATH`, `FORGOT_PASSWORD_PATH`, `ACCEPT_INVITATION_PATH`). Papéis (`hasRole`, `findWorkspace`) ficam em `lib/roles.ts` e o workspace da URL em `hooks/use-current-workspace.ts`, porque outras áreas também os usam.

**Não entra aqui**: chamadas de API e hooks (`lib/api/auth.ts`, `setup.ts`, `recovery.ts`, `invites.ts`), árvore de rotas (`app/router.tsx`), textos (`i18n/locales/`, chaves `auth.*`), telas da conta logada (perfil, segurança: `features/account/`).

**Convenções locais**:

- Guardas são só conveniência de navegação: quem autoriza é o backend. O `:workspaceId` da URL só seleciona o workspace; o acesso vem da membership em `useMe()`.
- `RequireWorkspaceRole` e `RequireSuperadmin` ficam sob `RequireAuth`, que carrega a sessão antes.
- Todo `next` lido da URL passa por `safeNextPath` antes de navegar (evita redirecionamento para outro site).
- Token de link de e-mail nunca fica na URL: `useUrlToken` o remove ao ler. O do convite espera o login no `sessionStorage` da aba (`INVITATION_TOKEN_KEY`), para o `?next=` ser só `/accept-invitation`; sai ao aceitar ou quando o convite é inválido.
- Formulários: zod com mensagens do i18n (schema montado com `t` em `useMemo`), `noValidate` (a validação é a do zod), foco no primeiro campo inválido (react-hook-form) ou no `FormAlert`; botão desabilitado e "Enviando…" durante o envio. Erros da API pelo `code` via `translateApiError`; `invalid_token` vira estado próprio da tela.
- Ordem dos papéis espelha o backend: `owner` > `admin` > `editor` > `viewer`.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Telas e guardas testados pela árvore real (`renderWithProviders({ path })`) com MSW (`meAs`, `meUnauthenticated`, `setupStatusNeeded`, `recordingPost` para conferir o corpo enviado, `pendingPost` para o estado de envio…), conferindo `router.state.location`. Nas telas públicas o `ApiStatus` do cabeçalho também tem `role="status"`: procure dentro do `main`.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../lib/api/AGENTS.md](../../lib/api/AGENTS.md); `docs/specs/openapi.json` (`/v1/me`, `/v1/setup`, `/v1/auth/*`, `/v1/invites/*`).
