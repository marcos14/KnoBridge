# frontend/src/app/

**Função**: casca da aplicação. Providers, roteamento, layout e as páginas estruturais (início e "não encontrada").

**Entra aqui**:

- `App.tsx`: cria router e `QueryClient` uma vez e monta `AppProviders`.
- `AppProviders.tsx`: pilha de providers (`QueryClientProvider`, `I18nextProvider`, `RouterProvider`), compartilhada com o helper de teste.
- `router.tsx`: árvore de rotas (`routes`) e `createAppRouter()` (data router do React Router).
- `queryClient.ts`: `createQueryClient()` com os defaults do TanStack Query.
- `Layout.tsx`, `HomePage.tsx`, `NotFoundPage.tsx`.
- Futuramente: guarda de autenticação e rotas das features.

**Não entra aqui**: telas de produto (vão para `features/<area>/`), componentes reutilizáveis (`components/`), chamadas de API (`lib/api/`), textos (`i18n/locales/`).

**Convenções locais**:

- Rotas novas entram em `routes`, como filhas do layout; páginas de feature são importadas de `features/`.
- Nenhum texto literal em componente: use `useTranslation()`.
- Landmarks semânticos (`header`, `nav` com `aria-label`, `main`) são parte do contrato do layout e têm teste.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Use `renderWithProviders({ path })` de `@/test/renderWithProviders` para renderizar uma rota com os providers reais.

**Leia também**: [../AGENTS.md](../AGENTS.md), [../../AGENTS.md](../../AGENTS.md).
