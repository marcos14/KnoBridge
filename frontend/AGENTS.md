# frontend/

**Função**: painel administrativo do KnoBridge em React + TypeScript. Fontes e conectores, canvas de pipelines (React Flow), execuções, coleções, assistentes, canais, conversas, custos e configurações do workspace. Estado: app Vite com providers (roteador, TanStack Query, i18n pt-BR), Tailwind v4 + shadcn/ui, cliente tipado gerado do OpenAPI (`src/lib/api/`), indicador de status da API no cabeçalho, infraestrutura de autenticação (cliente com cookie de sessão e CSRF, hooks de sessão, guardas de rota em `src/features/auth/`, rotas em inglês com telas provisórias), MSW nos testes, smoke E2E com Playwright e imagem nginx. Sem telas de produto ainda.

**Entra aqui**: aplicação Vite em `src/`, testes ao lado dos arquivos (`*.test.tsx`) e E2E em `e2e/`, `package.json`, `pnpm-lock.yaml`, `pnpm-workspace.yaml` (configurações do pnpm), `components.json` (shadcn), configs de ESLint, Prettier, Vitest e Playwright, `Dockerfile`, `nginx.conf`, `.dockerignore`, `README.md` curto.
**Não entra aqui**: o widget embutível (vai para `widget/`), documentação (vai para `docs/`), lógica de negócio que pertence ao backend, dados reais.

**Layout previsto** (crie cada pasta só quando for necessária, sempre com o seu `AGENTS.md`):

```
frontend/src/
  app/            # roteamento, providers, layout, páginas estruturais
  features/       # uma pasta por área: auth, sources, pipelines, runs, collections, assistants, channels, conversations, settings
  components/ui/  # shadcn/ui (gerado; editar só o necessário)
  components/     # componentes compartilhados próprios
  lib/api/        # cliente gerado do OpenAPI do backend + hooks TanStack Query
  lib/            # utilitários puros (cobertura 100%)
  i18n/           # pt-BR primeiro; chaves em inglês
  test/           # setup do Vitest, handlers MSW, fábricas de dados
```

**Convenções locais**

- Node LTS, `pnpm`. TypeScript `strict`; sem `any` sem comentário; sem `@ts-ignore` (use `@ts-expect-error` com motivo).
- ESLint + Prettier. A CI falha com aviso.
- Estado de servidor só via TanStack Query; estado local via hooks; store global só com necessidade demonstrada.
- Cliente de API gerado do OpenAPI do backend. Nunca escrever tipos de resposta à mão. Toda chamada passa por `lib/api/`. Contrato em `docs/specs/openapi.json`; `pnpm gen:api` regenera `src/lib/api/schema.gen.ts` e `pnpm check:api` (CI) falha se ele estiver desatualizado.
- A API é chamada na mesma origem, sob `/v1` (`VITE_API_BASE_URL`, padrão `/`): em desenvolvimento o proxy do Vite repassa para `127.0.0.1:8000`; na imagem, o `nginx.conf` repassa para o serviço `api` do compose.
- Dependências com script de instalação precisam de decisão explícita em `allowBuilds` no `pnpm-workspace.yaml`; exceções de peer dependency ficam em `peerDependencyRules`, com comentário. `pnpm peers check` deve sair limpo.
- Canvas: React Flow (xyflow). Nós e arestas tipados; o grafo salvo é o contrato com o backend (spec em `docs/specs/`).
- Componentes de `features/` não conhecem `fetch`; recebem dados por hooks. Componentes pequenos; lógica em funções puras em `lib/`, testadas isoladamente.
- Acessibilidade: elementos semânticos, foco visível, labels. Testes com Testing Library consultam por papel e texto, nunca por classe CSS.
- Textos de interface em pt-BR via i18n desde o início; nada hardcoded. URLs do painel em inglês (plano 0002, D11): públicas `/setup`, `/login`, `/forgot-password`, `/reset-password`, `/verify-email`, `/accept-invitation`; autenticadas `/w/:workspaceId/...`, `/account/...`, `/admin/...`.
- Formulários com react-hook-form + zod (`@hookform/resolvers`) e os componentes de `components/ui/form.tsx`; mensagens de erro da API pelo `code`, via `translateApiError` de `src/i18n/apiErrors.ts`.
- Streaming de respostas (SSE) tratado por um hook único, reutilizado pelo chat de teste e pela visualização de conversas.

**Como testar**

```sh
pnpm lint && pnpm typecheck
pnpm test -- --coverage        # Vitest; thresholds de 95 em lines, branches, functions e statements
pnpm check:api                 # tipos do cliente em dia com docs/specs/openapi.json
pnpm e2e                       # Playwright: fluxos críticos do canvas e do chat de teste
```

- Vitest + Testing Library para componentes e hooks; MSW para a API (nunca mockar `fetch` à mão; handlers por recurso em `src/test/handlers/`). O Vitest lê só `src/**/*.test.{ts,tsx}`.
- Playwright só para os poucos fluxos críticos; na CI (job `frontend` de `.github/workflows/ci.yml`) rodam contra o build de produção servido pelo `vite preview`, sem backend. Fluxos que precisarem da API real passarão a subir o backend em container.
- Componentes de `components/ui/` gerados pelo shadcn podem ficar fora da medição de cobertura, com justificativa no `vitest.config.ts`.

**Leia também**: `AGENTS.md` da raiz (seções 5 e 6.3); `docs/01-visao-do-projeto.md`, seções 7.2 e 8.
