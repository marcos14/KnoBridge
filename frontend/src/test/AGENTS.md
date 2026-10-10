# frontend/src/test/

**Função**: infraestrutura de testes do Vitest. Setup global, servidor MSW e helpers compartilhados entre os testes de componentes.

**Entra aqui**:

- `setup.ts`: matchers do jest-dom; sobe o servidor MSW antes da suíte (`onUnhandledRequest: "error"`), faz `cleanup` e `server.resetHandlers()` após cada teste e fecha o servidor no fim.
- `server.ts`: `server` do `msw/node` com os handlers padrão.
- `handlers.ts`: handlers MSW tipados pelo `schema.gen.ts`. Padrão: caminho feliz (`healthReadyOk`). Variações exportadas para `server.use(...)`: `healthReadyUnavailable` (503), `healthReadyNetworkError`, `healthReadyPending` (nunca responde).
- `renderWithProviders.tsx`: renderiza rotas com os providers reais e router em memória.
- Futuramente: fábricas de dados sintéticos.

**Não entra aqui**: os testes em si (ficam ao lado do arquivo testado, `*.test.tsx`), mocks manuais de `fetch` (use MSW), dados reais.

**Convenções locais**:

- Pasta fora da medição de cobertura (é infraestrutura de teste, não produto); a justificativa está em `vitest.config.ts`.
- Requisição sem handler falha o teste: endpoint novo ganha handler padrão aqui na mesma entrega.
- Handlers casam qualquer origem (`*/v1/...`), para não depender da `baseUrl`.
- Helpers usam a mesma pilha de providers do app (`AppProviders`) para que o teste renderize a árvore real.
- Cada render cria um `QueryClient` novo: sem cache compartilhado entre testes.

**Como testar**: exercitada indiretamente por `pnpm test -- --coverage`, de `frontend/`.

**Leia também**: [../AGENTS.md](../AGENTS.md); `AGENTS.md` da raiz, seção 5.
