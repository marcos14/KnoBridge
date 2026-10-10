# frontend/src/

**Função**: código-fonte do painel administrativo. Ponto de entrada (`main.tsx`) e uma pasta por responsabilidade, conforme o layout previsto em [../AGENTS.md](../AGENTS.md).

**Entra aqui**: `main.tsx` (só importa `index.css` e monta `<App />` no `#root`), `index.css` (Tailwind v4 e tema do shadcn/ui), `vite-env.d.ts` (tipos de `import.meta.env`, como `VITE_API_BASE_URL`) e as pastas `app/`, `components/`, `features/`, `i18n/`, `lib/` e `test/`.
**Não entra aqui**: configs de ferramenta (ficam na raiz de `frontend/`), testes E2E (`frontend/e2e/`), documentação (`docs/`).

**Convenções locais**:

- Imports internos pelo alias `@/` (ex.: `@/app/App`), relativos só dentro da mesma pasta.
- Testes `*.test.ts(x)` ao lado do arquivo testado.
- `main.tsx` não tem lógica: é o único arquivo fora da medição de cobertura (justificativa em `vitest.config.ts`).
- Pasta nova recebe `AGENTS.md` na mesma entrega.

**Como testar**: de `frontend/`, `pnpm test -- --coverage` (gate de 95% em lines, branches, functions e statements).

**Leia também**: [../AGENTS.md](../AGENTS.md); `AGENTS.md` da raiz, seções 5 e 6.3.
