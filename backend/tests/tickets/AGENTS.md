# backend/tests/tickets/

**Função**: testes de `src/knobridge/tickets/` contra Postgres real: RLS das tabelas de chamados, a busca do token de envio pelo prefixo, chaves, `CHECK`s, FKs compostas e exclusões, e a cifra do segredo do webhook.

**Entra aqui**:
- `tickets_support.py`: `run_db`, `seed` (workspace novo com fonte `tickets`, token de envio, entrada `pending` na caixa, assistente, conversa e pedido `pending` sobre uma resposta "sem fonte"), `count_by_model`, `new_token`, `tickets_source`, `pending_entry`, `pending_request` e `add_answer`.
- `conftest.py`: `rls_database_url` (o banco como dono e como não dono).
- `test_tickets_rls.py`: RLS forçada nas três tabelas, isolamento entre workspaces (leitura, alteração, exclusão e inserção alheia recusada), token achado pelo `token_prefix` só em modo de sistema e prefixo único na instância.
- `test_tickets_constraints.py`: fonte `tickets`, execução `ingest` e documento `ticket` aceitos; um token por fonte e formatos; `(source_id, external_id)` único; os `CHECK`s de estado da caixa e do pedido; um pedido por mensagem; FKs compostas; cascatas da fonte, da conversa, do assistente e do workspace; colunas e `CHECK`s do webhook em `assistants`.
- `test_webhook_secret.py` (unitário): cifra e decifra do segredo, presa ao assistente e com chave própria.

**Não entra aqui**: rotas (`tests/api/`), cadeia de migrações (`tests/migrations/`), a config da fonte (`tests/ingestion/test_source_config.py`).

**Convenções locais**:
- Os de banco levam `@pytest.mark.integration`; o banco é compartilhado, então cada teste cria seus workspaces com valores únicos.
- Tokens e segredos sintéticos (`kbi_<prefixo>_<segredo>` gerado no teste, `kbw_` de letras repetidas), nunca reais; chamados inventados e mínimos.

**Como testar**: de `backend/`, `uv run pytest tests/tickets` (exige Docker).

**Leia também**: [tickets/AGENTS.md](../../src/knobridge/tickets/AGENTS.md); [tests/AGENTS.md](../AGENTS.md).
