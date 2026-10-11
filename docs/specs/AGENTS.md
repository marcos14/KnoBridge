# docs/specs/

**Função**: contratos do KnoBridge, em formato que humanos e máquinas leem. O que estiver aqui é a referência que backend, frontend, conectores e harness precisam respeitar.

**Entra aqui**
- `openapi.json`: documento OpenAPI da API `/v1`, **gerado** a partir de `create_app` pelo comando `knobridge-openapi` do backend. É a fonte dos tipos do cliente do frontend (`frontend/src/lib/api/schema.gen.ts`).
- `modelo-de-dados.md`: tabelas do Postgres, convenções de nomes, escopo de RLS e diagrama Mermaid. Atualizado na mesma entrega de toda migração que muda tabela.
- `chat-sse.md`: eventos Server-Sent Events da resposta do chat (`citations`, `delta`, `done`, `error`), a regra de "sem fonte" e os estados da mensagem. O OpenAPI só declara `text/event-stream` nessa rota; o formato dos eventos vive aqui e muda junto com `backend/src/knobridge/api/conversations.py`.
- `chat.md`: o comportamento do chat além do fio: recuperação de fontes (`HybridRetriever`), regra de citações, interface `Retriever`, orquestração em duas fases, estados das mensagens, janela de histórico, feedback e visão administrativa. Muda junto com `backend/src/knobridge/conversations/` e `retrieval/retriever.py`/`context.py`.
- `conectores.md`: contrato dos conectores (`list_changes`, `fetch`, `permissions`, `test_connection` e os valores trocados), seleção de arquivos, conectores de pasta e Git, cursores versionados e a suíte de contrato. Muda junto com `backend/src/knobridge/connectors/` e `ingestion/source_config.py`.
- `indexacao.md`: parsing, chunking, embeddings e cache, execução no Temporal (`knobridge.ingestion.v1`), agendamento, custo registrado, busca híbrida com limiar e o caminho até a citação. Muda junto com `backend/src/knobridge/ingestion/`, `workers/`, `retrieval/` e `llm/embeddings*`/`pricing.py`.
- `autenticacao.md`: sessão, CSRF, tokens de e-mail, convites, limitação de login, setup, superadmin, papéis e a matriz de permissões por rota e por tela. Muda junto com as dependências de `backend/src/knobridge/api/deps.py`, `tenancy/rbac.py` e o `minRole` de `frontend/src/app/shell/navItems.ts`.
- Futuramente: formato do `.md` de conhecimento e seu frontmatter, schema JSON do harness, formato do grafo do canvas. Um arquivo por contrato, em Markdown (pt-BR) ou no formato nativo do contrato (JSON Schema, OpenAPI).

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
