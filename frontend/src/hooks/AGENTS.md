# frontend/src/hooks/

**Função**: hooks React genéricos, sem relação com uma área do produto, no caminho que o shadcn/ui espera (alias `hooks` do `components.json`).

**Entra aqui**: `use-current-workspace.ts` (`useCurrentWorkspace`: o `:workspaceId` da URL e a membership do usuário nele, lida do `me`; usado pelos guardas, pelo shell e pelas telas de workspace); `use-mobile.ts` (`useIsMobile`, usado pelo `components/ui/sidebar.tsx`; reescrito com `useSyncExternalStore` porque a versão do shadcn chama `setState` dentro de efeito, o que o lint estrito proíbe); `use-clock.ts` (`useClock`, `ClockContext`, `systemClock`: o relógio do app, injetado pelo `AppProviders` e fixado nos testes, para datas relativas determinísticas); `use-list-search.ts` (`useListSearch(spec)`: busca, filtros, ordenação e página de uma listagem lidos e gravados na query string; busca, filtro e ordenação nova voltam à primeira página; digitar substitui a entrada do histórico; cada mudança parte da URL atual); `use-offset-clamp.ts` (`useOffsetClamp`: volta à última página válida quando o `offset` passou do fim de uma lista paginada no servidor).
**Não entra aqui**: hooks de dados da API (`lib/api/`), hooks de uma feature (`features/<area>/`), funções puras (`lib/`).

**Convenções locais**:

- Nome de arquivo em `kebab-case` como gera o shadcn; um hook por arquivo.
- Dentro da medição de cobertura: cada hook é coberto por teste próprio ou pelos componentes que o usam (`use-mobile.ts`, pelos testes do `app/shell/` em viewport de celular).

**Como testar**: de `frontend/`, `pnpm test -- --coverage`. Em jsdom, `window.matchMedia` vem de `src/test/matchMedia.ts` (`setMobileViewport(true)`).

**Leia também**: [../AGENTS.md](../AGENTS.md); [../components/ui/AGENTS.md](../components/ui/AGENTS.md).
