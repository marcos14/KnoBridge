# frontend/src/components/ui/

**Função**: componentes do [shadcn/ui](https://ui.shadcn.com), copiados pelo CLI do shadcn conforme `frontend/components.json` (estilo `new-york`, Tailwind v4, tema em `src/index.css`).

**Entra aqui**: só os componentes de fato usados (hoje `badge.tsx` e `button.tsx`, mais `input.tsx`, `label.tsx` e `form.tsx`, a base dos formulários das telas de autenticação do plano 0002), adicionados com `pnpm dlx shadcn@latest add <nome>` de dentro de `frontend/`.
**Não entra aqui**: componentes próprios ou compostos (`components/`), lógica, textos, chamadas de API.

**Convenções locais**:

- Edite só o necessário, para que atualizações do upstream continuem triviais. Depois de `add`, rode `pnpm format` e `pnpm lint`; o CLI pode instalar pacotes indevidos (confira o diff do `package.json`) e já gerou `import { cn } from "cn"` com o pacote `cn` (troque por `@/lib/utils` e remova o pacote). Em `form.tsx` só houve ajustes exigidos pelo lint estrito (`interface`, condição sempre falsa, conversões redundantes).
- Fora da medição de cobertura (código de terceiros, exercitado pelos componentes que o usam; justificativa em `vitest.config.ts`). A regra `react-refresh/only-export-components` está desligada aqui, porque cada arquivo exporta também suas variantes `cva`.
- Componente que ninguém mais usa sai na mesma entrega.

**Como testar**: indiretamente, pelos testes dos componentes que os usam (`pnpm test -- --coverage`, de `frontend/`).

**Leia também**: [../AGENTS.md](../AGENTS.md); [../../../AGENTS.md](../../../AGENTS.md).
