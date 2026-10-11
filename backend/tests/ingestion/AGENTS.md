# backend/tests/ingestion/

**Função**: testes de `src/knobridge/ingestion/`: a validação da configuração de fonte por tipo, o parsing para Markdown, o chunking e as tabelas do índice de conhecimento contra Postgres real.

**Entra aqui**: `test_parsing.py` e `test_commit_rendering.py` (unitários, sem banco: Markdown, texto, código por extensão, PDF/DOCX/XLSX/PPTX das fixtures sintéticas de `tests/fixtures/documents/`, HTML página x fragmento, commits com metadados completos, parciais e malformados, encodings e erros de domínio), `test_chunking.py` e `test_code_chunking.py` (unitários, sem banco: Markdown por títulos, seção grande com sobreposição, documento convertido sem linhas, commit curto e longo, hash estável, divisor por linhas; TS/TSX/JS/Go por AST com símbolo, escopo pai e linhas, classe grande por métodos, função enorme por linhas, fallback por linhas), com `chunking_support.py` (`parsed`/`chunks` passam o arquivo sintético pelo parser real), `test_source_config.py` (unitários, sem banco: validação por tipo, exatamente um entre `path` e `url`, https sem credenciais, nomes de branch, limites, `Source.typed_config`), `test_index_rls.py` (RLS como dono e não dono via `rls_database_url` nas seis tabelas; inserção em workspace alheio recusada; FKs compostas de credencial, coleção e chunk; chave natural única por fonte; `tsv` gerado; busca por cosseno no `vector(1536)`; cascatas e `CHECK`s).
**Não entra aqui**: testes da cadeia de migrações (`tests/migrations/`), rotas (`tests/api/`), conectores (`tests/connectors/`), chamadas reais a provedores de embedding.

**Convenções locais**:
- Os de banco levam `@pytest.mark.integration`; o banco é compartilhado, então cada teste cria seus workspaces, credenciais (tipo `fake`, texto cifrado fictício) e linhas com valores únicos.
- As fixtures de documento são geradas e mínimas (texto inventado); para trocar, gere outra igualmente pequena, nunca um arquivo real.
- Código e Markdown dos testes de chunking são trechos sintéticos escritos no próprio teste.
- Vetores sintéticos (`_vector(eixo)`, unitários num eixo), nunca embeddings reais. Caminhos absolutos vêm de `tmp_path`.

**Como testar**: de `backend/`, `uv run pytest tests/ingestion` (exige Docker).

**Leia também**: [ingestion/AGENTS.md](../../src/knobridge/ingestion/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
