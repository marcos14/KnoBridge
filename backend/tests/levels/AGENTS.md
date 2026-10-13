# backend/tests/levels/

**Função**: testes de `src/knobridge/levels/`.

**Entra aqui**: `test_level.py` (ordem dos níveis, unitário) e `test_levels_rls.py` (contra Postgres real: `create_workspace_levels`; RLS de `workspace_levels` e `member_product_levels` como dono e não dono, com leitura, alteração e exclusão invisíveis em outro workspace e inserção em workspace alheio recusada; credencial e produto de outro workspace recusados pelas FKs compostas; credencial e modelo juntos; credencial em uso por um nível não exclui; nível gravado some com a membership, o produto ou o workspace).
**Não entra aqui**: testes de rotas (`tests/api/`), da migração `0018` (`tests/migrations/test_migration_0018.py`).

**Convenções locais**:
- Testes de banco levam `@pytest.mark.integration`; o banco é compartilhado, então cada teste cria seus workspaces, usuários, credenciais (tipo `fake`, texto cifrado fictício) e produtos com valores únicos.
- Sem rede, sem relógio real.

**Como testar**: de `backend/`, `uv run pytest tests/levels` (exige Docker).

**Leia também**: [levels/AGENTS.md](../../src/knobridge/levels/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
