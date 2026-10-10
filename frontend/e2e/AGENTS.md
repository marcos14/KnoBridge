# frontend/e2e/

**Função**: testes ponta a ponta com Playwright, contra o build de produção servido por `vite preview` (configurado no `webServer` de `playwright.config.ts`).

**Entra aqui**: poucos testes valiosos, `*.spec.ts`, dos fluxos críticos (hoje só o smoke `smoke.spec.ts`: o app abre, mostra o título e o landmark `main`). No futuro: criar pipeline no canvas, rodar com amostra e ver a saída; chat de teste com citações.
**Não entra aqui**: testes de unidade ou de componente (ficam ao lado do código em `src/`, com Vitest), dados reais.

**Convenções locais**:

- Nomes `test_<fluxo>_<comportamento>`; localizadores por papel e texto (`getByRole`), nunca por classe CSS.
- Sem `waitForTimeout`; use as asserções com espera automática do Playwright.
- Sem retentativas (`retries: 0`): teste instável se corrige, não se repete.
- Teste que não precisa do backend não pode depender dele (o smoke passa com a API fora do ar). Os que precisarem rodam na CI contra o backend em container.
- Configuração tipada por `tsconfig.node.json`; o Vitest não lê esta pasta.

**Como testar**: de `frontend/`, uma vez `pnpm exec playwright install chromium`, depois `pnpm e2e` (faz o build e sobe o preview na porta 4173).

**Leia também**: [../AGENTS.md](../AGENTS.md); `AGENTS.md` da raiz, seção 5.
