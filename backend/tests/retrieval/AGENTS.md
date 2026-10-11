# backend/tests/retrieval/

**Função**: testes de `src/knobridge/retrieval/`: a fusão RRF, a remoção de chunks vizinhos e a busca híbrida contra Postgres + pgvector reais.

**Entra aqui**:
- `test_fusion.py` (unitários, sem banco): RRF, sobreposição de trechos, `drop_neighbors`, `display_text`, `candidate_count` e os campos de citação de `SearchHit`.
- `test_search.py` (integração): fusão vetorial + FTS, isolamento por workspace e por coleção, várias coleções, similaridade mínima, pergunta sem relação devolvendo vazio, identificadores de código e caminhos pelo FTS, vizinhos do mesmo documento, limite, um embedding por modelo, chunks de outro modelo fora do braço vetorial, erro do provedor e número constante de statements.
- `test_rerank.py` (unitário): o `Protocol` `Reranker` aceita uma implementação estrutural.
- `retrieval_support.py`: `run_db` com um `Db` (engine novo por cenário) que cria workspace, credencial `fake` com a chave cifrada de verdade (o serviço a decifra), coleção com fonte e chunks gravados direto no banco com `fake_vector(content)`, sem o workflow de ingestão; `search` chama o `SearchService`; `statements()` conta os statements do engine.

**Não entra aqui**: testes da rota de busca (`tests/api/test_search_route.py`), do chunking e do modelo do índice (`tests/ingestion/`), chamadas reais a provedores de embedding.

**Convenções locais**:
- Os de banco levam `@pytest.mark.integration` e usam `app_database_url` (papel não superusuário, RLS valendo); cada teste cria o seu workspace.
- Embeddings só pelo `FakeEmbeddingProvider` (tipo `fake`) ou pelos fakes de `fakes.embedding_provider`; textos de teste em pt-BR com palavras escolhidas para ficar perto ou longe no espaço do fake.

**Como testar**: de `backend/`, `uv run pytest tests/retrieval` (exige Docker).

**Leia também**: [retrieval/AGENTS.md](../../src/knobridge/retrieval/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
