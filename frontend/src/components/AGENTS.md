# frontend/src/components/

**Função**: componentes de interface compartilhados, usados pelo layout e por mais de uma feature.

**Entra aqui**:

- Componentes próprios reutilizáveis, um por arquivo em `PascalCase.tsx`, com teste ao lado (hoje `ApiStatus.tsx`, indicador de status da API no cabeçalho; `TextField.tsx`, campo de react-hook-form com label, dica e erro; `FormAlert.tsx`, erro de envio de formulário com `role="alert"`, que recebe o foco ao aparecer; os dois usados pelas telas de `features/auth/` e `features/account/`; `DataTable.tsx`, tabela genérica com colunas tipadas, estado vazio e paginação por `offset` ("1–20 de 45", anterior/próxima), em que quem chama controla o `offset` (paginação no servidor ou no navegador; usada por membros e depois por auditoria, administração e conversas); `ConfirmDialog.tsx`, confirmação genérica (`AlertDialog`) com o gatilho recebido por prop, usada por membros, convites e sessões).
- `ui/`: componentes do shadcn/ui (ver [ui/AGENTS.md](ui/AGENTS.md)).

**Não entra aqui**: telas e componentes de uma feature só (`features/<area>/`), layout e rotas (`app/`), chamadas de API (`lib/api/`; aqui só se consomem os hooks).

**Convenções locais**:

- Componentes não conhecem `fetch`: recebem dados por props ou por hooks de `lib/api/`.
- Textos via `useTranslation()`; elementos semânticos e atributos ARIA quando o papel não for implícito (ex.: `role="status"`).
- Estilo com classes Tailwind e `cn()` de `@/lib/utils`; reaproveite `ui/` antes de criar algo novo.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Renderize com `renderWithProviders({ routes })` e simule a API com MSW (`server.use(...)` com os handlers de `@/test/handlers`). Consulte por papel e texto.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../AGENTS.md](../../AGENTS.md).
