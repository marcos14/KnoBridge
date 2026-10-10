# frontend/src/components/

**Função**: componentes de interface compartilhados, usados pelo layout e por mais de uma feature.

**Entra aqui**:

- Componentes próprios reutilizáveis, um por arquivo em `PascalCase.tsx`, com teste ao lado (hoje `ApiStatus.tsx`, indicador de status da API no cabeçalho).
- `ui/`: componentes do shadcn/ui (ver [ui/AGENTS.md](ui/AGENTS.md)).

**Não entra aqui**: telas e componentes de uma feature só (`features/<area>/`), layout e rotas (`app/`), chamadas de API (`lib/api/`; aqui só se consomem os hooks).

**Convenções locais**:

- Componentes não conhecem `fetch`: recebem dados por props ou por hooks de `lib/api/`.
- Textos via `useTranslation()`; elementos semânticos e atributos ARIA quando o papel não for implícito (ex.: `role="status"`).
- Estilo com classes Tailwind e `cn()` de `@/lib/utils`; reaproveite `ui/` antes de criar algo novo.

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Renderize com `renderWithProviders({ routes })` e simule a API com MSW (`server.use(...)` com os handlers de `@/test/handlers`). Consulte por papel e texto.

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../AGENTS.md](../../AGENTS.md).
