# frontend/src/lib/api/

**Função**: único ponto de acesso do frontend à API do backend. Tipos gerados do contrato, cliente HTTP tipado e hooks TanStack Query.

**Entra aqui**:

- `schema.gen.ts`: tipos gerados por `openapi-typescript` a partir de `docs/specs/openapi.json`. **Nunca edite à mão.** Fora do lint, do Prettier e da cobertura (só tipos).
- `client.ts`: `apiClient` (`openapi-fetch`, `credentials: "include"`), com `baseUrl` vindo de `VITE_API_BASE_URL` (padrão `/`, mesma origem; nginx e o proxy do Vite repassam `/v1` para a API), `createApiClient()`, `ApiError` (status, `code` e `details` do corpo de erro padrão), `isApiErrorCode(error, code)`, `retryAfterSeconds(error)` (espera pedida por um 429 em `details.retry_after_seconds`), `toApiError`, `unwrap` e o `authMiddleware`: copia o cookie `knobridge_csrf` no header `X-CSRF-Token` em métodos não seguros e avisa o handler registrado por `setUnauthorizedHandler` a cada 401 inesperado.
- Um módulo por recurso com seus hooks e funções de busca: `health.ts` (`useApiHealth`), `auth.ts` (`useMe`, `useUpdateProfile` (`PATCH /v1/me`, otimista), `useLogin`, `useLogout`, `endSession` (esquece a sessão encerrada nesta aba; usado pelo logout e pela revogação da sessão atual), chaves `meQueryKey` e `setupStatusQueryKey`), `account.ts` (`useSessions` (lê todas as páginas de `GET /v1/me/sessions`), `useRevokeSession` (404 conta como sucesso; a sessão atual vira logout), `useRevokeOtherSessions` (revoga uma a uma as outras, a partir de uma lista nova), `useChangePassword` (recarrega as sessões), `useResendVerification` (409 `email_already_verified` recarrega `me`)), `setup.ts` (`useSetupStatus`, `useRunSetup`), `recovery.ts` (`useForgotPassword`, `useResetPassword`, `useVerifyEmail`, que recarrega `me`; todos 204), `invites.ts` (`useInvitationPreview(token)`, `POST` com o token no corpo e desligado sem token; `useAcceptInvitation`, que grava a sessão como o login).

**Não entra aqui**: componentes (`components/`, `features/`), tipos de resposta escritos à mão, `fetch` direto, textos de erro (`i18n/apiErrors.ts`).

**Convenções locais**:

- Mudou o contrato no backend: `cd backend && uv run knobridge-openapi`, depois `pnpm gen:api`, e commite os dois arquivos juntos. A CI roda `pnpm check:api`, que falha se `schema.gen.ts` estiver desatualizado.
- Hooks recebem o `signal` do TanStack Query e o repassam ao cliente; chaves de query exportadas como constantes (`apiHealthQueryKey`, `meQueryKey`).
- Erro HTTP vira `ApiError` (use `unwrap`); falha de rede chega como `TypeError` do `fetch`.
- 401 esperados não disparam o handler de sessão expirada: `GET /v1/me` anônimo (vira `data === null` no `useMe`), login com credencial errada, logout de sessão já encerrada e aceite de convite que exige login (`login_required`, tratado pela tela de convite). Endpoint novo com 401 esperado entra em `EXPECTED_UNAUTHORIZED`.
- Login, setup, aceite de convite e `PATCH /v1/me` respondem com o corpo de `/v1/me`: a mutação grava no cache do `useMe` em vez de buscar de novo. `useUpdateProfile` aplica a mudança no cache antes da resposta e volta ao valor anterior se ela falhar. Logout grava o marcador local `loggedOutQueryKey` (`useLoggedOutByUser()`, sem requisição; login e setup o apagam via `storeSession`), para o `RequireAuth` mandar a um `/login` limpo em vez de `?next=`, e deixa `me` como `null` e remove as queries do usuário (mantém `me`, status do setup e health).

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. A API é simulada com MSW (handlers por recurso em `src/test/handlers/`); nunca mocke `fetch` à mão. Hooks: `renderQueryHook` de `@/test/renderWithProviders`.

**Leia também**: [../../../AGENTS.md](../../../AGENTS.md); [docs/specs/AGENTS.md](../../../../docs/specs/AGENTS.md); `backend/src/knobridge/security/csrf.py` (nome do cookie e do header).
