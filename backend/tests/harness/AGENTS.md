# backend/tests/harness/

**Função**: testes de `src/knobridge/harness/` contra Postgres real: RLS das tabelas do harness, a busca do runner pelo prefixo do token, chaves, `CHECK`s, FKs compostas e exclusões.

**Entra aqui**:
- `harness_support.py`: `run_db` (roda um cenário num engine próprio), `seed` (workspace novo com runner, fonte `runner`, módulo, tarefa, item e rejeição), `count_by_model`, `new_runner`, `runner_source` e `rule_item`.
- `conftest.py`: `rls_database_url` (o banco como dono e como não dono).
- `test_harness_rls.py`: RLS forçada nas cinco tabelas, isolamento de tarefas e itens entre workspaces (leitura, alteração, exclusão e inserção alheia recusada), runner achado pelo `token_prefix` só em modo de sistema e prefixo único na instância.
- `test_harness_constraints.py`: fonte `runner` aceita e par `(runner_id, repository)` único no workspace; documentos e `run_items` `knowledge`; FKs compostas de módulo e runner; `SET NULL` só da coluna ao excluir runner (tarefa) e tarefa (item); chave de item única por fonte e com formato checado; padrões do item; formato do commit; módulo sem padrões; cascatas da fonte e do workspace.
- `test_runner_tokens.py` (unitário): formato do token, prefixo de token bem formado e comparação do hash.
- `test_runner_presence.py`: `authenticate_runner` com `last_seen_at` gravado no máximo a cada 10 s e nada achado fora do modo de sistema.
- A seguir (plano 0004): fila, módulos e resultado. As rotas do runner e do painel de runners ficam em `tests/api/` (`test_runners.py`, `test_runner_heartbeat.py`).

**Não entra aqui**: rotas (`tests/api/`), cadeia de migrações (`tests/migrations/`), o pacote `runner/` (testes próprios em `runner/tests/`).

**Convenções locais**:
- Todos levam `@pytest.mark.integration`; o banco é compartilhado, então cada teste cria seus workspaces e runners com valores únicos (prefixo aleatório de 8 caracteres).
- Tokens sintéticos (`kbr_<prefixo>_<segredo>` gerado no teste), nunca um token real.

**Como testar**: de `backend/`, `uv run pytest tests/harness` (exige Docker).

**Leia também**: [harness/AGENTS.md](../../src/knobridge/harness/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
