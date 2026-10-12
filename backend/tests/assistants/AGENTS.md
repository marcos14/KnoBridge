# backend/tests/assistants/

**Função**: testes de `src/knobridge/assistants/` contra Postgres real: isolamento por RLS de `assistants` e `assistant_collections`, as FKs compostas que prendem credencial e coleções ao workspace, as regras de exclusão e o serviço.

**Entra aqui**: `test_assistants_rls.py` (RLS como dono e não dono pela fixture `rls_database_url`: leitura, alteração e exclusão invisíveis em outro workspace, inserção em workspace alheio recusada; credencial de outro workspace recusada pela FK em modo de sistema e pelo serviço; mensagem de "sem fonte" padrão; nome repetido na alteração; credencial em uso não exclui; exclusão do workspace cascateia). `test_assistant_collections_rls.py` (RLS como dono e não dono: vínculo de outro workspace invisível e não excluível, inserção em workspace alheio recusada; coleção de outro workspace recusada pela FK em modo de sistema e pelo serviço, na criação e na alteração; troca do conjunto; cascata ao excluir a coleção ou o assistente). As regras pela API (papéis, viewer só vê ativos, validação, CSRF, `provider_in_use`) ficam em `tests/api/test_assistants.py`.
**Não entra aqui**: testes de rotas (`tests/api/`), da cadeia de migrações (`tests/migrations/`), chamadas a provedores de LLM.

**Convenções locais**:
- Todos levam `@pytest.mark.integration`; o banco é compartilhado, então cada teste cria seus workspaces, credenciais (tipo `fake`, texto cifrado fictício) e usuários com valores únicos.
- Relógio `FrozenClock`; sem rede.

**Como testar**: de `backend/`, `uv run pytest tests/assistants` (exige Docker).

**Leia também**: [assistants/AGENTS.md](../../src/knobridge/assistants/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
