# widget/src/test/

**Função**: infraestrutura dos testes do widget: o `fetch` falso das rotas públicas com respostas por "MÉTODO /caminho" e SSE controlado pelo teste (`fake-api.ts`), e helpers para montar o elemento, consultar o Shadow DOM, digitar e coletar eventos (`dom.ts`).

**Entra aqui**: fakes e helpers usados por vários arquivos de teste.
**Não entra aqui**: testes (ficam ao lado do código), código de produto. Fica fora da medição de cobertura (justificativa em `vitest.config.ts`).

**Convenções locais**: sem rede e sem `sleep`; esperas só por `vi.waitFor` sobre um estado visível ou `updateComplete`. Dados sintéticos (chave `kbp_` e token `kbv_` de teste).

**Como testar**: de `widget/`, `pnpm test`.

**Leia também**: [../AGENTS.md](../AGENTS.md).
