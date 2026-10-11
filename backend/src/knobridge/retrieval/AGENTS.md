# backend/src/knobridge/retrieval/

**Função**: recuperação sobre o índice de conhecimento (seção 7.4 da [visão](../../../../docs/01-visao-do-projeto.md)): busca híbrida vetorial + FTS com fusão RRF, filtros por workspace e coleções, similaridade mínima e remoção de vizinhos; e o ponto de extensão do reranker. Sem rotas.

**Entra aqui**:
- `search.py`: `SearchService(credentials, factory)` com `search(db, workspace_id=, collection_ids=, query=, limit=10, min_similarity=0.3) -> list[SearchHit]` e `embed_query`. Passos: coleções + credenciais numa consulta (coleção ausente ou de outro workspace: `CollectionNotFoundError`, 404 `not_found`); um embedding da consulta por par (credencial, modelo), com a chave decifrada só em memória e o provedor sempre fechado; `set_config('hnsw.ef_search', max(100, candidatos), true)`; braço vetorial por modelo (`<=>`, só chunks com `embedding_model` do grupo, corte em `1 - distância >= min_similarity`); braço FTS numa consulta (`websearch_to_tsquery` em `portuguese` OU `simple` OU `simple` sobre a consulta com `/` e `.` trocados por espaço, como o `tsv`; `ts_rank_cd`); RRF; vizinhos removidos; chunks e documentos carregados numa consulta. Número de statements constante: 5 + 1 por modelo extra.
- `SearchHit`: `chunk_id`, `collection_id`, `position`, `content` (inteiro, para o LLM), `meta`, `document` (`DocumentRef`: id, fonte, tipo, chave natural, título, URI), `vector_similarity`, `fts_rank`, `fused_score`; propriedades `path`, `symbol`, `start_line`, `end_line` (lidas do `meta` com tolerância) e `snippet` (corpo sem o cabeçalho `path:`/`symbol:`/`section:`, até 600 caracteres).
- Constantes: `DEFAULT_LIMIT` 10, `MAX_LIMIT` 50, `DEFAULT_MIN_SIMILARITY` 0,3, candidatos por braço `limit × 4` entre 40 e 200.
- `fusion.py` (puro): `reciprocal_rank_fusion` (`RRF_K` = 60, do artigo original; ranks a partir de 1) e `drop_neighbors` sobre `ChunkSpan` (mesmo documento e posições adjacentes, ou faixas de linhas que se cruzam).
- `rerank.py`: `Reranker` (`Protocol`, `rerank(query, hits, limit=)`), sem implementação nem uso (decisão D8 do plano 0003).

**Não entra aqui**: o modelo do índice e a ingestão (`ingestion/`), adaptadores de embedding (`llm/`), a rota "testar busca" (`api/search.py`), o `Retriever` do chat e a montagem do contexto com citações (`conversations/`, plano 0003 F4.2).

**Convenções locais**:
- Limiar (decisão D12): um chunk entra se a similaridade vetorial alcança `min_similarity` ou se casa a consulta FTS. `websearch_to_tsquery` é conjuntivo (todos os termos, fora stop words), então casar o FTS já é sinal forte e é o que acha identificadores exatos; pergunta sem relação não passa em nenhum dos dois e volta vazia (regra 8). A contribuição vetorial ao RRF só vale acima do limiar.
- Vetores de modelos diferentes nunca se comparam: cada modelo é um ranking próprio na fusão; chunks com `embedding_model` diferente do da coleção (reindexação pendente) só aparecem pelo FTS.
- Toda consulta filtra por `workspace_id` e roda na sessão com escopo de RLS de quem chama. O embedding acontece dentro da transação do chamador; quem segura a sessão por mais tempo deve chamar `embed_query` antes.
- Sem `hnsw.iterative_scan` (exige pgvector 0.8+, e a imagem não fixa a versão); o `ef_search` maior compensa o filtro posterior ao índice.
- Logs nunca levam o texto da consulta nem dos chunks.

**Como testar**: de `backend/`, `uv run pytest tests/retrieval tests/api/test_search_route.py` (Postgres real; exige Docker). Gate da suíte inteira: `uv run pytest`.

**Leia também**: [ADR 0004](../../../../docs/adr/0004-indice-de-conhecimento.md); [ingestion/AGENTS.md](../ingestion/AGENTS.md); [llm/AGENTS.md](../llm/AGENTS.md); [tests/retrieval/AGENTS.md](../../../tests/retrieval/AGENTS.md).
