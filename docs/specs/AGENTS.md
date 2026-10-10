# docs/specs/

**Função**: contratos do KnoBridge, em formato que humanos e máquinas leem. O que estiver aqui é a referência que backend, frontend, conectores e harness precisam respeitar.

**Entra aqui**
- `openapi.json`: documento OpenAPI da API `/v1`, **gerado** a partir de `create_app` pelo comando `knobridge-openapi` do backend. É a fonte dos tipos do cliente do frontend (`frontend/src/lib/api/schema.gen.ts`).
- Futuramente: modelo de dados, formato do `.md` de conhecimento e seu frontmatter, protocolo dos conectores, schema JSON do harness, formato do grafo do canvas. Um arquivo por contrato, em Markdown (pt-BR) ou no formato nativo do contrato (JSON Schema, OpenAPI).

**Não entra aqui**
- Código, geradores ou scripts (ficam em `backend/`, `frontend/` ou `scripts/`).
- Guias de operação (`docs/guias/`) e decisões de arquitetura (`docs/adr/`).
- Exemplos com dados reais de clientes.

**Convenções locais**
- `openapi.json` nunca é editado à mão. Mudou rota ou schema no backend: regenere e commite junto, na mesma entrega.
  ```sh
  cd backend && uv run knobridge-openapi          # grava docs/specs/openapi.json
  cd frontend && pnpm gen:api                     # regenera os tipos do cliente
  ```
- Saída determinística (chaves ordenadas, indentação 2, newline final), para que o diff mostre só mudanças reais.
- A CI roda `pnpm check:api` no frontend: falha se os tipos gerados não baterem com este arquivo.
- Mudança incompatível de contrato exige versão nova da rota (`/v2`) ou ADR.

**Como testar**: de `backend/`, `uv run pytest tests/api/test_openapi.py` (gerador); de `frontend/`, `pnpm check:api` (tipos em dia com o contrato).

**Leia também**: [../AGENTS.md](../AGENTS.md); [backend/AGENTS.md](../../backend/AGENTS.md) (convenções da API); [frontend/AGENTS.md](../../frontend/AGENTS.md).
