# frontend/e2e/stack/

**Função**: testes ponta a ponta do painel contra a stack inteira do compose (`deploy/docker-compose.yml` + `deploy/docker-compose.e2e.yml`): API, Postgres, Mailpit e o nginx do painel, todos reais. Configurados por `playwright.stack.config.ts` (projeto `stack`), fora do `pnpm e2e` comum.

**Entra aqui**: `platform.spec.ts` (o fluxo navegável: setup → login → workspace e convite do proprietário → aceite pelo link do e-mail → convite de leitor → esqueci a senha → redefinição → provedor `fake` e assistente → chat "sem fonte" com avaliação → a conversa vista pelo proprietário → tema que acompanha a conta), `mailpit.ts` (lê os e-mails pela API HTTP do Mailpit e devolve o link do token) e outros fluxos que só fazem sentido com o backend de verdade.
**Não entra aqui**: testes que passam sem backend (ficam em `../`, com respostas sintéticas via `page.route`), testes de componente (Vitest, em `src/`), dados reais.

**Convenções locais**:

- Só dados sintéticos, e-mails `@example.test`. O superadmin é fixo (`E2E_ADMIN_EMAIL`/`E2E_ADMIN_PASSWORD`): banco limpo faz o setup, banco usado entra com ele. O resto ganha um sufixo por rodada, para repetir sem `down -v`.
- Uma pessoa por contexto do navegador (`browser.newContext()`), para cookies e `localStorage` separados.
- Sem `waitForTimeout`: espere pelo estado (`expect`, `expect.poll` com `timeout` explícito para e-mails). Depois de navegar pelo cliente, espere o título da nova página antes de preencher campos de mesmo nome.
- URLs só por ambiente: `E2E_BASE_URL` (painel) e `E2E_MAILPIT_URL`.
- Sem retentativas; um worker, na ordem do arquivo.

**Como testar**: com a stack no ar (`docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.e2e.yml up -d --build --wait`, da raiz), de `frontend/`: `pnpm e2e:stack`. Depois, `down -v`.

**Leia também**: [../AGENTS.md](../AGENTS.md); [docs/guias/subir-ambiente.md](../../../docs/guias/subir-ambiente.md) (seção do E2E contra a stack); [deploy/AGENTS.md](../../../deploy/AGENTS.md).
