# frontend/e2e/

**Função**: testes ponta a ponta com Playwright, contra o build de produção servido por `vite preview` (configurado no `webServer` de `playwright.config.ts`).

**Entra aqui**: poucos testes valiosos, `*.spec.ts`, dos fluxos críticos (hoje `smoke.spec.ts`: o app abre no shell com título, landmark `main` e a tela "sem workspace"; anônimo é levado ao login; o tema escuro salvo é aplicado pelo script do `index.html` antes do app carregar; e `chat.spec.ts`: a primeira pergunta cria a conversa, a resposta chega por SSE com citação e o painel da fonte abre, tudo com respostas sintéticas via `page.route`). No futuro: criar pipeline no canvas, rodar com amostra e ver a saída.
**Não entra aqui**: testes de unidade ou de componente (ficam ao lado do código em `src/`, com Vitest), dados reais.

**Convenções locais**:

- Nomes `test_<fluxo>_<comportamento>`; localizadores por papel e texto (`getByRole`), nunca por classe CSS.
- Sem `waitForTimeout`; use as asserções com espera automática do Playwright.
- Sem retentativas (`retries: 0`): teste instável se corrige, não se repete.
- Teste que não precisa do backend não pode depender dele (o smoke passa com a API fora do ar; as respostas que os guardas de rota pedem, `/v1/setup/status` e `/v1/me`, são sintéticas, via `page.route`). Os que precisarem rodam na CI contra o backend em container.
- Configuração tipada por `tsconfig.node.json`; o Vitest não lê esta pasta.

**Como testar**: de `frontend/`, uma vez `pnpm exec playwright install chromium`, depois `pnpm e2e` (faz o build e sobe o preview na porta 4173).

**Leia também**: [../AGENTS.md](../AGENTS.md); `AGENTS.md` da raiz, seção 5.
