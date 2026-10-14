# widget/

**Função**: o widget embutível do KnoBridge, o Web Component `<knobridge-chat>` que um site hospedeiro carrega num único arquivo JS para conversar com um produto pelas rotas públicas `/v1/widget/{kbp_}/...`. Pacote pnpm próprio, que não depende do `frontend/`.

**Entra aqui**: `src/` (elemento, cliente da API pública, lógica da conversa, i18n e utilitários, com os testes ao lado), `package.json`, `pnpm-lock.yaml`, configs de TypeScript, ESLint, Prettier, Vite e Vitest.
**Não entra aqui**: o painel (vai para `frontend/`, inclusive a tela de configuração e a prévia do widget), as rotas públicas (`backend/src/knobridge/api/widget_public.py` e `widget_conversations.py`), documentação (vai para `docs/`, contrato em `docs/specs/widget.md`), o build (`dist/`, gerado e ignorado pelo git).

**Convenções locais**:

- Lit 3, TypeScript `strict` sem decorators (propriedades em `static properties` com `declare`; `useDefineForClassFields: false`). Sem `any`.
- Build: Vite em modo biblioteca, **um** arquivo IIFE `dist/knobridge-chat.js`, sem `import` dinâmico, CSS externo, fontes nem `eval`. O `vite.config.ts` imprime o tamanho bruto e gzip e falha acima de 60 KiB gzip (orçamento da spec).
- Nada de `innerHTML` com conteúdo da API: o Markdown da resposta vira uma árvore (`src/lib/markdown.ts`) renderizada por templates do Lit, que escapam todo texto. Estilos só no Shadow DOM, e variáveis por `styleMap` (CSSOM), para funcionar com CSP restritiva.
- Sem `console` no build de produção: avisos só por `devWarn` (`import.meta.env.DEV`).
- Tipos do fio escritos à mão em `src/api/types.ts`, reduzidos ao que o widget lê e alinhados aos schemas de `docs/specs/openapi.json` (um cliente gerado pesaria no bundle).
- Textos de interface em `src/i18n/`; nada de texto fixo nos templates.
- Dependências com versão exata; o `pnpm-lock.yaml` é versionado.

**Como testar**:

```sh
pnpm install --frozen-lockfile
pnpm lint && pnpm format:check && pnpm typecheck
pnpm test        # Vitest + jsdom; cobertura sempre ligada, thresholds de 95 em lines, branches, functions e statements
pnpm build       # dist/knobridge-chat.js e o tamanho medido
```

Testes sem rede: o `fetch` global é trocado pelo fake de `src/test/fake-api.ts`, e o SSE é escrito pelo próprio teste com um `ReadableStream`.

**Leia também**: [docs/specs/widget.md](../docs/specs/widget.md), [docs/specs/chat-sse.md](../docs/specs/chat-sse.md) (seção "No canal widget"), [ADR 0009](../docs/adr/0009-canais-mcp-e-widget.md); `AGENTS.md` da raiz, seções 5 e 6.
