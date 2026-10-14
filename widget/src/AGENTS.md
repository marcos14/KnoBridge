# widget/src/

**Função**: código-fonte do widget. `index.ts` é a entrada do bundle: lê a origem do `<script>` que o carregou (base padrão da API) e registra `<knobridge-chat>` só se ainda não existir.

**Entra aqui**: `index.ts` e as pastas `api/` (cliente das rotas públicas e leitor de SSE), `chat/` (a conversa do visitante, sem renderização), `element/` (o elemento Lit, templates e estilos), `i18n/` (textos), `lib/` (funções puras: Markdown seguro, aparência, armazenamento) e `test/` (fakes e helpers de teste).
**Não entra aqui**: configs de ferramenta (ficam em `widget/`), documentação (`docs/`).

**Convenções locais**:

- Imports relativos com a extensão `.ts`.
- Testes `*.test.ts` ao lado do arquivo testado, nomes `test_<unidade>_<comportamento>`.
- `element/` não chama `fetch`: fala com a API por `chat/` e `api/`.
- Pasta nova recebe `AGENTS.md` na mesma entrega.

**Como testar**: de `widget/`, `pnpm test` (gate de 95%).

**Leia também**: [../AGENTS.md](../AGENTS.md).
