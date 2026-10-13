# backend/tests/products/

**Função**: testes de `src/knobridge/products/` contra Postgres real: isolamento por RLS de `products` e `product_collections`, as FKs compostas que prendem a credencial (transitória) e as coleções ao workspace, as regras de exclusão e o serviço.

**Entra aqui**: `test_products_rls.py` (RLS como dono e não dono pela fixture `rls_database_url`: leitura, alteração e exclusão invisíveis em outro workspace, inserção em workspace alheio recusada; credencial de outro workspace recusada pela FK em modo de sistema; o produto novo com o modelo do primeiro nível configurado (`product_dev`, `support`, `end_user`) e 409 `level_not_configured` sem nenhum; mensagem de "sem fonte" padrão; nome repetido na alteração; credencial em uso não exclui; exclusão do workspace cascateia). `test_product_collections_rls.py` (RLS como dono e não dono: vínculo de outro workspace invisível e não excluível, inserção em workspace alheio recusada; coleção de outro workspace recusada pela FK em modo de sistema e pelo serviço, na criação e na alteração; troca do conjunto; cascata ao excluir a coleção ou o produto). As regras pela API (papéis, viewer só vê ativos, validação, nome com `:<nível>`, `my_max_level`, CSRF, `provider_in_use`, listagem e duplicação) ficam em `tests/api/test_products.py`, `test_product_collections.py` e `test_product_listing.py`.
**Não entra aqui**: testes de rotas (`tests/api/`), da cadeia de migrações (`tests/migrations/`), dos níveis (`tests/levels/`), chamadas a provedores de LLM.

**Convenções locais**:
- Todos levam `@pytest.mark.integration`; o banco é compartilhado, então cada teste cria seus workspaces (com os três níveis e o `product_dev` configurado direto no banco), credenciais (tipo `fake`, texto cifrado fictício) e usuários com valores únicos.
- Relógio `FrozenClock`; sem rede.

**Como testar**: de `backend/`, `uv run pytest tests/products` (exige Docker).

**Leia também**: [products/AGENTS.md](../../src/knobridge/products/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
