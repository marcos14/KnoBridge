# frontend/src/lib/api/

**Função**: único ponto de acesso do frontend à API do backend. Tipos gerados do contrato, cliente HTTP tipado e hooks TanStack Query.

**Entra aqui**:

- `schema.gen.ts`: tipos gerados por `openapi-typescript` a partir de `docs/specs/openapi.json`. **Nunca edite à mão.** Fora do lint, do Prettier e da cobertura (só tipos).
- `client.ts`: `apiClient` (`openapi-fetch`), com `baseUrl` vindo de `VITE_API_BASE_URL` (padrão `/`, mesma origem; nginx e o proxy do Vite repassam `/v1` para a API), `createApiClient()` e `ApiError` (resposta não 2xx).
- Um módulo por recurso com seus hooks e funções de busca (hoje `health.ts`: `useApiHealth`, `GET /v1/health/ready`).

**Não entra aqui**: componentes (`components/`, `features/`), tipos de resposta escritos à mão, `fetch` direto.

**Convenções locais**:

- Mudou o contrato no backend: `cd backend && uv run knobridge-openapi`, depois `pnpm gen:api`, e commite os dois arquivos juntos. A CI roda `pnpm check:api`, que falha se `schema.gen.ts` estiver desatualizado.
- Hooks recebem o `signal` do TanStack Query e o repassam ao cliente; chaves de query exportadas como constantes (`apiHealthQueryKey`).
- Erro HTTP vira `ApiError` com `status`; falha de rede chega como `TypeError` do `fetch`.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. A API é simulada com MSW (handlers em `src/test/handlers.ts`); nunca mocke `fetch` à mão.

**Leia também**: [../../../AGENTS.md](../../../AGENTS.md); [docs/specs/AGENTS.md](../../../../docs/specs/AGENTS.md).
