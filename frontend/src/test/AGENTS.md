# frontend/src/test/

**Função**: infraestrutura de testes do Vitest. Setup global e helpers compartilhados entre os testes de componentes.

**Entra aqui**: `setup.ts` (matchers do jest-dom e `cleanup` após cada teste), `renderWithProviders.tsx` (renderiza rotas com os providers reais e router em memória) e, quando surgirem, handlers MSW e fábricas de dados sintéticos.
**Não entra aqui**: os testes em si (ficam ao lado do arquivo testado, `*.test.tsx`), mocks manuais de `fetch` (use MSW), dados reais.

**Convenções locais**:

- Pasta fora da medição de cobertura (é infraestrutura de teste, não produto); a justificativa está em `vitest.config.ts`.
- Helpers usam a mesma pilha de providers do app (`AppProviders`) para que o teste renderize a árvore real.
- Cada render cria um `QueryClient` novo: sem cache compartilhado entre testes.

**Como testar**: exercitada indiretamente por `pnpm test -- --coverage`, de `frontend/`.

**Leia também**: [../AGENTS.md](../AGENTS.md); `AGENTS.md` da raiz, seção 5.
