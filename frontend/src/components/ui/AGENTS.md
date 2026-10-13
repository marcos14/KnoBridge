# frontend/src/components/ui/

**Função**: componentes do [shadcn/ui](https://ui.shadcn.com), copiados pelo CLI do shadcn conforme `frontend/components.json` (estilo `new-york`, Tailwind v4, tema em `src/index.css`).

**Entra aqui**: só os componentes de fato usados (hoje `badge.tsx` e `button.tsx`; `input.tsx`, `label.tsx` e `form.tsx`, a base dos formulários das telas de autenticação do plano 0002; `sidebar.tsx`, `dropdown-menu.tsx` e `avatar.tsx`, usados pelo shell em `app/shell/`, com `sheet.tsx`, `tooltip.tsx`, `separator.tsx` e `skeleton.tsx`, dependências internas do `sidebar.tsx`; `select.tsx`, `radio-group.tsx` e `alert-dialog.tsx`, usados pelas telas de `features/account/` e `features/members/`; `table.tsx` (base do `components/DataTable.tsx`), `dialog.tsx` e `tabs.tsx`, usados por `features/members/`; `textarea.tsx` (campos de várias linhas do `components/TextField.tsx`) e `checkbox.tsx`, usados por `features/products/`), adicionados com `pnpm dlx shadcn@latest add <nome>` de dentro de `frontend/`.
**Não entra aqui**: componentes próprios ou compostos (`components/`), lógica, textos, chamadas de API.

**Convenções locais**:

- Edite só o necessário, para que atualizações do upstream continuem triviais. Depois de `add`, rode `pnpm format` e `pnpm lint`; o CLI pode instalar pacotes indevidos (confira o diff do `package.json`) e já gerou `import { cn } from "cn"` com o pacote `cn` (troque por `@/lib/utils` e remova o pacote). O `add` também pergunta se sobrescreve arquivos existentes (ex.: `button.tsx`): responda não. Em `form.tsx` só houve ajustes exigidos pelo lint estrito (`interface`, condição sempre falsa, conversões redundantes). Em `sidebar.tsx`: ajustes do lint estrito (`interface`, `String()` em template, sem `return` de expressão `void`, largura fixa no lugar de `Math.random()` no `SidebarMenuSkeleton`) e as props `mobileTitle`/`mobileDescription` do `Sidebar`, para traduzir o título oculto do `Sheet` no celular. O `useIsMobile` que ele importa fica em `src/hooks/`.
- Fora da medição de cobertura (código de terceiros, exercitado pelos componentes que o usam; justificativa em `vitest.config.ts`). A regra `react-refresh/only-export-components` está desligada aqui, porque cada arquivo exporta também suas variantes `cva`.
- Componente que ninguém mais usa sai na mesma entrega.

**Como testar**: indiretamente, pelos testes dos componentes que os usam (`pnpm test -- --coverage`, de `frontend/`).

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../../AGENTS.md](../../../AGENTS.md).
