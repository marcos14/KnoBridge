# frontend/src/lib/api/

**Função**: único ponto de acesso do frontend à API do backend. Tipos gerados do contrato, cliente HTTP tipado e hooks TanStack Query.

**Entra aqui**:

- `schema.gen.ts`: tipos gerados por `openapi-typescript` a partir de `docs/specs/openapi.json`. **Nunca edite à mão.** Fora do lint, do Prettier e da cobertura (só tipos).
- `client.ts`: `apiClient` (`openapi-fetch`, `credentials: "include"`), com `baseUrl` vindo de `VITE_API_BASE_URL` (padrão `/`, mesma origem; nginx e o proxy do Vite repassam `/v1` para a API), `createApiClient()`, `ApiError` (status, `code` e `details` do corpo de erro padrão), `toApiError`, `unwrap` e o `authMiddleware`: copia o cookie `knobridge_csrf` no header `X-CSRF-Token` em métodos não seguros e avisa o handler registrado por `setUnauthorizedHandler` a cada 401 inesperado.
- Um módulo por recurso com seus hooks e funções de busca: `health.ts` (`useApiHealth`), `auth.ts` (`useMe`, `useUpdateProfile` (`PATCH /v1/me`, otimista), `useLogin`, `useLogout`, chaves `meQueryKey` e `setupStatusQueryKey`), `setup.ts` (`useSetupStatus`, `useRunSetup`).

**Não entra aqui**: componentes (`components/`, `features/`), tipos de resposta escritos à mão, `fetch` direto, textos de erro (`i18n/apiErrors.ts`).

**Convenções locais**:

- Mudou o contrato no backend: `cd backend && uv run knobridge-openapi`, depois `pnpm gen:api`, e commite os dois arquivos juntos. A CI roda `pnpm check:api`, que falha se `schema.gen.ts` estiver desatualizado.
- Hooks recebem o `signal` do TanStack Query e o repassam ao cliente; chaves de query exportadas como constantes (`apiHealthQueryKey`, `meQueryKey`).
- Erro HTTP vira `ApiError` (use `unwrap`); falha de rede chega como `TypeError` do `fetch`.
- 401 esperados não disparam o handler de sessão expirada: `GET /v1/me` anônimo (vira `data === null` no `useMe`), login com credencial errada e logout de sessão já encerrada. Endpoint novo com 401 esperado entra em `EXPECTED_UNAUTHORIZED`.
- Login, setup e `PATCH /v1/me` respondem com o corpo de `/v1/me`: a mutação grava no cache do `useMe` em vez de buscar de novo. `useUpdateProfile` aplica a mudança no cache antes da resposta e volta ao valor anterior se ela falhar. Logout grava o marcador local `loggedOutQueryKey` (`useLoggedOutByUser()`, sem requisição; login e setup o apagam via `storeSession`), para o `RequireAuth` mandar a um `/login` limpo em vez de `?next=`, e deixa `me` como `null` e remove as queries do usuário (mantém `me`, status do setup e health).

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. A API é simulada com MSW (handlers por recurso em `src/test/handlers/`); nunca mocke `fetch` à mão. Hooks: `renderQueryHook` de `@/test/renderWithProviders`.

**Leia também**: [../../../AGENTS.md](../../../AGENTS.md); [docs/specs/AGENTS.md](../../../../docs/specs/AGENTS.md); `backend/src/knobridge/security/csrf.py` (nome do cookie e do header).
